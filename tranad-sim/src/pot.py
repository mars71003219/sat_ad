# -*- coding: utf-8 -*-
"""
이 스크립트는 POT(Peaks-Over-Threshold) 통계적 방법을 사용하여 이상 점수를 평가하고
최적의 임계값을 찾는 함수들을 구현합니다.

주요 기능:
- `calc_point2point`: 예측과 실제 레이블을 기반으로 F1 점수, 정밀도, 재현율 등 포인트별 평가 메트릭을 계산합니다.
- `adjust_predicts`: 시계열 이상 탐지 평가를 위한 예측 레이블 조정 기법을 구현합니다.
                     (OmniAnomaly 코드베이스에서 가져옴)
- `bf_search`: 다양한 임계값을 시도하여 최상의 F1 점수를 찾는 브루트포스 탐색을 수행합니다.
- `pot_eval`: POT(Peaks-Over-Threshold) 방법을 사용하여 이상 점수에 대한 임계값을 설정하고,
              이를 기반으로 모델의 성능을 평가합니다.
"""
import numpy as np

from src.spot import SPOT
from src.constants import *
from sklearn.metrics import *

def calc_point2point(predict, actual):
    """
    예측값과 실제값을 기반으로 포인트별 F1 점수를 계산합니다.

    Args:
        predict (np.ndarray): 예측된 레이블 배열.
        actual (np.ndarray): 실제 레이블 배열.
    
    Returns:
        tuple: f1, precision, recall, TP, TN, FP, FN, roc_auc 점수를 포함하는 튜플.
    """
    TP = np.sum(predict * actual)
    TN = np.sum((1 - predict) * (1 - actual))
    FP = np.sum(predict * (1 - actual))
    FN = np.sum((1 - predict) * actual)
    precision = TP / (TP + FP + 0.00001)
    recall = TP / (TP + FN + 0.00001)
    f1 = 2 * precision * recall / (precision + recall + 0.00001)
    try:
        roc_auc = roc_auc_score(actual, predict)
    except:
        roc_auc = 0
    return f1, precision, recall, TP, TN, FP, FN, roc_auc


# 아래 함수는 OmniAnomaly 코드베이스에서 직접 가져온 것입니다.
def adjust_predicts(score, label,
                    threshold=None,
                    pred=None,
                    calc_latency=False):
    """
    주어진 `score`, `threshold` (또는 `pred`) 및 `label`을 사용하여 조정된 예측 레이블을 계산합니다.
    실제 이상 구간 내에서 첫 탐지 이후의 모든 포인트를 탐지된 것으로 간주하여 조정합니다.

    Args:
        score (np.ndarray): 이상 점수.
        label (np.ndarray): 실제 레이블.
        threshold (float): 이상 점수의 임계값.
        pred (np.ndarray or None): None이 아니면 `score`와 `threshold`를 무시하고 `pred`를 조정합니다.
        calc_latency (bool): 지연 시간을 계산할지 여부.

    Returns:
        np.ndarray: 조정된 예측 레이블.
    """
    if len(score) != len(label):
        raise ValueError("score and label must have the same length")
    score = np.asarray(score)
    label = np.asarray(label)
    latency = 0
    if pred is None:
        predict = score > threshold
    else:
        predict = pred
    actual = label > 0.1
    anomaly_state = False
    anomaly_count = 0
    for i in range(len(score)):
        if actual[i] and predict[i] and not anomaly_state:
                anomaly_state = True
                anomaly_count += 1
                for j in range(i, 0, -1):
                    if not actual[j]:
                        break
                    else:
                        if not predict[j]:
                            predict[j] = True
                            latency += 1
        elif not actual[i]:
            anomaly_state = False
        if anomaly_state:
            predict[i] = True
    if calc_latency:
        return predict, latency / (anomaly_count + 1e-4)
    else:
        return predict


def calc_seq(score, label, threshold, calc_latency=False):
    """
    점수 시퀀스에 대한 f1 점수를 계산합니다.
    """
    if calc_latency:
        predict, latency = adjust_predicts(score, label, threshold, calc_latency=calc_latency)
        t = list(calc_point2point(predict, label))
        t.append(latency)
        return t
    else:
        predict = adjust_predicts(score, label, threshold, calc_latency=calc_latency)
        return calc_point2point(predict, label)


def bf_search(score, label, start, end=None, step_num=1, display_freq=1, verbose=True):
    """
    [`start`, `end`) 범위에서 최적의 `threshold`를 탐색하여 최고의 F1 점수를 찾습니다.

    Returns:
        list: 결과 리스트.
        float: 최고의 F1 점수를 위한 `threshold`.
    """
    if step_num is None or end is None:
        end = start
        step_num = 1
    search_step, search_range, search_lower_bound = step_num, end - start, start
    if verbose:
        print("search range: ", search_lower_bound, search_lower_bound + search_range)
    threshold = search_lower_bound
    m = (-1., -1., -1.)
    m_t = 0.0
    for i in range(search_step):
        threshold += search_range / float(search_step)
        target = calc_seq(score, label, threshold, calc_latency=True)
        if target[0] > m[0]:
            m_t = threshold
            m = target
        if verbose and i % display_freq == 0:
            print("cur thr: ", threshold, target, m, m_t)
    print(m, m_t)
    return m, m_t


def pot_eval(init_score, score, label, q=1e-5, level=0.02):
    """
    주어진 점수에 대해 POT(Peaks-Over-Threshold) 방법을 실행합니다.

    Args:
        init_score (np.ndarray): 초기 임계값을 얻기 위한 데이터 (훈련 세트의 이상 점수).
        score (np.ndarray): POT 방법을 실행할 데이터 (테스트 세트의 이상 점수).
        label (np.ndarray): 실제 레이블.
        q (float): 탐지 수준 (위험).
        level (float): 초기 임계값과 관련된 확률.

    Returns:
        dict: POT 결과 딕셔너리.
    """
    lms = lm[0]
    while True:
        try:
            s = SPOT(q)  # SPOT 객체
            s.fit(init_score, score)  # 데이터 가져오기
            s.initialize(level=lms, min_extrema=False, verbose=False)  # 초기화 단계
        except: lms = lms * 0.999
        else: break
    ret = s.run(dynamic=False)  # 실행
    # print(len(ret['alarms']))
    # print(len(ret['thresholds']))
    pot_th = np.mean(ret['thresholds']) * lm[1]
    # pot_th = np.percentile(score, 100 * lm[0])
    # np.percentile(score, 100 * lm[0])
    pred, p_latency = adjust_predicts(score, label, pot_th, calc_latency=True)
    # DEBUG - np.save(f'{debug}.npy', np.array(pred))
    # DEBUG - print(np.argwhere(np.array(pred)))
    p_t = calc_point2point(pred, label)
    # print('POT result: ', p_t, pot_th, p_latency)
    return {
        'f1': p_t[0],
        'precision': p_t[1],
        'recall': p_t[2],
        'TP': p_t[3],
        'TN': p_t[4],
        'FP': p_t[5],
        'FN': p_t[6],
        'ROC/AUC': p_t[7],
        'threshold': pot_th,
        # 'pot-latency': p_latency
    }, np.array(pred)