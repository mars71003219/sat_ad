import React, { useState, useEffect, useRef } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { format } from 'date-fns';
import axios from 'axios';
import './TrendChart.css';

const SUBSYSTEMS = [
  { key: 'eps', label: 'EPS (전력)', color: '#4a9eff' },
  { key: 'thermal', label: 'Thermal (온도)', color: '#a78bfa' },
  { key: 'aocs', label: 'AOCS (자세제어)', color: '#fbbf24' },
  { key: 'comm', label: 'Comm (통신)', color: '#4ade80' }
];

const TIME_RANGES = [
  { label: '5m', hours: 5/60 },
  { label: '15m', hours: 15/60 },
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '9h', hours: 9 },
  { label: '24h', hours: 24 }
];

function TrendChart({ onFilterChange }) {
  const [selectedSubsystem, setSelectedSubsystem] = useState(SUBSYSTEMS[0]);
  const [selectedTimeRange, setSelectedTimeRange] = useState(TIME_RANGES[2]); // 1h
  const [trendData, setTrendData] = useState([]);
  const [error, setError] = useState(null);
  const [satellites, setSatellites] = useState([]);
  const [selectedSatellite, setSelectedSatellite] = useState('SAT-001');
  const [visibleLines, setVisibleLines] = useState({
    actual_value: true,
    predicted_value: true,
    anomaly_detected: true
  });
  const [threshold, setThreshold] = useState(0.5); // 잔차 임계값
  const [features, setFeatures] = useState([]);
  const [selectedFeature, setSelectedFeature] = useState(null); // null = 종합 평균
  const [subsystemStats, setSubsystemStats] = useState({}); // 서브시스템별 최근 값
  const [wsConnected, setWsConnected] = useState(false);

  const trendWsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // 위성 목록 조회
  useEffect(() => {
    fetchSatellites();
  }, []);

  // WebSocket 연결 설정
  useEffect(() => {
    connectTrendWebSocket();

    return () => {
      if (trendWsRef.current) {
        trendWsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 필터 변경 시 WebSocket으로 전송
  useEffect(() => {
    if (trendWsRef.current && trendWsRef.current.readyState === WebSocket.OPEN) {
      const now = Date.now();
      const endTime = new Date(now).toISOString();
      const startTime = new Date(now - selectedTimeRange.hours * 60 * 60 * 1000).toISOString();

      const filters = {
        satellite_id: selectedSatellite,
        subsystem: selectedSubsystem.key,
        feature_index: selectedFeature,
        start_time: startTime,
        end_time: endTime
      };
      console.log('Sending trend filters to WebSocket:', filters);
      trendWsRef.current.send(JSON.stringify(filters));
    }
  }, [selectedSatellite, selectedSubsystem, selectedFeature, selectedTimeRange]);

  // 선택 변경 시 상위 컴포넌트에 알림
  useEffect(() => {
    if (onFilterChange) {
      onFilterChange(selectedSatellite, selectedSubsystem.key, selectedFeature);
    }
  }, [selectedSatellite, selectedSubsystem, selectedFeature, onFilterChange]);

  const connectTrendWebSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/trends`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('Trend WebSocket connected');
        setWsConnected(true);
        setError(null);

        // 현재 필터 전송
        const now = Date.now();
        const endTime = new Date(now).toISOString();
        const startTime = new Date(now - selectedTimeRange.hours * 60 * 60 * 1000).toISOString();

        const filters = {
          satellite_id: selectedSatellite,
          subsystem: selectedSubsystem.key,
          feature_index: selectedFeature,
          start_time: startTime,
          end_time: endTime
        };
        ws.send(JSON.stringify(filters));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'trends' && data.data) {
          const responseData = data.data;

          if (responseData.data_points && responseData.data_points.length > 0) {
            const formattedData = responseData.data_points.map(point => {
              const actual = point.actual_value;
              const predicted = point.predicted_value;
              const residual = actual !== null && predicted !== null ? Math.abs(actual - predicted) : null;
              const isAnomaly = residual !== null && residual > threshold;

              return {
                timestamp: new Date(point.timestamp).getTime(),
                actual_value: actual,
                predicted_value: predicted,
                residual: residual,
                anomaly_detected: isAnomaly ? actual : null
              };
            });
            setTrendData(formattedData);
          }
        } else if (data.type === 'error') {
          console.error('Trend WebSocket error:', data.message);
          setError(data.message);
        }
      };

      ws.onerror = (error) => {
        console.error('Trend WebSocket error:', error);
        setWsConnected(false);
        setError('WebSocket connection error');
      };

      ws.onclose = () => {
        console.log('Trend WebSocket disconnected');
        setWsConnected(false);

        // 5초 후 재연결 시도
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect trend WebSocket...');
          connectTrendWebSocket();
        }, 5000);
      };

      trendWsRef.current = ws;
    } catch (error) {
      console.error('Failed to create Trend WebSocket:', error);
      setWsConnected(false);
      setError('Failed to connect');
    }
  };

  const fetchSatellites = async () => {
    try {
      const response = await axios.get('/api/dashboard/stats');
      if (response.data && response.data.satellites) {
        const sats = response.data.satellites.map(s => s.satellite_id);
        setSatellites(sats);
        if (sats.length > 0) {
          setSelectedSatellite(sats[0]);
        }
      }
    } catch (err) {
      console.error('Failed to fetch satellites:', err);
    }
  };

  // 서브시스템 변경 시 특징 목록 조회
  useEffect(() => {
    fetchFeatures();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSubsystem]);

  const fetchFeatures = async () => {
    try {
      const response = await axios.get(`/api/dashboard/features?subsystem=${selectedSubsystem.key}`);
      if (response.data && response.data.features) {
        setFeatures(response.data.features);
        setSelectedFeature(null); // 서브시스템 변경 시 종합 평균으로 리셋
      }
    } catch (err) {
      console.error('Failed to fetch features:', err);
      setFeatures([]);
    }
  };

  // WebSocket에서 서브시스템 통계 자동 업데이트
  useEffect(() => {
    // 트렌드 데이터가 업데이트될 때마다 서브시스템 통계도 함께 업데이트
    if (trendData.length > 0) {
      const lastPoint = trendData[trendData.length - 1];
      setSubsystemStats(prev => ({
        ...prev,
        [selectedSubsystem.key]: {
          actual: lastPoint.actual_value,
          predicted: lastPoint.predicted_value
        }
      }));
    }
  }, [trendData, selectedSubsystem.key]);

  // 수동 새로고침 함수 (새로고침 버튼용)
  const handleManualRefresh = () => {
    if (trendWsRef.current && trendWsRef.current.readyState === WebSocket.OPEN) {
      const now = Date.now();
      const endTime = new Date(now).toISOString();
      const startTime = new Date(now - selectedTimeRange.hours * 60 * 60 * 1000).toISOString();

      const filters = {
        satellite_id: selectedSatellite,
        subsystem: selectedSubsystem.key,
        feature_index: selectedFeature,
        start_time: startTime,
        end_time: endTime
      };
      trendWsRef.current.send(JSON.stringify(filters));
    }
  };

  const formatXAxis = (timestamp) => {
    if (selectedTimeRange.hours <= 0.25) {
      return format(new Date(timestamp), 'HH:mm:ss');
    } else if (selectedTimeRange.hours <= 1) {
      return format(new Date(timestamp), 'HH:mm');
    } else {
      return format(new Date(timestamp), 'HH:mm');
    }
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="custom-tooltip">
          <p className="tooltip-time">{format(new Date(label), 'yyyy-MM-dd HH:mm:ss')}</p>
          {data.actual_value !== null && data.actual_value !== undefined && (
            <p style={{ color: selectedSubsystem.color }}>
              실측값: {data.actual_value.toFixed(3)}
            </p>
          )}
          {data.predicted_value !== null && data.predicted_value !== undefined && (
            <p style={{ color: '#4ade80' }}>
              예측값: {data.predicted_value.toFixed(3)}
            </p>
          )}
          {data.residual !== null && data.residual !== undefined && (
            <p style={{ color: data.residual > threshold ? '#f87171' : '#a0a0a0' }}>
              잔차: {data.residual.toFixed(3)} {data.residual > threshold ? '(이상)' : ''}
            </p>
          )}
        </div>
      );
    }
    return null;
  };

  const toggleLine = (lineKey) => {
    setVisibleLines(prev => ({
      ...prev,
      [lineKey]: !prev[lineKey]
    }));
  };

  return (
    <div className="trend-chart-container">
      <div className="chart-header">
        <div className="header-left">
          <h2>Anomaly Score Trend</h2>
        </div>

        <div className="header-controls">
          {/* 위성 선택 */}
          {satellites.length > 0 && (
            <select
              className="satellite-selector"
              value={selectedSatellite}
              onChange={(e) => setSelectedSatellite(e.target.value)}
            >
              {satellites.map(sat => (
                <option key={sat} value={sat}>{sat}</option>
              ))}
            </select>
          )}

          {/* 특징 선택 */}
          {features.length > 0 && (
            <select
              className="feature-selector"
              value={selectedFeature === null ? 'all' : selectedFeature}
              onChange={(e) => setSelectedFeature(e.target.value === 'all' ? null : parseInt(e.target.value))}
            >
              <option value="all">All Features (Average)</option>
              {features.map(feature => (
                <option key={feature.index} value={feature.index}>{feature.name}</option>
              ))}
            </select>
          )}

          {/* 시간 범위 선택 */}
          {TIME_RANGES.map(range => (
            <button
              key={range.label}
              className={`time-range-btn ${selectedTimeRange.label === range.label ? 'active' : ''}`}
              onClick={() => setSelectedTimeRange(range)}
            >
              {range.label}
            </button>
          ))}

          <button className="refresh-btn" onClick={handleManualRefresh}>
            ↻
          </button>
        </div>
      </div>

      {/* 서브시스템 선택 */}
      <div className="subsystems-grid">
        {SUBSYSTEMS.map(subsystem => {
          const isSelected = selectedSubsystem.key === subsystem.key;
          const stats = subsystemStats[subsystem.key];
          return (
            <div
              key={subsystem.key}
              className={`subsystem-card ${isSelected ? 'selected' : ''}`}
              onClick={() => setSelectedSubsystem(subsystem)}
            >
              <div className="subsystem-label">{subsystem.label}</div>
              {stats && (
                <div className="subsystem-values">
                  <div className="subsystem-value-item">
                    <div className="subsystem-value-label">Actual</div>
                    <div className="subsystem-value-number">
                      {stats.actual !== null && stats.actual !== undefined ? stats.actual.toFixed(2) : 'N/A'}
                    </div>
                  </div>
                  <div className="subsystem-value-item">
                    <div className="subsystem-value-label">Predicted</div>
                    <div className="subsystem-value-number predicted">
                      {stats.predicted !== null && stats.predicted !== undefined ? stats.predicted.toFixed(2) : 'N/A'}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 에러 메시지 */}
      {error && (
        <div className="error-message">
          ⚠️ Error: {error}
        </div>
      )}

      {/* 차트 */}
      <div className="chart-wrapper">
        <div className="chart-legend">
          <span
            className={`legend-item ${visibleLines.actual_value ? 'active' : 'inactive'}`}
            onClick={() => toggleLine('actual_value')}
          >
            <span className="legend-line actual-value"></span>
            실측값 (Actual)
          </span>
          <span
            className={`legend-item ${visibleLines.predicted_value ? 'active' : 'inactive'}`}
            onClick={() => toggleLine('predicted_value')}
          >
            <span className="legend-line predicted-value"></span>
            예측값 (Predicted)
          </span>
          <span
            className={`legend-item ${visibleLines.anomaly_detected ? 'active' : 'inactive'}`}
            onClick={() => toggleLine('anomaly_detected')}
          >
            <span className="legend-line anomaly-detected"></span>
            이상 감지 (Anomaly)
          </span>
          <div style={{ marginLeft: '16px', color: '#909296', fontSize: '12px' }}>
            임계값: {threshold.toFixed(2)}
          </div>
        </div>

        {trendData.length === 0 ? (
          <div className="empty-state">
            {wsConnected ? 'Waiting for data...' : 'Connecting...'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2b30" />
              <XAxis
                dataKey="timestamp"
                type="number"
                domain={['dataMin', 'dataMax']}
                tickFormatter={formatXAxis}
                stroke="#909296"
                scale="time"
                tickCount={6}
                style={{ fontSize: '11px' }}
              />
              <YAxis
                stroke="#909296"
                label={{ value: 'Value', angle: -90, position: 'insideLeft', fill: '#909296', fontSize: 11 }}
                style={{ fontSize: '11px' }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              {visibleLines.actual_value && (
                <Line
                  type="monotone"
                  dataKey="actual_value"
                  stroke={selectedSubsystem.color}
                  strokeWidth={2}
                  dot={false}
                  name="실측값"
                  isAnimationActive={false}
                  connectNulls={true}
                />
              )}
              {visibleLines.predicted_value && (
                <Line
                  type="monotone"
                  dataKey="predicted_value"
                  stroke="#4ade80"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={false}
                  name="예측값"
                  isAnimationActive={false}
                  connectNulls={true}
                />
              )}
              {visibleLines.anomaly_detected && (
                <Line
                  type="monotone"
                  dataKey="anomaly_detected"
                  stroke="#f87171"
                  strokeWidth={0}
                  dot={{ r: 5, fill: '#f87171' }}
                  name="이상 감지"
                  isAnimationActive={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default TrendChart;
