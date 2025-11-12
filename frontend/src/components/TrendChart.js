import React, { useState, useEffect, useRef } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  Bar
} from 'recharts';
import { format } from 'date-fns';
import axios from 'axios';
import './TrendChart.css';

const SUBSYSTEMS = [
  { key: 'EPS', label: 'EPS (전력)', color: '#4a9eff' },
  { key: 'TCS', label: 'TCS (온도)', color: '#a78bfa' },
  { key: 'ACS', label: 'ACS (자세제어)', color: '#fbbf24' },
  { key: 'Data', label: 'Data (통신)', color: '#4ade80' },
  { key: 'FSW', label: 'FSW', color: '#f59e0b' },
  { key: 'PS', label: 'PS', color: '#8b5cf6' },
  { key: 'SS', label: 'SS', color: '#ec4899' }
];

const TIME_RANGES = [
  { label: '30s', seconds: 30 },
  { label: '1m', seconds: 60 },
  { label: '5m', seconds: 300 },
  { label: '15m', seconds: 900 },
  { label: '1h', seconds: 3600 }
];

const MAX_DATA_POINTS = 500; // 최대 표시 데이터 포인트

function TrendChart({ onFilterChange }) {
  const [selectedSubsystem, setSelectedSubsystem] = useState(SUBSYSTEMS[0]);
  const [selectedTimeRange, setSelectedTimeRange] = useState(TIME_RANGES[2]); // 5m
  const [trendData, setTrendData] = useState([]);
  const [anomalyScoreData, setAnomalyScoreData] = useState([]);
  const [error, setError] = useState(null);
  const [satellites, setSatellites] = useState([]);
  const [selectedSatellite, setSelectedSatellite] = useState('sat1');
  const [visibleLines, setVisibleLines] = useState({
    actual_value: true,
    predicted_value: true,
    anomaly_detected: true
  });
  const [threshold, setThreshold] = useState(0.5); // 잔차 임계값
  const [features, setFeatures] = useState([]);
  const [selectedFeature, setSelectedFeature] = useState(0); // 0~24
  const [subsystemStats, setSubsystemStats] = useState({}); // 서브시스템별 최근 값
  const [wsConnected, setWsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(true); // 실시간 스트리밍 on/off

  const trendWsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const streamIntervalRef = useRef(null);

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

  // 실시간 스트리밍 업데이트 (1초마다)
  useEffect(() => {
    if (isStreaming) {
      streamIntervalRef.current = setInterval(() => {
        fetchRealtimeData();
      }, 1000);
    } else {
      if (streamIntervalRef.current) {
        clearInterval(streamIntervalRef.current);
      }
    }

    return () => {
      if (streamIntervalRef.current) {
        clearInterval(streamIntervalRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming, selectedSatellite, selectedSubsystem, selectedFeature, selectedTimeRange]);

  // 필터 변경 시 초기 데이터 로드
  useEffect(() => {
    fetchRealtimeData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSatellite, selectedSubsystem, selectedFeature, selectedTimeRange]);

  // 선택 변경 시 상위 컴포넌트에 알림
  useEffect(() => {
    if (onFilterChange) {
      onFilterChange(selectedSatellite, selectedSubsystem.key, selectedFeature);
    }
  }, [selectedSatellite, selectedSubsystem, selectedFeature, onFilterChange]);

  const fetchRealtimeData = async () => {
    try {
      const now = Date.now();
      const startTime = new Date(now - selectedTimeRange.seconds * 1000).toISOString();
      const endTime = new Date(now).toISOString();

      const response = await axios.get('/api/dashboard/trends', {
        params: {
          satellite_id: selectedSatellite,
          subsystem: selectedSubsystem.key,
          feature_index: selectedFeature,
          start_time: startTime,
          end_time: endTime
        }
      });

      if (response.data && response.data.data_points) {
        const dataPoints = response.data.data_points;

        // 텔레메트리 값 데이터
        const formattedTrendData = dataPoints.map(point => {
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

        // 이상 점수 데이터
        const formattedAnomalyData = dataPoints.map(point => ({
          timestamp: new Date(point.timestamp).getTime(),
          anomaly_score: point.anomaly_score || 0
        }));

        // 최대 포인트 수 제한 (메모리 관리)
        setTrendData(prev => {
          const combined = [...prev, ...formattedTrendData];
          return combined.slice(-MAX_DATA_POINTS);
        });

        setAnomalyScoreData(prev => {
          const combined = [...prev, ...formattedAnomalyData];
          return combined.slice(-MAX_DATA_POINTS);
        });

        setError(null);
      }
    } catch (err) {
      console.error('Failed to fetch realtime data:', err);
      setError('Failed to fetch data');
    }
  };

  const connectTrendWebSocket = () => {
    // WebSocket은 제거하고 polling 방식으로 대체
    setWsConnected(true);
  };

  const fetchSatellites = async () => {
    try {
      // VictoriaMetrics에서 실제 satellite_id 조회
      const sats = ['sat1', 'sat2', 'sat3', 'sat4', 'sat5'];
      setSatellites(sats);
      if (sats.length > 0 && !selectedSatellite) {
        setSelectedSatellite(sats[0]);
      }
    } catch (err) {
      console.error('Failed to fetch satellites:', err);
    }
  };

  // 서브시스템 변경 시 특징 목록 생성 (0~24)
  useEffect(() => {
    const featureList = Array.from({ length: 25 }, (_, i) => ({
      index: i,
      name: `Dimension ${i}`
    }));
    setFeatures(featureList);
    setSelectedFeature(0); // 첫 번째 특징으로 리셋
  }, [selectedSubsystem]);

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

  // 수동 새로고침 함수
  const handleManualRefresh = () => {
    // 데이터 초기화 후 다시 로드
    setTrendData([]);
    setAnomalyScoreData([]);
    fetchRealtimeData();
  };

  // 스트리밍 토글
  const toggleStreaming = () => {
    setIsStreaming(prev => !prev);
  };

  const formatXAxis = (timestamp) => {
    if (selectedTimeRange.seconds <= 60) {
      return format(new Date(timestamp), 'HH:mm:ss');
    } else if (selectedTimeRange.seconds <= 900) {
      return format(new Date(timestamp), 'HH:mm:ss');
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
          <h2>Real-time Telemetry Stream</h2>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '12px',
            color: isStreaming ? '#4ade80' : '#909296'
          }}>
            <div style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: isStreaming ? '#4ade80' : '#909296',
              animation: isStreaming ? 'pulse 2s infinite' : 'none'
            }}></div>
            {isStreaming ? 'Streaming Live' : 'Paused'}
          </div>
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

          {/* 특징 선택 (Dimension 0-24) */}
          {features.length > 0 && (
            <select
              className="feature-selector"
              value={selectedFeature}
              onChange={(e) => setSelectedFeature(parseInt(e.target.value))}
            >
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

          <button
            className={`stream-btn ${isStreaming ? 'active' : ''}`}
            onClick={toggleStreaming}
            title={isStreaming ? 'Pause streaming' : 'Resume streaming'}
          >
            {isStreaming ? '⏸' : '▶'}
          </button>

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

      {/* 차트 1: 텔레메트리 값 (True vs Predicted) */}
      <div className="chart-wrapper">
        <div className="chart-title">
          <h3>Telemetry Value - {selectedSubsystem.label} (Dimension {selectedFeature})</h3>
        </div>
        <div className="chart-legend">
          <span
            className={`legend-item ${visibleLines.actual_value ? 'active' : 'inactive'}`}
            onClick={() => toggleLine('actual_value')}
          >
            <span className="legend-line actual-value"></span>
            True
          </span>
          <span
            className={`legend-item ${visibleLines.predicted_value ? 'active' : 'inactive'}`}
            onClick={() => toggleLine('predicted_value')}
          >
            <span className="legend-line predicted-value"></span>
            Predicted
          </span>
          <span
            className={`legend-item ${visibleLines.anomaly_detected ? 'active' : 'inactive'}`}
            onClick={() => toggleLine('anomaly_detected')}
          >
            <span className="legend-line anomaly-detected"></span>
            Anomaly Region
          </span>
        </div>

        {trendData.length === 0 ? (
          <div className="empty-state">
            {isStreaming ? 'Waiting for data...' : 'Streaming paused'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trendData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2b30" />
              <XAxis
                dataKey="timestamp"
                type="number"
                domain={['dataMin', 'dataMax']}
                tickFormatter={formatXAxis}
                stroke="#909296"
                scale="time"
                tickCount={8}
                style={{ fontSize: '11px' }}
              />
              <YAxis
                stroke="#909296"
                label={{ value: 'Value', angle: -90, position: 'insideLeft', fill: '#909296', fontSize: 11 }}
                style={{ fontSize: '11px' }}
              />
              <Tooltip content={<CustomTooltip />} />
              {visibleLines.actual_value && (
                <Line
                  type="monotone"
                  dataKey="actual_value"
                  stroke="#1e3a8a"
                  strokeWidth={2}
                  dot={false}
                  name="True"
                  isAnimationActive={false}
                  connectNulls={true}
                />
              )}
              {visibleLines.predicted_value && (
                <Line
                  type="monotone"
                  dataKey="predicted_value"
                  stroke="#ef4444"
                  strokeWidth={2}
                  dot={false}
                  name="Predicted"
                  isAnimationActive={false}
                  connectNulls={true}
                />
              )}
              {visibleLines.anomaly_detected && (
                <Line
                  type="monotone"
                  dataKey="anomaly_detected"
                  stroke="rgba(96, 165, 250, 0.3)"
                  strokeWidth={0}
                  fill="rgba(96, 165, 250, 0.3)"
                  fillOpacity={0.3}
                  dot={false}
                  name="Anomaly"
                  isAnimationActive={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* 차트 2: 이상 점수 (Anomaly Score) */}
      <div className="chart-wrapper" style={{ marginTop: '20px' }}>
        <div className="chart-title">
          <h3>Anomaly Score</h3>
        </div>

        {anomalyScoreData.length === 0 ? (
          <div className="empty-state">
            {isStreaming ? 'Waiting for data...' : 'Streaming paused'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={anomalyScoreData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2b30" />
              <XAxis
                dataKey="timestamp"
                type="number"
                domain={['dataMin', 'dataMax']}
                tickFormatter={formatXAxis}
                stroke="#909296"
                scale="time"
                tickCount={8}
                style={{ fontSize: '11px' }}
              />
              <YAxis
                stroke="#909296"
                domain={[0, 'auto']}
                label={{ value: 'Score', angle: -90, position: 'insideLeft', fill: '#909296', fontSize: 11 }}
                style={{ fontSize: '11px' }}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                labelFormatter={(value) => format(new Date(value), 'yyyy-MM-dd HH:mm:ss')}
                formatter={(value) => [value.toFixed(4), 'Score']}
              />
              <Bar
                dataKey="anomaly_score"
                fill="#10b981"
                name="Anomaly Score"
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default TrendChart;
