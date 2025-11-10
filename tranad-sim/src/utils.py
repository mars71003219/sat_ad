# -*- coding: utf-8 -*-
"""
이 스크립트는 프로젝트 전반에서 사용되는 다양한 유틸리티 함수와 클래스를 제공합니다.

포함된 내용:
- color 클래스: 터미널 출력에 색상을 추가하여 가독성을 높입니다.
- plot_accuracies: 훈련 과정에서의 손실 및 학습률 변화를 시각화하고 PDF 파일로 저장합니다.
- cut_array: 데이터셋의 일부만 사용하도록 배열을 자르는 함수입니다.
- getresults2: 평가 결과 DataFrame을 요약하고 집계하는 함수입니다.
"""
import matplotlib.pyplot as plt
import os
from src.constants import *
import pandas as pd 
import numpy as np

class color:
    """터미널 출력에 사용할 색상 코드 정의."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    RED = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def plot_accuracies(accuracy_list, folder):
	"""
	훈련 손실과 학습률을 epoch에 따라 플롯하고 PDF로 저장합니다.

	Args:
		accuracy_list (list): (손실, 학습률) 튜플의 리스트.
		folder (str): 플롯을 저장할 폴더 이름.
	"""
	os.makedirs(f'plots/{folder}/', exist_ok=True)
	trainAcc = [i[0] for i in accuracy_list]
	lrs = [i[1] for i in accuracy_list]
	plt.xlabel('Epochs')
	plt.ylabel('Average Training Loss')
	plt.plot(range(len(trainAcc)), trainAcc, label='Average Training Loss', linewidth=1, linestyle='-', marker='.')
	plt.twinx()
	plt.plot(range(len(lrs)), lrs, label='Learning Rate', color='r', linewidth=1, linestyle='--', marker='.')
	plt.savefig(f'plots/{folder}/training-graph.pdf')
	plt.clf()

def cut_array(percentage, arr):
	"""
	배열의 중앙에서 지정된 비율만큼의 데이터를 잘라냅니다.

	Args:
		percentage (float): 잘라낼 데이터의 비율 (0.0에서 1.0 사이).
		arr (np.ndarray): 원본 배열.

	Returns:
		np.ndarray: 잘라낸 배열.
	"""
	print(f'{color.BOLD}Slicing dataset to {int(percentage*100)}%{color.ENDC}')
	mid = round(arr.shape[0] / 2)
	window = round(arr.shape[0] * percentage * 0.5)
	return arr[mid - window : mid + window, :]

def getresults2(df, result):
	"""
	결과 DataFrame을 집계하여 요약된 결과를 생성합니다.

	Args:
		df (pd.DataFrame): 개별 차원 또는 평가의 결과가 담긴 DataFrame.
		result (dict): 기존 결과 딕셔너리.

	Returns:
		dict: 집계된 결과가 추가된 딕셔너리.
	"""
	results2, df1, df2 = {}, df.sum(), df.mean()
	for a in ['FN', 'FP', 'TP', 'TN']:
		results2[a] = df1[a]
	for a in ['precision', 'recall']:
		results2[a] = df2[a]
	results2['f1*'] = 2 * results2['precision'] * results2['recall'] / (results2['precision'] + results2['recall'])
	return results2
