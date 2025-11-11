# -*- coding: utf-8 -*-
"""
이 스크립트는 모델 훈련 및 평가에 사용되는 전역 상수와 하이퍼파라미터를 정의합니다.

포함된 내용:
- 명령줄 인수 파싱 (`parser.py`에서 가져옴).
- 데이터셋별 임계값 파라미터 (`lm_d`).
- 데이터셋별 학습률 (`lr_d`).
- MERLIN 알고리즘 및 기타 디버깅을 위한 백분위수 값.
"""
from src.parser import *
from src.folderconstants import *

# Threshold parameters
# 데이터셋 및 모델에 따른 임계값 파라미터
# lm_d는 각 데이터셋에 대해 두 개의 튜플을 가집니다.
# 첫 번째 튜플은 일반 모델용, 두 번째 튜플은 'TranAD' 모델용입니다.
lm_d = {
		'SMD': [(0.99995, 1.04), (0.99995, 1.06)],
		'synthetic': [(0.999, 1), (0.999, 1)],
		'SWaT': [(0.993, 1), (0.993, 1)],
		'UCR': [(0.993, 1), (0.99935, 1)],
		'NAB': [(0.991, 1), (0.99, 1)],
		'SMAP': [(0.98, 1), (0.98, 1)],
		'MSL': [(0.97, 1), (0.999, 1.04)],
		'WADI': [(0.99, 1), (0.999, 1)],
		'MSDS': [(0.91, 1), (0.9, 1.04)],
		'MBA': [(0.87, 1), (0.93, 1.04)],
	}
# 현재 모델이 'TranAD'인지 여부에 따라 적절한 임계값 튜플을 선택합니다.
lm = lm_d[args.dataset][1 if 'TranAD' in args.model else 0]

# Hyperparameters
# 데이터셋별 학습률
lr_d = {
		'SMD': 0.0001, 
		'synthetic': 0.0001, 
		'SWaT': 0.008, 
		'SMAP': 0.001, 
		'MSL': 0.002, 
		'WADI': 0.0001, 
		'MSDS': 0.001, 
		'UCR': 0.006, 
		'NAB': 0.009, 
		'MBA': 0.001, 
	}
# 현재 데이터셋에 맞는 학습률을 선택합니다.
lr = lr_d[args.dataset]

# Debugging
# 디버깅 및 평가를 위한 데이터셋별 백분위수 파라미터
percentiles = {
		'SMD': (98, 2000),
		'synthetic': (95, 10),
		'SWaT': (95, 10),
		'SMAP': (97, 5000),
		'MSL': (97, 150),
		'WADI': (99, 1200),
		'MSDS': (96, 30),
		'UCR': (98, 2),
		'NAB': (98, 2),
		'MBA': (99, 2),
	}
# MERLIN 알고리즘에 사용될 백분위수
percentile_merlin = percentiles[args.dataset][0]
# 컨볼루션에 사용될 포인트 수
cvp = percentiles[args.dataset][1]
# 예측값을 저장하기 위한 리스트
preds = []
# 디버깅용 변수
debug = 9
