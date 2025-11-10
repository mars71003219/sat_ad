# -*- coding: utf-8 -*-
"""
이 스크립트는 프로그램 실행 시 사용될 명령줄 인수를 파싱하는 역할을 합니다.

`argparse` 모듈을 사용하여 다음과 같은 인수를 정의하고 처리합니다:
- --dataset: 사용할 데이터셋 지정 (기본값: 'synthetic').
- --model: 사용할 모델 아키텍처 지정.
- --test: 모델을 테스트 모드로만 실행할지 여부.
- --retrain: 기존에 저장된 모델이 있어도 강제로 재학습할지 여부.
- --less: 더 적은 양의 데이터로 학습할지 여부.

파싱된 인수는 'args' 객체에 저장되어 프로젝트의 다른 모듈에서 사용됩니다.
"""
import argparse

# ArgumentParser 객체 생성
parser = argparse.ArgumentParser(description='Time-Series Anomaly Detection')

# 데이터셋 인자 추가
parser.add_argument('--dataset', 
					metavar='-d', 
					type=str, 
					required=False,
					default='synthetic',
                    help="dataset from ['synthetic', 'SMD']")

# 모델 이름 인자 추가
parser.add_argument('--model', 
					metavar='-m', 
					type=str, 
					required=False,
					default='LSTM_Multivariate',
                    help="model name")

# 테스트 모드 플래그 추가
parser.add_argument('--test', 
					action='store_true', 
					help="test the model")

# 재학습 플래그 추가
parser.add_argument('--retrain', 
					action='store_true', 
					help="retrain the model")

# 적은 데이터 사용 플래그 추가
parser.add_argument('--less', 
					action='store_true', 
					help="train using less data")

# 명령줄 인수 파싱
args = parser.parse_args()
