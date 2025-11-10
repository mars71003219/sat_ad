# -*- coding: utf-8 -*-
"""
이 스크립트는 "MERLIN: Parameter-Free Discovery of Arbitrary Length Anomalies in
Massive Time Series Archives" (ICDM 2020) 논문에서 제안된 MERLIN 알고리즘을 구현합니다.

MERLIN은 대규모 시계열 데이터에서 파라미터 없이 임의 길이의 이상을 발견하는 알고리즘입니다.
주요 함수는 다음과 같습니다:
- csa: 후보 선택 알고리즘 (Candidate Selection Algorithm)
- drag: 불협화음 정제 알고리즘 (Discords Refinement Algorithm)
- merlin: CSA와 DRAG를 사용하여 최적의 이상 시퀀스를 찾는 메인 알고리즘.
- run_merlin: 데이터셋에 대해 MERLIN 알고리즘을 실행하고 평가합니다.
"""
# Replicated from the following paper:
# Nakamura, T., Imamura, M., Mercer, R. and Keogh, E., 2020, November. 
# MERLIN: Parameter-Free Discovery of Arbitrary Length Anomalies in Massive 
# Time Series Archives. In 2020 IEEE International Conference on Data Mining (ICDM) 
# (pp. 1190-1195). IEEE.

import numpy as np
from pprint import pprint
from time import time
from src.utils import *
from src.constants import *
from src.diagnosis import *
from src.pot import *
maxint = 200000

def dist(t, q):
	"""
	두 시퀀스 t와 q 사이의 Z-정규화된 유클리드 거리를 계산합니다.
	현재 구현은 평균 제곱 오차의 제곱근(유클리드 거리)을 사용합니다.
	"""
	m = q.shape[0]
	# t, q = t.reshape(-1), q.reshape(-1)
	# znorm2 = 2 * m * (1 - (np.dot(q, t) - m * np.mean(q) * np.mean(t)) / (m * np.std(q) * np.std(t)))
	znorm2 = np.mean((t - q) ** 2)
	return np.sqrt(znorm2)

def getsub(t, L, i):
	"""시계열 t에서 인덱스 i부터 시작하는 길이 L의 하위 시퀀스를 추출합니다."""
	return t[i:i+L]

def csa(t, L, r):
	"""
	후보 선택 알고리즘 (Candidate Selection Algorithm).
	거리 r을 기준으로 후보 이상(discord) 시퀀스 집합을 찾습니다.
	"""
	C = []
	for i in range(1, t.shape[0] - L + 1):
		iscandidate = True
		for j in C:
			if i != j:
				if dist(getsub(t, L, i), getsub(t, L, j)) < r:
					C.remove(j)
					iscandidate = False
		if iscandidate and i not in C:
			C.append(i)
	if C:
		return C
	else:
		return []

def check(t, pred):
	"""
	예측된 이상 구간을 기반으로 레이블을 확인하고 조정하는 함수.
	이동 평균과의 차이를 기반으로 이상 점수를 계산하고 백분위수를 사용하여 레이블을 생성합니다.
	"""
	labels = [];
	for i in range(t.shape[1]):
		new = np.convolve(t[:, i], np.ones(cvp)/cvp, mode='same')
		scores = np.abs(new - t[:,i])
		labels.append((scores > np.percentile(scores, percentile_merlin)) + 0)
	labels = np.array(labels).transpose()
	return (np.sum(labels, axis=1) >= 1) + 0, labels

def drag(C, t, L, r):
	"""
	불협화음 정제 알고리즘 (Discords Refinement Algorithm).
	CSA에서 찾은 후보 집합 C를 정제하여 실제 이상(discord)을 찾습니다.
	"""
	D = [];
	if not C: return []
	for i in range(1, t.shape[0] - L + 1):
		isdiscord = True 
		dj = maxint
		for j in C:
			if i != j:
				d = dist(getsub(t, L, i), getsub(t, L, j))
				if d < r:
					C.remove(j)
					isdiscord = False
				else:
					dj = min(dj, d)
		if isdiscord:
			D.append((i, L, dj))
	return D

def merlin(t, minL, maxL):
	"""
	MERLIN 알고리즘의 메인 함수.
	주어진 최소/최대 길이 범위 내에서 최적의 이상 시퀀스를 탐색합니다.
	"""
	r = 2 * np.sqrt(minL)
	dminL = - maxint; DFinal = []
	while dminL < 0:
		C = csa(t, minL, r)
		D = drag(C, t, minL, r)
		r = r / 2
		if D: break
	rstart = r
	distances = [-maxint] * 4
	print('phase 1')
	for i in range(minL, min(minL+4, maxL)):
		di = distances[i - minL]
		dim1 = rstart if i == minL else distances[i - minL - 1]
		r = 0.99 * dim1
		while di < 0:
			C = csa(t, i, r)
			D = drag(C, t, i, r)
			if D: 
				di = np.max([p[2] for p in D])
				distances[i - minL] = di
				DFinal += D
			r = r * 0.99
		print(i, r)
	print('phase 2')
	for i in range(minL + 4, maxL + 1):
		M = np.mean(distances)
		S = np.std(distances) + 1e-2
		r = M - 2 * S
		di = - maxint
		for _ in range(1000):
			C = csa(t, i, r)
			D = drag(C, t, i, r)
			if D: 
				di = np.max([p[2] for p in D])
				DFinal += D
				if di > 0:	break
			r = r - S
	vals = []
	for p in DFinal: 
		if p[2] != maxint: vals.append(p[2])
	dmin = np.argmax(vals)
	return DFinal[dmin], DFinal

def get_result(pred, labels):
	"""평가 결과를 딕셔너리 형태로 포맷팅합니다."""
	p_t = calc_point2point(pred, labels)
	result = {
        'f1': p_t[0],
        'precision': p_t[1],
        'recall': p_t[2],
        'TP': p_t[3],
        'TN': p_t[4],
        'FP': p_t[5],
        'FN': p_t[6],
        'ROC/AUC': p_t[7],
    }
	return result

def run_merlin(test, labels, dset):
	"""
	주어진 데이터셋에 대해 MERLIN 알고리즘을 실행하고 성능을 평가합니다.
	"""
	t = next(iter(test)).detach().numpy(); labelsAll = labels
	labels = (np.sum(labels, axis=1) >= 1) + 0
	lsum = np.sum(labels)
	start = time()
	pred = np.zeros_like(labels)
	d, _ = merlin(t, 60, 62) #
	print('Result:', d) #
	pred[d[0]:d[0]+d[1]] = 1; #
	pred, predAll = check(t, pred)
	print(t.shape, pred.shape, labels.shape)
	result = get_result(pred, labels)
	if dset in ['SMD', 'MSDS']:
		result.update(hit_att(predAll, labelsAll))
		result.update(ndcg(predAll, labelsAll))
	pprint(result); 
	print(color.BOLD+'Training time: '+"{:10.4f}".format(time()-start)+' s'+color.ENDC)
	exit()

if __name__ == '__main__':
	# 간단한 테스트 케이스 (2번 라인을 주석 처리하고 'python3 src/merlin.py' 실행)
	a = np.random.normal(size=(100, 1))
	a[10:13][:] = 100
	d, D = merlin(a, 1, 10)		
	print(D); print(d)