# -*- coding: utf-8 -*-
"""
이 스크립트는 이상 진단 및 모델 평가를 위한 함수들을 포함하고 있습니다.

주요 기능:
- Hit@p%: 상위 p% 예측에서 실제 이상을 얼마나 잘 감지하는지 측정하는 메트릭을 계산합니다.
- NDCG@p%: 순위 기반 평가 메트릭인 정규화된 할인 누적 이득(NDCG)을 계산하여
           모델이 이상 징후의 순위를 얼마나 잘 매기는지 평가합니다.
"""
import numpy as np
from sklearn.metrics import ndcg_score
from src.constants import lm

def hit_att(ascore, labels, ps = [100, 150]):
	"""
	Hit@p% 메트릭을 계산합니다.

	이 메트릭은 상위 p%의 이상 점수 예측이 실제 이상을 얼마나 포함하는지를 평가합니다.

	Args:
		ascore (np.ndarray): 모델이 예측한 이상 점수 배열.
		labels (np.ndarray): 실제 이상 레이블 배열.
		ps (list, optional): 평가할 백분위수 리스트. Defaults to [100, 150].

	Returns:
		dict: 각 p%에 대한 평균 Hit 점수를 담은 딕셔너리.
	"""
	res = {}
	for p in ps:
		hit_score = []
		for i in range(ascore.shape[0]):
			a, l = ascore[i], labels[i]
			a, l = np.argsort(a).tolist()[::-1], set(np.where(l == 1)[0])
			if l:
				size = round(p * len(l) / 100)
				a_p = set(a[:size])
				intersect = a_p.intersection(l)
				hit = len(intersect) / len(l)
				hit_score.append(hit)
		res[f'Hit@{p}%'] = np.mean(hit_score)
	return res

def ndcg(ascore, labels, ps = [100, 150]):
	"""
	NDCG@p% (정규화된 할인 누적 이득) 메트릭을 계산합니다.

	이 메트릭은 모델이 예측한 이상 점수의 순위 품질을 평가합니다.

	Args:
		ascore (np.ndarray): 모델이 예측한 이상 점수 배열.
		labels (np.ndarray): 실제 이상 레이블 배열.
		ps (list, optional): 평가할 백분위수 리스트. Defaults to [100, 150].

	Returns:
		dict: 각 p%에 대한 평균 NDCG 점수를 담은 딕셔너리.
	"""
	res = {}
	for p in ps:
		ndcg_scores = []
		for i in range(ascore.shape[0]):
			a, l = ascore[i], labels[i]
			labs = list(np.where(l == 1)[0])
			if labs:
				k_p = round(p * len(labs) / 100)
				try:
					hit = ndcg_score(l.reshape(1, -1), a.reshape(1, -1), k = k_p)
				except Exception as e:
					return {}
				ndcg_scores.append(hit)
		res[f'NDCG@{p}%'] = np.mean(ndcg_scores)
	return res