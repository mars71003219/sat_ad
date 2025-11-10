# -*- coding: utf-8 -*-
"""
이 스크립트는 모델의 예측 결과와 이상 점수를 시각화하는 유틸리티 함수를 포함합니다.

주요 기능:
- `smooth`: 이동 평균을 사용하여 데이터를 부드럽게 만드는 함수.
- `plotter`: 각 차원(feature)에 대해 실제 값, 예측 값, 이상 점수, 실제 레이블을
             하나의 그래프로 그려 다중 페이지 PDF 파일로 저장합니다.
"""
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import statistics
import os, torch
import numpy as np

# Matplotlib 스타일 및 설정
plt.style.use(['science', 'ieee'])
plt.rcParams["text.usetex"] = False
plt.rcParams['figure.figsize'] = 6, 2

# 'plots' 디렉토리가 없으면 생성
os.makedirs('plots', exist_ok=True)

def smooth(y, box_pts=1):
    """
    이동 평균을 사용하여 1D 배열을 부드럽게 만듭니다.

    Args:
        y (np.ndarray): 부드럽게 만들 1D 배열.
        box_pts (int, optional): 이동 평균 윈도우의 크기. Defaults to 1.

    Returns:
        np.ndarray: 부드러워진 배열.
    """
    box = np.ones(box_pts)/box_pts
    y_smooth = np.convolve(y, box, mode='same')
    return y_smooth

def plotter(name, y_true, y_pred, ascore, labels):
	"""
	결과를 시각화하고 PDF 파일로 저장합니다.

	각 차원에 대해 실제 값, 예측 값, 이상 점수, 실제 레이블을 포함하는
	그래프를 생성하여 하나의 PDF 파일에 페이지별로 저장합니다.

	Args:
		name (str): 플롯을 저장할 폴더 및 파일 이름의 접두사.
		y_true (np.ndarray): 실제 시계열 데이터.
		y_pred (np.ndarray): 모델이 예측한 시계열 데이터.
		ascore (np.ndarray): 모델이 계산한 이상 점수.
		labels (np.ndarray): 실제 이상 레이블.
	"""
	if 'TranAD' in name: y_true = torch.roll(y_true, 1, 0)
	os.makedirs(os.path.join('plots', name), exist_ok=True)
	pdf = PdfPages(f'plots/{name}/output.pdf')
	for dim in range(y_true.shape[1]):
		y_t, y_p, l, a_s = y_true[:, dim], y_pred[:, dim], labels[:, dim], ascore[:, dim]
		fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
		ax1.set_ylabel('Value')
		ax1.set_title(f'Dimension = {dim}')
		# if dim == 0: np.save(f'true{dim}.npy', y_t); np.save(f'pred{dim}.npy', y_p); np.save(f'ascore{dim}.npy', a_s)
		ax1.plot(smooth(y_t), linewidth=0.2, label='True')
		ax1.plot(smooth(y_p), '-', alpha=0.6, linewidth=0.3, label='Predicted')
		ax3 = ax1.twinx()
		ax3.plot(l, '--', linewidth=0.3, alpha=0.5)
		ax3.fill_between(np.arange(l.shape[0]), l, color='blue', alpha=0.3)
		if dim == 0: ax1.legend(ncol=2, bbox_to_anchor=(0.6, 1.02))
		ax2.plot(smooth(a_s), linewidth=0.2, color='g')
		ax2.set_xlabel('Timestamp')
		ax2.set_ylabel('Anomaly Score')
		pdf.savefig(fig)
		plt.close()
	pdf.close()