# -*- coding: utf-8 -*-
"""
이 스크립트는 스트리밍 데이터에 대한 이상 탐지를 위한 SPOT(Streaming Peaks-Over-Threshold),
biSPOT, dSPOT, bidSPOT 알고리즘을 구현합니다.

이 알고리즘들은 극단값 이론(Extreme Value Theory)에 기반하며, 특히 POT(Peaks-Over-Threshold)
접근법을 스트리밍 환경에 적용한 것입니다.

- SPOT: 단변량 데이터 스트림의 상위 임계값을 초과하는 이상을 탐지합니다.
- biSPOT: 상위 및 하위 양방향 임계값을 모두 처리하여 이상을 탐지합니다.
- dSPOT: 데이터의 드리프트(drift)를 고려하여 이동 평균과의 차이를 기반으로 이상을 탐지합니다.
- bidSPOT: 양방향 탐지와 드리프트 처리를 결합한 알고리즘입니다.

각 클래스는 데이터 스트림을 처리하고, 동적으로 임계값을 조정하며, 이상 징후를 식별하는
메서드를 제공합니다.
"""
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 12 10:08:16 2016

@author: Alban Siffer 
@company: Amossys
@license: GNU GPLv3
"""

from math import log, floor

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tqdm
from scipy.optimize import minimize

# plot을 위한 색상
deep_saffron = '#FF9933'
air_force_blue = '#5D8AA8'

"""
================================= MAIN CLASS ==================================
"""


class SPOT:
    """
    이 클래스는 단변량 데이터셋(상한)에 대해 SPOT 알고리즘을 실행할 수 있게 합니다.
    
    Attributes
    ----------
    proba : float
        사용자가 선택한 탐지 수준(위험도).
        
    extreme_quantile : float
        현재 임계값 (정상 이벤트와 비정상 이벤트를 구분하는 경계).
        
    data : numpy.array
        스트림 데이터.
    
    init_data : numpy.array
        초기 보정 단계용 관측치 배치.
    
    init_threshold : float
        보정 단계에서 계산된 초기 임계값.
    
    peaks : numpy.array
        초기 임계값을 초과하는 피크(excesses) 배열.
    
    n : int
        관측된 값의 수.
    
    Nt : int
        관측된 피크의 수.
    """

    def __init__(self, q=1e-4):
        """
        생성자

        Args:
            q (float): 탐지 수준 (위험도).
    
        Returns:
            SPOT 객체.
        """
        self.proba = q
        self.extreme_quantile = None
        self.data = None
        self.init_data = None
        self.init_threshold = None
        self.peaks = None
        self.n = 0
        self.Nt = 0

    def __str__(self):
        s = ''
        s += 'Streaming Peaks-Over-Threshold Object\n'
        s += 'Detection level q = %s\n' % self.proba
        if self.data is not None:
            s += 'Data imported : Yes\n'
            s += '\t initialization  : %s values\n' % self.init_data.size
            s += '\t stream : %s values\n' % self.data.size
        else:
            s += 'Data imported : No\n'
            return s

        if self.n == 0:
            s += 'Algorithm initialized : No\n'
        else:
            s += 'Algorithm initialized : Yes\n'
            s += '\t initial threshold : %s\n' % self.init_threshold

            r = self.n - self.init_data.size
            if r > 0:
                s += 'Algorithm run : Yes\n'
                s += '\t number of observations : %s (%.2f %%)\n' % (r, 100 * r / self.n)
            else:
                s += '\t number of peaks  : %s\n' % self.Nt
                s += '\t extreme quantile : %s\n' % self.extreme_quantile
                s += 'Algorithm run : No\n'
        return s

    def fit(self, init_data, data):
        """
        SPOT 객체에 데이터를 가져옵니다.
        
        Args:
            init_data (list, numpy.array or pandas.Series): 알고리즘 보정을 위한 초기 배치.
            data (numpy.array): 실행용 데이터.
        """
        if isinstance(data, list):
            self.data = np.array(data)
        elif isinstance(data, np.ndarray):
            self.data = data
        elif isinstance(data, pd.Series):
            self.data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        if isinstance(init_data, list):
            self.init_data = np.array(init_data)
        elif isinstance(init_data, np.ndarray):
            self.init_data = init_data
        elif isinstance(init_data, pd.Series):
            self.init_data = init_data.values
        elif isinstance(init_data, int):
            self.init_data = self.data[:init_data]
            self.data = self.data[init_data:]
        elif isinstance(init_data, float) & (init_data < 1) & (init_data > 0):
            r = int(init_data * data.size)
            self.init_data = self.data[:r]
            self.data = self.data[r:]
        else:
            print('The initial data cannot be set')
            return

    def add(self, data):
        """
        이미 적합된 데이터에 데이터를 추가합니다.
        
        Args:
            data (list, numpy.array, pandas.Series): 추가할 데이터.
        """
        if isinstance(data, list):
            data = np.array(data)
        elif isinstance(data, np.ndarray):
            data = data
        elif isinstance(data, pd.Series):
            data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        self.data = np.append(self.data, data)
        return

    def initialize(self, level=0.98, min_extrema=False, verbose=True):
        """
        보정(초기화) 단계를 실행합니다.
        
        Args:
            level (float): 초기 임계값 t와 관련된 확률 (기본값 0.98).
            verbose (bool): True이면 배치 초기화에 대한 세부 정보를 제공합니다 (기본값 True).
            min_extrema (bool): True이면 최대 극값 대신 최소 극값을 찾습니다 (기본값 False).
        """
        if min_extrema:
            self.init_data = -self.init_data
            self.data = -self.data
            level = 1 - level

        level = level - floor(level)

        n_init = self.init_data.size

        S = np.sort(self.init_data)  # 경험적 분위수를 얻기 위해 X를 정렬
        self.init_threshold = S[int(level * n_init)]  # t는 전체 알고리즘에 대해 고정

        # 초기 피크
        self.peaks = self.init_data[self.init_data > self.init_threshold] - self.init_threshold
        self.Nt = self.peaks.size
        self.n = n_init

        if verbose:
            print('Initial threshold : %s' % self.init_threshold)
            print('Number of peaks : %s' % self.Nt)
            print('Grimshaw maximum log-likelihood estimation ... ', end='')

        g, s, l = self._grimshaw()
        self.extreme_quantile = self._quantile(g, s)

        if verbose:
            print('[done]')
            print('\t' + chr(0x03B3) + ' = ' + str(g))
            print('\t' + chr(0x03C3) + ' = ' + str(s))
            print('\tL = ' + str(l))
            print('Extreme quantile (probability = %s): %s' % (self.proba, self.extreme_quantile))

        return

    def _rootsFinder(fun, jac, bounds, npoints, method):
        """
        스칼라 함수의 가능한 근을 찾습니다.
        """
        if method == 'regular':
            step = (bounds[1] - bounds[0]) / (npoints + 1)
            ## Bug fix - Shreshth Tuli
            if step == 0: bounds, step = (0, 1e-4), 1e-5
            X0 = np.arange(bounds[0] + step, bounds[1], step)
        elif method == 'random':
            X0 = np.random.uniform(bounds[0], bounds[1], npoints)

        def objFun(X, f, jac):
            g = 0
            j = np.zeros(X.shape)
            i = 0
            for x in X:
                fx = f(x)
                g = g + fx ** 2
                j[i] = 2 * fx * jac(x)
                i = i + 1
            return g, j

        opt = minimize(lambda X: objFun(X, fun, jac), X0,
                       method='L-BFGS-B',
                       jac=True, bounds=[bounds] * len(X0))

        X = opt.x
        np.round(X, decimals=5)
        return np.unique(X)

    def _log_likelihood(Y, gamma, sigma):
        """
        일반화 파레토 분포(GPD, μ=0)에 대한 로그 우도를 계산합니다.
        """
        n = Y.size
        if gamma != 0:
            tau = gamma / sigma
            L = -n * log(sigma) - (1 + (1 / gamma)) * (np.log(1 + tau * Y)).sum()
        else:
            L = n * (1 + log(Y.mean()))
        return L

    def _grimshaw(self, epsilon=1e-8, n_points=10):
        """
        Grimshaw의 트릭을 사용하여 GPD 파라미터 추정치를 계산합니다.
        """

        def u(s):
            return 1 + np.log(s).mean()

        def v(s):
            return np.mean(1 / s)

        def w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            return us * vs - 1

        def jac_w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            jac_us = (1 / t) * (1 - vs)
            jac_vs = (1 / t) * (-vs + np.mean(1 / s ** 2))
            return us * jac_vs + vs * jac_us

        Ym = self.peaks.min()
        YM = self.peaks.max()
        Ymean = self.peaks.mean()

        a = -1 / YM
        if abs(a) < 2 * epsilon:
            epsilon = abs(a) / n_points

        a = a + epsilon
        b = 2 * (Ymean - Ym) / (Ymean * Ym)
        c = 2 * (Ymean - Ym) / (Ym ** 2)

        # 가능한 근을 찾습니다.
        left_zeros = SPOT._rootsFinder(lambda t: w(self.peaks, t),
                                       lambda t: jac_w(self.peaks, t),
                                       (a + epsilon, -epsilon),
                                       n_points, 'regular')

        right_zeros = SPOT._rootsFinder(lambda t: w(self.peaks, t),
                                        lambda t: jac_w(self.peaks, t),
                                        (b, c),
                                        n_points, 'regular')

        # 모든 가능한 근
        zeros = np.concatenate((left_zeros, right_zeros))

        # 0은 항상 해이므로 그것으로 초기화합니다.
        gamma_best = 0
        sigma_best = Ymean
        ll_best = SPOT._log_likelihood(self.peaks, gamma_best, sigma_best)

        # 더 나은 후보를 찾습니다.
        for z in zeros:
            gamma = u(1 + z * self.peaks) - 1
            sigma = gamma / z
            ll = SPOT._log_likelihood(self.peaks, gamma, sigma)
            if ll > ll_best:
                gamma_best = gamma
                sigma_best = sigma
                ll_best = ll

        return gamma_best, sigma_best, ll_best

    def _quantile(self, gamma, sigma):
        """
        수준 1-q에서 분위수를 계산합니다.
        """
        r = self.n * self.proba / self.Nt
        if gamma != 0:
            return self.init_threshold + (sigma / gamma) * (pow(r, -gamma) - 1)
        else:
            return self.init_threshold - sigma * log(r)

    def run(self, with_alarm=True, dynamic=True):
        """
        스트림에 대해 SPOT을 실행합니다.
        
        Args:
            with_alarm (bool): False이면 비정상적인 값이 없다고 가정하고 임계값을 조정합니다 (기본값 True).
            dynamic (bool): True이면 임계값을 동적으로 조정합니다 (기본값 True).

        Returns:
            dict: 'thresholds'와 'alarms' 키를 포함하는 딕셔너리.
        """
        if self.n > self.init_data.size:
            print('Warning : the algorithm seems to have already been run, you \
            should initialize before running again')
            return {}

        # 임계값 리스트
        th = []
        alarm = []
        # 스트림에 대한 루프
        for i in range(self.data.size):

            if not dynamic:
                if self.data[i] > self.init_threshold and with_alarm:
                    self.extreme_quantile = self.init_threshold
                    alarm.append(i)
            else:
                # 관측된 값이 현재 임계값을 초과하는 경우 (알람 발생)
                if self.data[i] > self.extreme_quantile:
                    # 알람을 원하면 알람 리스트에 추가
                    if with_alarm:
                        alarm.append(i)
                    # 그렇지 않으면 피크에 추가
                    else:
                        self.peaks = np.append(self.peaks, self.data[i] - self.init_threshold)
                        self.Nt += 1
                        self.n += 1
                        # 그리고 임계값 업데이트

                        g, s, l = self._grimshaw()
                        self.extreme_quantile = self._quantile(g, s)

                # 값이 초기 임계값은 초과하지만 알람 임계값은 초과하지 않는 경우
                elif self.data[i] > self.init_threshold:
                    # 피크에 추가
                    self.peaks = np.append(self.peaks, self.data[i] - self.init_threshold)
                    self.Nt += 1
                    self.n += 1
                    # 그리고 임계값 업데이트

                    g, s, l = self._grimshaw()
                    self.extreme_quantile = self._quantile(g, s)
                else:
                    self.n += 1

            th.append(self.extreme_quantile)  # 임계값 기록

        return {'thresholds': th, 'alarms': alarm}

    def plot(self, run_results, with_alarm=True):
        """
        실행 결과를 플롯합니다.
        
        Args:
            run_results (dict): 'run' 메서드에서 반환된 결과.
            with_alarm (bool): True이면 알람을 플롯합니다 (기본값 True).

        Returns:
            list: 플롯 리스트.
        """
        x = range(self.data.size)
        K = run_results.keys()

        ts_fig, = plt.plot(x, self.data, color=air_force_blue)
        fig = [ts_fig]

        if 'thresholds' in K:
            th = run_results['thresholds']
            th_fig, = plt.plot(x, th, color=deep_saffron, lw=2, ls='dashed')
            fig.append(th_fig)

        if with_alarm and ('alarms' in K):
            alarm = run_results['alarms']
            al_fig = plt.scatter(alarm, self.data[alarm], color='red')
            fig.append(al_fig)

        plt.xlim((0, self.data.size))

        return fig


"""
============================ UPPER & LOWER BOUNDS =============================
"""


class biSPOT:
    """
    이 클래스는 단변량 데이터셋(상한 및 하한)에 대해 biSPOT 알고리즘을 실행할 수 있게 합니다.
    """

    def __init__(self, q=1e-4):
        """
        생성자

        Args:
            q (float): 탐지 수준 (위험도).
    
        Returns:
            biSPOT 객체.
        """
        self.proba = q
        self.data = None
        self.init_data = None
        self.n = 0
        nonedict = {'up': None, 'down': None}

        self.extreme_quantile = dict.copy(nonedict)
        self.init_threshold = dict.copy(nonedict)
        self.peaks = dict.copy(nonedict)
        self.gamma = dict.copy(nonedict)
        self.sigma = dict.copy(nonedict)
        self.Nt = {'up': 0, 'down': 0}

    def __str__(self):
        s = ''
        s += 'Streaming Peaks-Over-Threshold Object\n'
        s += 'Detection level q = %s\n' % self.proba
        if self.data is not None:
            s += 'Data imported : Yes\n'
            s += '\t initialization  : %s values\n' % self.init_data.size
            s += '\t stream : %s values\n' % self.data.size
        else:
            s += 'Data imported : No\n'
            return s

        if self.n == 0:
            s += 'Algorithm initialized : No\n'
        else:
            s += 'Algorithm initialized : Yes\n'
            s += '\t initial threshold : %s\n' % self.init_threshold

            r = self.n - self.init_data.size
            if r > 0:
                s += 'Algorithm run : Yes\n'
                s += '\t number of observations : %s (%.2f %%)\n' % (r, 100 * r / self.n)
                s += '\t triggered alarms : %s (%.2f %%)\n' % (len(self.alarm), 100 * len(self.alarm) / self.n)
            else:
                s += '\t number of peaks  : %s\n' % self.Nt
                s += '\t upper extreme quantile : %s\n' % self.extreme_quantile['up']
                s += '\t lower extreme quantile : %s\n' % self.extreme_quantile['down']
                s += 'Algorithm run : No\n'
        return s

    def fit(self, init_data, data):
        """
        biSPOT 객체에 데이터를 가져옵니다.
        """
        if isinstance(data, list):
            self.data = np.array(data)
        elif isinstance(data, np.ndarray):
            self.data = data
        elif isinstance(data, pd.Series):
            self.data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        if isinstance(init_data, list):
            self.init_data = np.array(init_data)
        elif isinstance(init_data, np.ndarray):
            self.init_data = init_data
        elif isinstance(init_data, pd.Series):
            self.init_data = init_data.values
        elif isinstance(init_data, int):
            self.init_data = self.data[:init_data]
            self.data = self.data[init_data:]
        elif isinstance(init_data, float) & (init_data < 1) & (init_data > 0):
            r = int(init_data * data.size)
            self.init_data = self.data[:r]
            self.data = self.data[r:]
        else:
            print('The initial data cannot be set')
            return

    def add(self, data):
        """
        이미 적합된 데이터에 데이터를 추가합니다.
        """
        if isinstance(data, list):
            data = np.array(data)
        elif isinstance(data, np.ndarray):
            data = data
        elif isinstance(data, pd.Series):
            data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        self.data = np.append(self.data, data)
        return

    def initialize(self, verbose=True):
        """
        보정(초기화) 단계를 실행합니다.
        """
        n_init = self.init_data.size

        S = np.sort(self.init_data)  # 경험적 분위수를 얻기 위해 X를 정렬
        self.init_threshold['up'] = S[int(0.98 * n_init)]  # t는 전체 알고리즘에 대해 고정
        self.init_threshold['down'] = S[int(0.02 * n_init)]  # t는 전체 알고리즘에 대해 고정

        # 초기 피크
        self.peaks['up'] = self.init_data[self.init_data > self.init_threshold['up']] - self.init_threshold['up']
        self.peaks['down'] = -(
                self.init_data[self.init_data < self.init_threshold['down']] - self.init_threshold['down'])
        self.Nt['up'] = self.peaks['up'].size
        self.Nt['down'] = self.peaks['down'].size
        self.n = n_init

        if verbose:
            print('Initial threshold : %s' % self.init_threshold)
            print('Number of peaks : %s' % self.Nt)
            print('Grimshaw maximum log-likelihood estimation ... ', end='')

        l = {'up': None, 'down': None}
        for side in ['up', 'down']:
            g, s, l[side] = self._grimshaw(side)
            self.extreme_quantile[side] = self._quantile(side, g, s)
            self.gamma[side] = g
            self.sigma[side] = s

        ltab = 20
        form = ('\t' + '%20s' + '%20.2f' + '%20.2f')
        if verbose:
            print('[done]')
            print('\t' + 'Parameters'.rjust(ltab) + 'Upper'.rjust(ltab) + 'Lower'.rjust(ltab))
            print('\t' + '-' * ltab * 3)
            print(form % (chr(0x03B3), self.gamma['up'], self.gamma['down']))
            print(form % (chr(0x03C3), self.sigma['up'], self.sigma['down']))
            print(form % ('likelihood', l['up'], l['down']))
            print(form % ('Extreme quantile', self.extreme_quantile['up'], self.extreme_quantile['down']))
            print('\t' + '-' * ltab * 3)
        return

    def _rootsFinder(fun, jac, bounds, npoints, method):
        """
        스칼라 함수의 가능한 근을 찾습니다.
        """
        if method == 'regular':
            step = (bounds[1] - bounds[0]) / (npoints + 1)
            X0 = np.arange(bounds[0] + step, bounds[1], step)
        elif method == 'random':
            X0 = np.random.uniform(bounds[0], bounds[1], npoints)

        def objFun(X, f, jac):
            g = 0
            j = np.zeros(X.shape)
            i = 0
            for x in X:
                fx = f(x)
                g = g + fx ** 2
                j[i] = 2 * fx * jac(x)
                i = i + 1
            return g, j

        opt = minimize(lambda X: objFun(X, fun, jac), X0,
                       method='L-BFGS-B',
                       jac=True, bounds=[bounds] * len(X0))

        X = opt.x
        np.round(X, decimals=5)
        return np.unique(X)

    def _log_likelihood(Y, gamma, sigma):
        """
        일반화 파레토 분포(GPD, μ=0)에 대한 로그 우도를 계산합니다.
        """
        n = Y.size
        if gamma != 0:
            tau = gamma / sigma
            L = -n * log(sigma) - (1 + (1 / gamma)) * (np.log(1 + tau * Y)).sum()
        else:
            L = n * (1 + log(Y.mean()))
        return L

    def _grimshaw(self, side, epsilon=1e-8, n_points=10):
        """
        Grimshaw의 트릭을 사용하여 GPD 파라미터 추정치를 계산합니다.
        """

        def u(s):
            return 1 + np.log(s).mean()

        def v(s):
            return np.mean(1 / s)

        def w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            return us * vs - 1

        def jac_w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            jac_us = (1 / t) * (1 - vs)
            jac_vs = (1 / t) * (-vs + np.mean(1 / s ** 2))
            return us * jac_vs + vs * jac_us

        Ym = self.peaks[side].min()
        YM = self.peaks[side].max()
        Ymean = self.peaks[side].mean()

        a = -1 / YM
        if abs(a) < 2 * epsilon:
            epsilon = abs(a) / n_points

        a = a + epsilon
        b = 2 * (Ymean - Ym) / (Ymean * Ym)
        c = 2 * (Ymean - Ym) / (Ym ** 2)

        # 가능한 근을 찾습니다.
        left_zeros = biSPOT._rootsFinder(lambda t: w(self.peaks[side], t),
                                         lambda t: jac_w(self.peaks[side], t),
                                         (a + epsilon, -epsilon),
                                         n_points, 'regular')

        right_zeros = biSPOT._rootsFinder(lambda t: w(self.peaks[side], t),
                                          lambda t: jac_w(self.peaks[side], t),
                                          (b, c),
                                          n_points, 'regular')

        # 모든 가능한 근
        zeros = np.concatenate((left_zeros, right_zeros))

        # 0은 항상 해이므로 그것으로 초기화합니다.
        gamma_best = 0
        sigma_best = Ymean
        ll_best = biSPOT._log_likelihood(self.peaks[side], gamma_best, sigma_best)

        # 더 나은 후보를 찾습니다.
        for z in zeros:
            gamma = u(1 + z * self.peaks[side]) - 1
            sigma = gamma / z
            ll = biSPOT._log_likelihood(self.peaks[side], gamma, sigma)
            if ll > ll_best:
                gamma_best = gamma
                sigma_best = sigma
                ll_best = ll

        return gamma_best, sigma_best, ll_best

    def _quantile(self, side, gamma, sigma):
        """
        주어진 측면에 대해 수준 1-q에서 분위수를 계산합니다.
        """
        if side == 'up':
            r = self.n * self.proba / self.Nt[side]
            if gamma != 0:
                return self.init_threshold['up'] + (sigma / gamma) * (pow(r, -gamma) - 1)
            else:
                return self.init_threshold['up'] - sigma * log(r)
        elif side == 'down':
            r = self.n * self.proba / self.Nt[side]
            if gamma != 0:
                return self.init_threshold['down'] - (sigma / gamma) * (pow(r, -gamma) - 1)
            else:
                return self.init_threshold['down'] + sigma * log(r)
        else:
            print('error : the side is not right')

    def run(self, with_alarm=True):
        """
        스트림에 대해 biSPOT을 실행합니다.
        """
        if (self.n > self.init_data.size):
            print('Warning : the algorithm seems to have already been run, you \
            should initialize before running again')
            return {}

        # 임계값 리스트
        thup = []
        thdown = []
        alarm = []
        # 스트림에 대한 루프
        for i in range(self.data.size):

            # 관측된 값이 현재 임계값을 초과하는 경우 (알람 발생)
            if self.data[i] > self.extreme_quantile['up']:
                # 알람을 원하면 알람 리스트에 추가
                if with_alarm:
                    alarm.append(i)
                # 그렇지 않으면 피크에 추가
                else:
                    self.peaks['up'] = np.append(self.peaks['up'], self.data[i] - self.init_threshold['up'])
                    self.Nt['up'] += 1
                    self.n += 1
                    # 그리고 임계값 업데이트

                    g, s, l = self._grimshaw('up')
                    self.extreme_quantile['up'] = self._quantile('up', g, s)

            # 값이 초기 임계값은 초과하지만 알람 임계값은 초과하지 않는 경우
            elif self.data[i] > self.init_threshold['up']:
                # 피크에 추가
                self.peaks['up'] = np.append(self.peaks['up'], self.data[i] - self.init_threshold['up'])
                self.Nt['up'] += 1
                self.n += 1
                # 그리고 임계값 업데이트

                g, s, l = self._grimshaw('up')
                self.extreme_quantile['up'] = self._quantile('up', g, s)

            elif self.data[i] < self.extreme_quantile['down']:
                # 알람을 원하면 알람 리스트에 추가
                if with_alarm:
                    alarm.append(i)
                # 그렇지 않으면 피크에 추가
                else:
                    self.peaks['down'] = np.append(self.peaks['down'], -(self.data[i] - self.init_threshold['down']))
                    self.Nt['down'] += 1
                    self.n += 1
                    # 그리고 임계값 업데이트

                    g, s, l = self._grimshaw('down')
                    self.extreme_quantile['down'] = self._quantile('down', g, s)

            # 값이 초기 임계값은 초과하지만 알람 임계값은 초과하지 않는 경우
            elif self.data[i] < self.init_threshold['down']:
                # 피크에 추가
                self.peaks['down'] = np.append(self.peaks['down'], -(self.data[i] - self.init_threshold['down']))
                self.Nt['down'] += 1
                self.n += 1
                # 그리고 임계값 업데이트

                g, s, l = self._grimshaw('down')
                self.extreme_quantile['down'] = self._quantile('down', g, s)
            else:
                self.n += 1

            thup.append(self.extreme_quantile['up'])  # 상한 임계값 기록
            thdown.append(self.extreme_quantile['down'])  # 하한 임계값 기록

        return {'upper_thresholds': thup, 'lower_thresholds': thdown, 'alarms': alarm}

    def plot(self, run_results, with_alarm=True):
        """
        실행 결과를 플롯합니다.
        """
        x = range(self.data.size)
        K = run_results.keys()

        ts_fig, = plt.plot(x, self.data, color=air_force_blue)
        fig = [ts_fig]

        if 'upper_thresholds' in K:
            thup = run_results['upper_thresholds']
            uth_fig, = plt.plot(x, thup, color=deep_saffron, lw=2, ls='dashed')
            fig.append(uth_fig)

        if 'lower_thresholds' in K:
            thdown = run_results['lower_thresholds']
            lth_fig, = plt.plot(x, thdown, color=deep_saffron, lw=2, ls='dashed')
            fig.append(lth_fig)

        if with_alarm and ('alarms' in K):
            alarm = run_results['alarms']
            al_fig = plt.scatter(alarm, self.data[alarm], color='red')
            fig.append(al_fig)

        plt.xlim((0, self.data.size))

        return fig


"""
================================= WITH DRIFT ==================================
"""


def backMean(X, d):
    M = []
    w = X[:d].sum()
    M.append(w / d)
    for i in range(d, len(X)):
        w = w - X[i - d] + X[i]
        M.append(w / d)
    return np.array(M)


class dSPOT:
    """
    이 클래스는 단변량 데이터셋(상한)에 대해 드리프트를 고려한 dSPOT 알고리즘을 실행할 수 있게 합니다.
    """

    def __init__(self, q, depth):
        self.proba = q
        self.extreme_quantile = None
        self.data = None
        self.init_data = None
        self.init_threshold = None
        self.peaks = None
        self.n = 0
        self.Nt = 0
        self.depth = depth

    def __str__(self):
        s = ''
        s += 'Streaming Peaks-Over-Threshold Object\n'
        s += 'Detection level q = %s\n' % self.proba
        if self.data is not None:
            s += 'Data imported : Yes\n'
            s += '\t initialization  : %s values\n' % self.init_data.size
            s += '\t stream : %s values\n' % self.data.size
        else:
            s += 'Data imported : No\n'
            return s

        if self.n == 0:
            s += 'Algorithm initialized : No\n'
        else:
            s += 'Algorithm initialized : Yes\n'
            s += '\t initial threshold : %s\n' % self.init_threshold

            r = self.n - self.init_data.size
            if r > 0:
                s += 'Algorithm run : Yes\n'
                s += '\t number of observations : %s (%.2f %%)\n' % (r, 100 * r / self.n)
                s += '\t triggered alarms : %s (%.2f %%)\n' % (len(self.alarm), 100 * len(self.alarm) / self.n)
            else:
                s += '\t number of peaks  : %s\n' % self.Nt
                s += '\t extreme quantile : %s\n' % self.extreme_quantile
                s += 'Algorithm run : No\n'
        return s

    def fit(self, init_data, data):
        """
        DSPOT 객체에 데이터를 가져옵니다.
        """
        if isinstance(data, list):
            self.data = np.array(data)
        elif isinstance(data, np.ndarray):
            self.data = data
        elif isinstance(data, pd.Series):
            self.data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        if isinstance(init_data, list):
            self.init_data = np.array(init_data)
        elif isinstance(init_data, np.ndarray):
            self.init_data = init_data
        elif isinstance(init_data, pd.Series):
            self.init_data = init_data.values
        elif isinstance(init_data, int):
            self.init_data = self.data[:init_data]
            self.data = self.data[init_data:]
        elif isinstance(init_data, float) & (init_data < 1) & (init_data > 0):
            r = int(init_data * data.size)
            self.init_data = self.data[:r]
            self.data = self.data[r:]
        else:
            print('The initial data cannot be set')
            return

    def add(self, data):
        """
        이미 적합된 데이터에 데이터를 추가합니다.
        """
        if isinstance(data, list):
            data = np.array(data)
        elif isinstance(data, np.ndarray):
            data = data
        elif isinstance(data, pd.Series):
            data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        self.data = np.append(self.data, data)
        return

    def initialize(self, verbose=True):
        """
        보정(초기화) 단계를 실행합니다.
        """
        n_init = self.init_data.size - self.depth

        M = backMean(self.init_data, self.depth)
        T = self.init_data[self.depth:] - M[:-1]  # 새 변수

        S = np.sort(T)  # 경험적 분위수를 얻기 위해 X를 정렬
        self.init_threshold = S[int(0.98 * n_init)]  # t는 전체 알고리즘에 대해 고정

        # 초기 피크
        self.peaks = T[T > self.init_threshold] - self.init_threshold
        self.Nt = self.peaks.size
        self.n = n_init

        if verbose:
            print('Initial threshold : %s' % self.init_threshold)
            print('Number of peaks : %s' % self.Nt)
            print('Grimshaw maximum log-likelihood estimation ... ', end='')

        g, s, l = self._grimshaw()
        self.extreme_quantile = self._quantile(g, s)

        if verbose:
            print('[done]')
            print('\t' + chr(0x03B3) + ' = ' + str(g))
            print('\t' + chr(0x03C3) + ' = ' + str(s))
            print('\tL = ' + str(l))
            print('Extreme quantile (probability = %s): %s' % (self.proba, self.extreme_quantile))

        return

    def _rootsFinder(fun, jac, bounds, npoints, method):
        """
        스칼라 함수의 가능한 근을 찾습니다.
        """
        if method == 'regular':
            step = (bounds[1] - bounds[0]) / (npoints + 1)
            X0 = np.arange(bounds[0] + step, bounds[1], step)
        elif method == 'random':
            X0 = np.random.uniform(bounds[0], bounds[1], npoints)

        def objFun(X, f, jac):
            g = 0
            j = np.zeros(X.shape)
            i = 0
            for x in X:
                fx = f(x)
                g = g + fx ** 2
                j[i] = 2 * fx * jac(x)
                i = i + 1
            return g, j

        opt = minimize(lambda X: objFun(X, fun, jac), X0,
                       method='L-BFGS-B',
                       jac=True, bounds=[bounds] * len(X0))

        X = opt.x
        np.round(X, decimals=5)
        return np.unique(X)

    def _log_likelihood(Y, gamma, sigma):
        """
        일반화 파레토 분포(GPD, μ=0)에 대한 로그 우도를 계산합니다.
        """
        n = Y.size
        if gamma != 0:
            tau = gamma / sigma
            L = -n * log(sigma) - (1 + (1 / gamma)) * (np.log(1 + tau * Y)).sum()
        else:
            L = n * (1 + log(Y.mean()))
        return L

    def _grimshaw(self, epsilon=1e-8, n_points=10):
        """
        Grimshaw의 트릭을 사용하여 GPD 파라미터 추정치를 계산합니다.
        """

        def u(s):
            return 1 + np.log(s).mean()

        def v(s):
            return np.mean(1 / s)

        def w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            return us * vs - 1

        def jac_w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            jac_us = (1 / t) * (1 - vs)
            jac_vs = (1 / t) * (-vs + np.mean(1 / s ** 2))
            return us * jac_vs + vs * jac_us

        Ym = self.peaks.min()
        YM = self.peaks.max()
        Ymean = self.peaks.mean()

        a = -1 / YM
        if abs(a) < 2 * epsilon:
            epsilon = abs(a) / n_points

        a = a + epsilon
        b = 2 * (Ymean - Ym) / (Ymean * Ym)
        c = 2 * (Ymean - Ym) / (Ym ** 2)

        # 가능한 근을 찾습니다.
        left_zeros = SPOT._rootsFinder(lambda t: w(self.peaks, t),
                                       lambda t: jac_w(self.peaks, t),
                                       (a + epsilon, -epsilon),
                                       n_points, 'regular')

        right_zeros = SPOT._rootsFinder(lambda t: w(self.peaks, t),
                                        lambda t: jac_w(self.peaks, t),
                                        (b, c),
                                        n_points, 'regular')

        # 모든 가능한 근
        zeros = np.concatenate((left_zeros, right_zeros))

        # 0은 항상 해이므로 그것으로 초기화합니다.
        gamma_best = 0
        sigma_best = Ymean
        ll_best = SPOT._log_likelihood(self.peaks, gamma_best, sigma_best)

        # 더 나은 후보를 찾습니다.
        for z in zeros:
            gamma = u(1 + z * self.peaks) - 1
            sigma = gamma / z
            ll = dSPOT._log_likelihood(self.peaks, gamma, sigma)
            if ll > ll_best:
                gamma_best = gamma
                sigma_best = sigma
                ll_best = ll

        return gamma_best, sigma_best, ll_best

    def _quantile(self, gamma, sigma):
        """
        수준 1-q에서 분위수를 계산합니다.
        """
        r = self.n * self.proba / self.Nt
        if gamma != 0:
            return self.init_threshold + (sigma / gamma) * (pow(r, -gamma) - 1)
        else:
            return self.init_threshold - sigma * log(r)

    def run(self, with_alarm=True):
        """
        스트림에 대해 biSPOT을 실행합니다.
        """
        if (self.n > self.init_data.size):
            print('Warning : the algorithm seems to have already been run, you \
            should initialize before running again')
            return {}

        # 실제 정상 윈도우
        W = self.init_data[-self.depth:]

        # 임계값 리스트
        th = []
        alarm = []
        # 스트림에 대한 루프
        for i in range(self.data.size):
            Mi = W.mean()
            # 관측된 값이 현재 임계값을 초과하는 경우 (알람 발생)
            if (self.data[i] - Mi) > self.extreme_quantile:
                # 알람을 원하면 알람 리스트에 추가
                if with_alarm:
                    alarm.append(i)
                # 그렇지 않으면 피크에 추가
                else:
                    self.peaks = np.append(self.peaks, self.data[i] - Mi - self.init_threshold)
                    self.Nt += 1
                    self.n += 1
                    # 그리고 임계값 업데이트

                    g, s, l = self._grimshaw()
                    self.extreme_quantile = self._quantile(g, s)  # + Mi
                    W = np.append(W[1:], self.data[i])

            # 값이 초기 임계값은 초과하지만 알람 임계값은 초과하지 않는 경우
            elif (self.data[i] - Mi) > self.init_threshold:
                # 피크에 추가
                self.peaks = np.append(self.peaks, self.data[i] - Mi - self.init_threshold)
                self.Nt += 1
                self.n += 1
                # 그리고 임계값 업데이트

                g, s, l = self._grimshaw()
                self.extreme_quantile = self._quantile(g, s)  # + Mi
                W = np.append(W[1:], self.data[i])
            else:
                self.n += 1
                W = np.append(W[1:], self.data[i])

            th.append(self.extreme_quantile + Mi)  # 임계값 기록

        return {'thresholds': th, 'alarms': alarm}

    def plot(self, run_results, with_alarm=True):
        """
        실행 결과를 플롯합니다.
        """
        x = range(self.data.size)
        K = run_results.keys()

        ts_fig, = plt.plot(x, self.data, color=air_force_blue)
        fig = [ts_fig]

        #        if 'upper_thresholds' in K:
        #            thup = run_results['upper_thresholds']
        #            uth_fig, = plt.plot(x,thup,color=deep_saffron,lw=2,ls='dashed')
        #            fig.append(uth_fig)
        #
        #        if 'lower_thresholds' in K:
        #            thdown = run_results['lower_thresholds']
        #            lth_fig, = plt.plot(x,thdown,color=deep_saffron,lw=2,ls='dashed')
        #            fig.append(lth_fig)

        if 'thresholds' in K:
            th = run_results['thresholds']
            th_fig, = plt.plot(x, th, color=deep_saffron, lw=2, ls='dashed')
            fig.append(th_fig)

        if with_alarm and ('alarms' in K):
            alarm = run_results['alarms']
            if len(alarm) > 0:
                plt.scatter(alarm, self.data[alarm], color='red')

        plt.xlim((0, self.data.size))

        return fig


"""
=========================== DRIFT & DOUBLE BOUNDS =============================
"""


class bidSPOT:
    """
    이 클래스는 단변량 데이터셋(상한 및 하한)에 대해 드리프트를 고려한 bidSPOT 알고리즘을 실행할 수 있게 합니다.
    """

    def __init__(self, q=1e-4, depth=10):
        self.proba = q
        self.data = None
        self.init_data = None
        self.n = 0
        self.depth = depth

        nonedict = {'up': None, 'down': None}

        self.extreme_quantile = dict.copy(nonedict)
        self.init_threshold = dict.copy(nonedict)
        self.peaks = dict.copy(nonedict)
        self.gamma = dict.copy(nonedict)
        self.sigma = dict.copy(nonedict)
        self.Nt = {'up': 0, 'down': 0}

    def __str__(self):
        s = ''
        s += 'Streaming Peaks-Over-Threshold Object\n'
        s += 'Detection level q = %s\n' % self.proba
        if self.data is not None:
            s += 'Data imported : Yes\n'
            s += '\t initialization  : %s values\n' % self.init_data.size
            s += '\t stream : %s values\n' % self.data.size
        else:
            s += 'Data imported : No\n'
            return s

        if self.n == 0:
            s += 'Algorithm initialized : No\n'
        else:
            s += 'Algorithm initialized : Yes\n'
            s += '\t initial threshold : %s\n' % self.init_threshold

            r = self.n - self.init_data.size
            if r > 0:
                s += 'Algorithm run : Yes\n'
                s += '\t number of observations : %s (%.2f %%)\n' % (r, 100 * r / self.n)
                s += '\t triggered alarms : %s (%.2f %%)\n' % (len(self.alarm), 100 * len(self.alarm) / self.n)
            else:
                s += '\t number of peaks  : %s\n' % self.Nt
                s += '\t upper extreme quantile : %s\n' % self.extreme_quantile['up']
                s += '\t lower extreme quantile : %s\n' % self.extreme_quantile['down']
                s += 'Algorithm run : No\n'
        return s

    def fit(self, init_data, data):
        """
        biDSPOT 객체에 데이터를 가져옵니다.
        """
        if isinstance(data, list):
            self.data = np.array(data)
        elif isinstance(data, np.ndarray):
            self.data = data
        elif isinstance(data, pd.Series):
            self.data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        if isinstance(init_data, list):
            self.init_data = np.array(init_data)
        elif isinstance(init_data, np.ndarray):
            self.init_data = init_data
        elif isinstance(init_data, pd.Series):
            self.init_data = init_data.values
        elif isinstance(init_data, int):
            self.init_data = self.data[:init_data]
            self.data = self.data[init_data:]
        elif isinstance(init_data, float) & (init_data < 1) & (init_data > 0):
            r = int(init_data * data.size)
            self.init_data = self.data[:r]
            self.data = self.data[r:]
        else:
            print('The initial data cannot be set')
            return

    def add(self, data):
        """
        이미 적합된 데이터에 데이터를 추가합니다.
        """
        if isinstance(data, list):
            data = np.array(data)
        elif isinstance(data, np.ndarray):
            data = data
        elif isinstance(data, pd.Series):
            data = data.values
        else:
            print('This data format (%s) is not supported' % type(data))
            return

        self.data = np.append(self.data, data)
        return

    def initialize(self, verbose=True):
        """
        보정(초기화) 단계를 실행합니다.
        """
        n_init = self.init_data.size - self.depth

        M = backMean(self.init_data, self.depth)
        T = self.init_data[self.depth:] - M[:-1]  # 새 변수

        S = np.sort(T)  # 경험적 분위수를 얻기 위해 T를 정렬
        self.init_threshold['up'] = S[int(0.98 * n_init)]  # t는 전체 알고리즘에 대해 고정
        self.init_threshold['down'] = S[int(0.02 * n_init)]  # t는 전체 알고리즘에 대해 고정

        # 초기 피크
        self.peaks['up'] = T[T > self.init_threshold['up']] - self.init_threshold['up']
        self.peaks['down'] = -(T[T < self.init_threshold['down']] - self.init_threshold['down'])
        self.Nt['up'] = self.peaks['up'].size
        self.Nt['down'] = self.peaks['down'].size
        self.n = n_init

        if verbose:
            print('Initial threshold : %s' % self.init_threshold)
            print('Number of peaks : %s' % self.Nt)
            print('Grimshaw maximum log-likelihood estimation ... ', end='')

        l = {'up': None, 'down': None}
        for side in ['up', 'down']:
            g, s, l[side] = self._grimshaw(side)
            self.extreme_quantile[side] = self._quantile(side, g, s)
            self.gamma[side] = g
            self.sigma[side] = s

        ltab = 20
        form = ('\t' + '%20s' + '%20.2f' + '%20.2f')
        if verbose:
            print('[done]')
            print('\t' + 'Parameters'.rjust(ltab) + 'Upper'.rjust(ltab) + 'Lower'.rjust(ltab))
            print('\t' + '-' * ltab * 3)
            print(form % (chr(0x03B3), self.gamma['up'], self.gamma['down']))
            print(form % (chr(0x03C3), self.sigma['up'], self.sigma['down']))
            print(form % ('likelihood', l['up'], l['down']))
            print(form % ('Extreme quantile', self.extreme_quantile['up'], self.extreme_quantile['down']))
            print('\t' + '-' * ltab * 3)
        return

    def _rootsFinder(fun, jac, bounds, npoints, method):
        """
        스칼라 함수의 가능한 근을 찾습니다.
        """
        if method == 'regular':
            step = (bounds[1] - bounds[0]) / (npoints + 1)
            X0 = np.arange(bounds[0] + step, bounds[1], step)
        elif method == 'random':
            X0 = np.random.uniform(bounds[0], bounds[1], npoints)

        def objFun(X, f, jac):
            g = 0
            j = np.zeros(X.shape)
            i = 0
            for x in X:
                fx = f(x)
                g = g + fx ** 2
                j[i] = 2 * fx * jac(x)
                i = i + 1
            return g, j

        opt = minimize(lambda X: objFun(X, fun, jac), X0,
                       method='L-BFGS-B',
                       jac=True, bounds=[bounds] * len(X0))

        X = opt.x
        np.round(X, decimals=5)
        return np.unique(X)

    def _log_likelihood(Y, gamma, sigma):
        """
        일반화 파레토 분포(GPD, μ=0)에 대한 로그 우도를 계산합니다.
        """
        n = Y.size
        if gamma != 0:
            tau = gamma / sigma
            L = -n * log(sigma) - (1 + (1 / gamma)) * (np.log(1 + tau * Y)).sum()
        else:
            L = n * (1 + log(Y.mean()))
        return L

    def _grimshaw(self, side, epsilon=1e-8, n_points=8):
        """
        Grimshaw의 트릭을 사용하여 GPD 파라미터 추정치를 계산합니다.
        """

        def u(s):
            return 1 + np.log(s).mean()

        def v(s):
            return np.mean(1 / s)

        def w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            return us * vs - 1

        def jac_w(Y, t):
            s = 1 + t * Y
            us = u(s)
            vs = v(s)
            jac_us = (1 / t) * (1 - vs)
            jac_vs = (1 / t) * (-vs + np.mean(1 / s ** 2))
            return us * jac_vs + vs * jac_us

        Ym = self.peaks[side].min()
        YM = self.peaks[side].max()
        Ymean = self.peaks[side].mean()

        a = -1 / YM
        if abs(a) < 2 * epsilon:
            epsilon = abs(a) / n_points

        a = a + epsilon
        b = 2 * (Ymean - Ym) / (Ymean * Ym)
        c = 2 * (Ymean - Ym) / (Ym ** 2)

        # 가능한 근을 찾습니다.
        left_zeros = bidSPOT._rootsFinder(lambda t: w(self.peaks[side], t),
                                          lambda t: jac_w(self.peaks[side], t),
                                          (a + epsilon, -epsilon),
                                          n_points, 'regular')

        right_zeros = bidSPOT._rootsFinder(lambda t: w(self.peaks[side], t),
                                           lambda t: jac_w(self.peaks[side], t),
                                           (b, c),
                                           n_points, 'regular')

        # 모든 가능한 근
        zeros = np.concatenate((left_zeros, right_zeros))

        # 0은 항상 해이므로 그것으로 초기화합니다.
        gamma_best = 0
        sigma_best = Ymean
        ll_best = bidSPOT._log_likelihood(self.peaks[side], gamma_best, sigma_best)

        # 더 나은 후보를 찾습니다.
        for z in zeros:
            gamma = u(1 + z * self.peaks[side]) - 1
            sigma = gamma / z
            ll = bidSPOT._log_likelihood(self.peaks[side], gamma, sigma)
            if ll > ll_best:
                gamma_best = gamma
                sigma_best = sigma
                ll_best = ll

        return gamma_best, sigma_best, ll_best

    def _quantile(self, side, gamma, sigma):
        """
        주어진 측면에 대해 수준 1-q에서 분위수를 계산합니다.
        """
        if side == 'up':
            r = self.n * self.proba / self.Nt[side]
            if gamma != 0:
                return self.init_threshold['up'] + (sigma / gamma) * (pow(r, -gamma) - 1)
            else:
                return self.init_threshold['up'] - sigma * log(r)
        elif side == 'down':
            r = self.n * self.proba / self.Nt[side]
            if gamma != 0:
                return self.init_threshold['down'] - (sigma / gamma) * (pow(r, -gamma) - 1)
            else:
                return self.init_threshold['down'] + sigma * log(r)
        else:
            print('error : the side is not right')

    def run(self, with_alarm=True, plot=True):
        """
        스트림에 대해 biDSPOT을 실행합니다.
        """
        if (self.n > self.init_data.size):
            print('Warning : the algorithm seems to have already been run, you \
            should initialize before running again')
            return {}

        # 실제 정상 윈도우
        W = self.init_data[-self.depth:]

        # 임계값 리스트
        thup = []
        thdown = []
        alarm = []
        # 스트림에 대한 루프
        for i in range(self.data.size):
            Mi = W.mean()
            Ni = self.data[i] - Mi
            # 관측된 값이 현재 임계값을 초과하는 경우 (알람 발생)
            if Ni > self.extreme_quantile['up']:
                # 알람을 원하면 알람 리스트에 추가
                if with_alarm:
                    alarm.append(i)
                # 그렇지 않으면 피크에 추가
                else:
                    self.peaks['up'] = np.append(self.peaks['up'], Ni - self.init_threshold['up'])
                    self.Nt['up'] += 1
                    self.n += 1
                    # 그리고 임계값 업데이트

                    g, s, l = self._grimshaw('up')
                    self.extreme_quantile['up'] = self._quantile('up', g, s)
                    W = np.append(W[1:], self.data[i])

            # 값이 초기 임계값은 초과하지만 알람 임계값은 초과하지 않는 경우
            elif Ni > self.init_threshold['up']:
                # 피크에 추가
                self.peaks['up'] = np.append(self.peaks['up'], Ni - self.init_threshold['up'])
                self.Nt['up'] += 1
                self.n += 1
                # 그리고 임계값 업데이트
                g, s, l = self._grimshaw('up')
                self.extreme_quantile['up'] = self._quantile('up', g, s)
                W = np.append(W[1:], self.data[i])

            elif Ni < self.extreme_quantile['down']:
                # 알람을 원하면 알람 리스트에 추가
                if with_alarm:
                    alarm.append(i)
                # 그렇지 않으면 피크에 추가
                else:
                    self.peaks['down'] = np.append(self.peaks['down'], -(Ni - self.init_threshold['down']))
                    self.Nt['down'] += 1
                    self.n += 1
                    # 그리고 임계값 업데이트

                    g, s, l = self._grimshaw('down')
                    self.extreme_quantile['down'] = self._quantile('down', g, s)
                    W = np.append(W[1:], self.data[i])

            # 값이 초기 임계값은 초과하지만 알람 임계값은 초과하지 않는 경우
            elif Ni < self.init_threshold['down']:
                # 피크에 추가
                self.peaks['down'] = np.append(self.peaks['down'], -(Ni - self.init_threshold['down']))
                self.Nt['down'] += 1
                self.n += 1
                # 그리고 임계값 업데이트

                g, s, l = self._grimshaw('down')
                self.extreme_quantile['down'] = self._quantile('down', g, s)
                W = np.append(W[1:], self.data[i])
            else:
                self.n += 1
                W = np.append(W[1:], self.data[i])

            thup.append(self.extreme_quantile['up'] + Mi)  # 상한 임계값 기록
            thdown.append(self.extreme_quantile['down'] + Mi)  # 하한 임계값 기록

        return {'upper_thresholds': thup, 'lower_thresholds': thdown, 'alarms': alarm}

    def plot(self, run_results, with_alarm=True):
        """
        실행 결과를 플롯합니다.
        """
        x = range(self.data.size)
        K = run_results.keys()

        ts_fig, = plt.plot(x, self.data, color=air_force_blue)
        fig = [ts_fig]

        if 'upper_thresholds' in K:
            thup = run_results['upper_thresholds']
            uth_fig, = plt.plot(x, thup, color=deep_saffron, lw=2, ls='dashed')
            fig.append(uth_fig)

        if 'lower_thresholds' in K:
            thdown = run_results['lower_thresholds']
            lth_fig, = plt.plot(x, thdown, color=deep_saffron, lw=2, ls='dashed')
            fig.append(lth_fig)

        if with_alarm and ('alarms' in K):
            alarm = run_results['alarms']
            if len(alarm) > 0:
                plt.scatter(alarm, self.data[alarm], color='red')

        plt.xlim((0, self.data.size))

        return fig
