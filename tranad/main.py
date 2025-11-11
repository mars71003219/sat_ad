# -*- coding: utf-8 -*-
"""
이 스크립트는 이상 탐지 모델의 훈련, 평가 및 결과 시각화를 위한 메인 실행 파일입니다.

전체 프로세스는 다음과 같이 진행됩니다:
1.  `parser.py`를 통해 전달된 명령줄 인자(데이터셋, 모델 등)를 확인합니다.
2.  지정된 데이터셋의 `processed` 폴더에서 모든 하위 채널(sub-dataset) 목록을 가져옵니다.
3.  각 채널을 순회하며 다음을 반복합니다:
    a. `load_channel_data`: 해당 채널의 `train`, `test`, `labels` 데이터를 로드합니다.
    b. `load_model`: 채널별 모델을 초기화하거나, 기존 체크포인트를 로드합니다.
    c. `prepare_data_for_model`: 로드된 데이터를 모델 입력에 맞게 변환합니다 (e.g., 윈도우 변환).
    d. `backprop`: 모델을 훈련하고, `save_model`로 채널별 모델을 저장합니다.
    e. `backprop`: 평가 모드로 테스트 결과(loss, prediction)를 얻습니다.
    f. `plotter`, `pot_eval`: 결과를 시각화하고 성능을 평가합니다.
"""
# import debugpy
# debugpy.listen(("0.0.0.0", 5678))
# print("Waiting for debugger attach")
# debugpy.wait_for_client()

import pickle
import os
import pandas as pd
from tqdm import tqdm
from src.models import *
from src.constants import *
from src.plotting import *
from src.pot import *
from src.utils import *
from src.diagnosis import *
from src.merlin import *
from torch.utils.data import Dataset, DataLoader, TensorDataset
import torch.nn as nn
from time import time
from pprint import pprint
# from beepy import beep

def convert_to_windows(data, model):
	"""
	시계열 데이터를 시퀀스 기반 모델이 사용할 수 있는 슬라이딩 윈도우 형태로 변환합니다.
	"""
	windows = []; w_size = model.n_window
	for i, g in enumerate(data): 
		if i >= w_size: 
			w = data[i-w_size:i]
		else: 
			w = torch.cat([data[0].repeat(w_size-i, 1), data[0:i]])
		windows.append(w if 'TranAD' in args.model or 'Attention' in args.model else w.view(-1))
	return torch.stack(windows)

def load_channel_data(dataset_path, channel, is_single_file_dataset):
    """특정 채널의 train/test/labels npy 파일을 로드합니다."""
    try:
        if is_single_file_dataset:
            train_data = np.load(os.path.join(dataset_path, 'train.npy'))
            test_data = np.load(os.path.join(dataset_path, 'test.npy'))
            labels = np.load(os.path.join(dataset_path, 'labels.npy'))
        else:
            train_data = np.load(os.path.join(dataset_path, f'{channel}_train.npy'))
            test_data = np.load(os.path.join(dataset_path, f'{channel}_test.npy'))
            labels = np.load(os.path.join(dataset_path, f'{channel}_labels.npy'))
        return train_data, test_data, labels
    except FileNotFoundError as e:
        print(f"Skipping channel {channel} due to missing data file: {e}")
        return None, None, None

def prepare_data_for_model(train_data, test_data, model):
    """데이터를 DataLoader로 변환하고 모델 입력에 맞게 최종 준비합니다."""
    train_loader = DataLoader(train_data, batch_size=train_data.shape[0] if train_data.size > 0 else 1)
    test_loader = DataLoader(test_data, batch_size=test_data.shape[0] if test_data.size > 0 else 1)
    trainD, testD = next(iter(train_loader)), next(iter(test_loader))
    trainO, testO = trainD, testD # Original data copy
    if model.name in ['Attention', 'DAGMM', 'USAD', 'MSCRED', 'CAE_M', 'GDN', 'MTAD_GAT', 'MAD_GAN'] or 'TranAD' in args.model: 
        trainD, testD = convert_to_windows(trainD, model), convert_to_windows(testD, model)
    return trainD, testD, trainO, testO

def save_model(model, optimizer, scheduler, epoch, accuracy_list):
	"""훈련된 모델의 상태를 체크포인트 파일로 저장합니다."""
	folder = f'{checkpoint_folder}/{args.model}/'
	os.makedirs(folder, exist_ok=True)
	file_path = f'{folder}/model_{args.dataset}.ckpt'
	torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'accuracy_list': accuracy_list}, file_path)

def load_model(modelname, dims):
	"""체크포인트에서 모델을 로드하거나, 없을 경우 새로 생성합니다."""
	import src.models
	model_class = getattr(src.models, modelname)
	model = model_class(dims).double()
	optimizer = torch.optim.AdamW(model.parameters() , lr=model.lr, weight_decay=1e-5)
	scheduler = torch.optim.lr_scheduler.StepLR(optimizer, 5, 0.9)
	fname = f'{checkpoint_folder}/{args.model}/model_{args.dataset}.ckpt'
	if os.path.exists(fname) and (not args.retrain or args.test):
		print(f"{color.GREEN}Loading pre-trained model: {model.name} for {args.dataset}{color.ENDC}")
		checkpoint = torch.load(fname)
		model.load_state_dict(checkpoint['model_state_dict'])
		optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
		scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
		epoch = checkpoint['epoch']
		accuracy_list = checkpoint['accuracy_list']
	else:
		print(f"{color.GREEN}Creating new model: {model.name} for {args.dataset}{color.ENDC}")
		epoch = -1; accuracy_list = []
	return model, optimizer, scheduler, epoch, accuracy_list

def backprop(epoch, model, data, dataO, optimizer, scheduler, training = True):
	"""단일 에포크의 훈련 또는 평가를 수행합니다."""
	l = nn.MSELoss(reduction = 'mean' if training else 'none')
	feats = dataO.shape[1]
	
	if 'DAGMM' in model.name:
		l = nn.MSELoss(reduction = 'none')
		compute = ComputeLoss(model, 0.1, 0.005, 'cpu', model.n_gmm)
		n = epoch + 1; w_size = model.n_window
		l1s = []; l2s = []
		if training:
			for d in data:
				_, x_hat, z, gamma = model(d)
				l1, l2 = l(x_hat, d), l(gamma, d)
				l1s.append(torch.mean(l1).item()); l2s.append(torch.mean(l2).item())
				loss = torch.mean(l1) + torch.mean(l2)
				optimizer.zero_grad()
				loss.backward()
				optimizer.step()
			scheduler.step()
			tqdm.write(f'Epoch {epoch},\tL1 = {np.mean(l1s)},\tL2 = {np.mean(l2s)}')
			return np.mean(l1s)+np.mean(l2s), optimizer.param_groups[0]['lr']
		else:
			ae1s = []
			for d in data: 
				_, x_hat, _, _ = model(d)
				ae1s.append(x_hat)
			ae1s = torch.stack(ae1s)
			y_pred = ae1s[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			loss = l(ae1s, data)[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			return loss.detach().numpy(), y_pred.detach().numpy()
	if 'Attention' in model.name:
		l = nn.MSELoss(reduction = 'none')
		n = epoch + 1; w_size = model.n_window
		l1s = []; res = []
		if training:
			for d in data:
				ae, ats = model(d)
				l1 = l(ae, d)
				l1s.append(torch.mean(l1).item())
				loss = torch.mean(l1)
				optimizer.zero_grad()
				loss.backward()
				optimizer.step()
			scheduler.step()
			tqdm.write(f'Epoch {epoch},\tL1 = {np.mean(l1s)}')
			return np.mean(l1s), optimizer.param_groups[0]['lr']
		else:
			ae1s, y_pred = [], []
			for d in data: 
				ae1 = model(d)
				y_pred.append(ae1[-1])
				ae1s.append(ae1)
			ae1s, y_pred = torch.stack(ae1s), torch.stack(y_pred)
			loss = torch.mean(l(ae1s, data), axis=1)
			return loss.detach().numpy(), y_pred.detach().numpy()
	elif 'OmniAnomaly' in model.name:
		if training:
			mses, klds = [], []
			for i, d in enumerate(data):
				y_pred, mu, logvar, hidden = model(d, hidden if i else None)
				MSE = l(y_pred, d)
				KLD = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp(), dim=0)
				loss = MSE + model.beta * KLD
				mses.append(torch.mean(MSE).item()); klds.append(model.beta * torch.mean(KLD).item())
				optimizer.zero_grad()
				loss.backward()
				optimizer.step()
			tqdm.write(f'Epoch {epoch},\tMSE = {np.mean(mses)},\tKLD = {np.mean(klds)}')
			scheduler.step()
			return loss.item(), optimizer.param_groups[0]['lr']
		else:
			y_preds = []
			for i, d in enumerate(data):
				y_pred, _, _, hidden = model(d, hidden if i else None)
				y_preds.append(y_pred)
			y_pred = torch.stack(y_preds)
			MSE = l(y_pred, data)
			return MSE.detach().numpy(), y_pred.detach().numpy()
	elif 'USAD' in model.name:
		l = nn.MSELoss(reduction = 'none')
		n = epoch + 1; w_size = model.n_window
		l1s, l2s = [], []
		if training:
			for d in data:
				ae1s, ae2s, ae2ae1s = model(d)
				l1 = (1 / n) * l(ae1s, d) + (1 - 1/n) * l(ae2ae1s, d)
				l2 = (1 / n) * l(ae2s, d) - (1 - 1/n) * l(ae2ae1s, d)
				l1s.append(torch.mean(l1).item()); l2s.append(torch.mean(l2).item())
				loss = torch.mean(l1 + l2)
				optimizer.zero_grad()
				loss.backward()
				optimizer.step()
			scheduler.step()
			tqdm.write(f'Epoch {epoch},\tL1 = {np.mean(l1s)},\tL2 = {np.mean(l2s)}')
			return np.mean(l1s)+np.mean(l2s), optimizer.param_groups[0]['lr']
		else:
			ae1s, ae2s, ae2ae1s = [], [], []
			for d in data: 
				ae1, ae2, ae2ae1 = model(d)
				ae1s.append(ae1); ae2s.append(ae2); ae2ae1s.append(ae2ae1)
			ae1s, ae2s, ae2ae1s = torch.stack(ae1s), torch.stack(ae2s), torch.stack(ae2ae1s)
			y_pred = ae1s[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			loss = 0.1 * l(ae1s, data) + 0.9 * l(ae2ae1s, data)
			loss = loss[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			return loss.detach().numpy(), y_pred.detach().numpy()
	elif model.name in ['GDN', 'MTAD_GAT', 'MSCRED', 'CAE_M']:
		l = nn.MSELoss(reduction = 'none')
		n = epoch + 1; w_size = model.n_window
		l1s = []
		if training:
			for i, d in enumerate(data):
				if 'MTAD_GAT' in model.name: 
					x, h = model(d, h if i else None)
				else:
					x = model(d)
				loss = torch.mean(l(x, d))
				l1s.append(torch.mean(loss).item())
				optimizer.zero_grad()
				loss.backward()
				optimizer.step()
			tqdm.write(f'Epoch {epoch},\tMSE = {np.mean(l1s)}')
			return np.mean(l1s), optimizer.param_groups[0]['lr']
		else:
			xs = []
			for d in data: 
				if 'MTAD_GAT' in model.name: 
					x, h = model(d, None)
				else:
					x = model(d)
				xs.append(x)
			xs = torch.stack(xs)
			y_pred = xs[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			loss = l(xs, data)
			loss = loss[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			return loss.detach().numpy(), y_pred.detach().numpy()
	elif 'GAN' in model.name:
		l = nn.MSELoss(reduction = 'none')
		bcel = nn.BCELoss(reduction = 'mean')
		msel = nn.MSELoss(reduction = 'mean')
		real_label, fake_label = torch.tensor([0.9]), torch.tensor([0.1]) # label smoothing
		real_label, fake_label = real_label.type(torch.DoubleTensor), fake_label.type(torch.DoubleTensor)
		n = epoch + 1; w_size = model.n_window
		mses, gls, dls = [], [], []
		if training:
			for d in data:
				# 판별자(discriminator) 훈련
				model.discriminator.zero_grad()
				_, real, fake = model(d)
				dl = bcel(real, real_label) + bcel(fake, fake_label)
				dl.backward()
				model.generator.zero_grad()
				optimizer.step()
				# 생성자(generator) 훈련
				z, _, fake = model(d)
				mse = msel(z, d) 
				gl = bcel(fake, real_label)
				tl = gl + mse
				tl.backward()
				model.discriminator.zero_grad()
				optimizer.step()
				mses.append(mse.item()); gls.append(gl.item()); dls.append(dl.item())
			tqdm.write(f'Epoch {epoch},\tMSE = {np.mean(mses)},\tG = {np.mean(gls)},\tD = {np.mean(dls)}')
			return np.mean(gls)+np.mean(dls), optimizer.param_groups[0]['lr']
		else:
			outputs = []
			for d in data: 
				z, _, _ = model(d)
				outputs.append(z)
			outputs = torch.stack(outputs)
			y_pred = outputs[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			loss = l(outputs, data)
			loss = loss[:, data.shape[1]-feats:data.shape[1]].view(-1, feats)
			return loss.detach().numpy(), y_pred.detach().numpy()
	elif 'TranAD' in model.name:
		l = nn.MSELoss(reduction = 'none')
		data_x = torch.DoubleTensor(data); dataset = TensorDataset(data_x, data_x)
		bs = model.batch if training else len(data)
		dataloader = DataLoader(dataset, batch_size = bs)
		n = epoch + 1; w_size = model.n_window
		l1s, l2s = [], []
		if training:
			for d, _ in dataloader:
				local_bs = d.shape[0]
				window = d.permute(1, 0, 2)
				elem = window[-1, :, :].view(1, local_bs, feats)
				z = model(window, elem)
				# TranAD은 두 단계의 예측(z)을 튜플로 반환할 수 있음
			l1 = l(z, elem) if not isinstance(z, tuple) else (1 / n) * l(z[0], elem) + (1 - 1/n) * l(z[1], elem)
			if isinstance(z, tuple): z = z[1]
			l1s.append(torch.mean(l1).item())
			loss = torch.mean(l1)
			optimizer.zero_grad()
			loss.backward(retain_graph=True)
			optimizer.step()
			scheduler.step()
			tqdm.write(f'Epoch {epoch},\tL1 = {np.mean(l1s)}')
			return np.mean(l1s), optimizer.param_groups[0]['lr']
		else:
			for d, _ in dataloader:
				window = d.permute(1, 0, 2)
				elem = window[-1, :, :].view(1, bs, feats)
				z = model(window, elem)
				if isinstance(z, tuple): z = z[1]
			loss = l(z, elem)[0]
			return loss.detach().numpy(), z.detach().numpy()[0]
	else: # 그 외 일반적인 오토인코더 모델
		y_pred = model(data)
		loss = l(y_pred, data)
		if training:
			tqdm.write(f'Epoch {epoch},\tMSE = {loss}')
			optimizer.zero_grad()
			loss.backward()
			optimizer.step()
			scheduler.step()
			return loss.item(), optimizer.param_groups[0]['lr']
		else:
			return loss.detach().numpy(), y_pred.detach().numpy()

if __name__ == '__main__':
    # 1. Find all sub-datasets (channels) for the given dataset
    dataset_path = os.path.join(output_folder, args.dataset)
    if not os.path.exists(dataset_path):
        raise Exception(f"Processed data not found for dataset '{args.dataset}' in '{dataset_path}'. Please run preprocess.py.")
    
    # Find unique channel prefixes (e.g., 'A-1' from 'A-1_train.npy')
    # If no '_' is in the name, it means it's a single-file dataset (e.g., train.npy)
    channels = sorted(list(set([f.split('_')[0] for f in os.listdir(dataset_path) if f.endswith('.npy')])))
    is_single_file_dataset = 'train' in channels and 'test' in channels and 'labels' in channels
    if is_single_file_dataset:
        channels = [args.dataset]
        
    original_dataset_name = args.dataset
    
    # 2. Loop through each channel and train/evaluate a model
    for channel in channels:
        print(f'{color.BOLD}{color.BLUE}Starting training and evaluation for: {original_dataset_name} -> {channel}{color.ENDC}')
        
        # 2.1. Load data for the current channel
        train_data, test_data, labels = load_channel_data(dataset_path, channel, is_single_file_dataset)
        if labels is None: continue

        # 2.2. Set unique name for model/results for this channel and load model
        if not is_single_file_dataset:
            args.dataset = f'{original_dataset_name}_{channel}'
        
        model, optimizer, scheduler, epoch, accuracy_list = load_model(args.model, labels.shape[1])

        # MERLIN is not a neural network, handle separately
        if args.model in ['MERLIN']:
            test_loader = DataLoader(test_data, batch_size=test_data.shape[0] if test_data.size > 0 else 1)
            eval(f'run_{args.model.lower()}(test_loader, labels, args.dataset)')
            args.dataset = original_dataset_name # Restore dataset name
            continue

        # 2.3. Prepare data for the model (sliding window, etc.)
        trainD, testD, trainO, testO = prepare_data_for_model(train_data, test_data, model)

        # 2.4. Training phase
        if not args.test:
            print(f'{color.HEADER}Training {args.model} on {args.dataset}{color.ENDC}')
            num_epochs = 10; e = epoch + 1; start = time()
            for e in tqdm(list(range(epoch+1, epoch+num_epochs+1))):
                lossT, lr = backprop(e, model, trainD, trainO, optimizer, scheduler)
                accuracy_list.append((lossT, lr))
            print(color.BOLD+'Training time: '+"{:10.4f}".format(time()-start)+' s'+color.ENDC)
            save_model(model, optimizer, scheduler, e, accuracy_list)
            plot_accuracies(accuracy_list, f'{args.model}_{args.dataset}')

        # 2.5. Testing phase
        torch.zero_grad = True
        model.eval()
        print(f'{color.HEADER}Testing {args.model} on {args.dataset}{color.ENDC}')
        loss, y_pred = backprop(0, model, testD, testO, optimizer, scheduler, training=False)

        # 2.6. Visualization
        if not args.test:
            if 'TranAD' in model.name: testO = torch.roll(testO, 1, 0) 
            plotter(f'{args.model}_{args.dataset}', testO, y_pred, loss, labels)

        # 2.7. Performance evaluation
        df = pd.DataFrame()
        lossT, _ = backprop(0, model, trainD, trainO, optimizer, scheduler, training=False)
        for i in range(loss.shape[1]):
            lt, l, ls = lossT[:, i], loss[:, i], labels[:, i]
            result, pred = pot_eval(lt, l, ls); preds.append(pred)
            df = pd.concat([df, pd.DataFrame([result])], ignore_index=True)
        
        lossTfinal, lossFinal = np.mean(lossT, axis=1), np.mean(loss, axis=1)
        labelsFinal = (np.sum(labels, axis=1) >= 1) + 0
        result, _ = pot_eval(lossTfinal, lossFinal, labelsFinal)
        result.update(hit_att(loss, labels))
        result.update(ndcg(loss, labels))
        print(f"Results for {args.dataset}:")
        print(df)
        pprint(result)

        # Restore original dataset name for the next loop iteration
        args.dataset = original_dataset_name