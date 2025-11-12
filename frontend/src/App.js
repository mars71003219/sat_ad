import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import TrendChart from './components/TrendChart';
import './App.css';

function App() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedSatellite, setSelectedSatellite] = useState('sat1');
  const [selectedSubsystem, setSelectedSubsystem] = useState('EPS');
  const [selectedFeatureIndex, setSelectedFeatureIndex] = useState(null);
  const [recentInferences, setRecentInferences] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // WebSocket 연결 설정
  useEffect(() => {
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 필터 변경 시 WebSocket으로 전송
  useEffect(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const filters = {
        satellite_id: selectedSatellite,
        subsystem: selectedSubsystem,
        feature_index: selectedFeatureIndex
      };
      console.log('Sending filters to WebSocket:', filters);
      wsRef.current.send(JSON.stringify(filters));
    } else {
      console.log('WebSocket not ready. State:', wsRef.current?.readyState);
    }
  }, [selectedSatellite, selectedSubsystem, selectedFeatureIndex]);

  const connectWebSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/dashboard`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setWsConnected(true);

        // 현재 필터 전송
        const filters = {
          satellite_id: selectedSatellite,
          subsystem: selectedSubsystem,
          feature_index: selectedFeatureIndex
        };
        ws.send(JSON.stringify(filters));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'inferences') {
          setRecentInferences(data.data || []);
        } else if (data.type === 'error') {
          console.error('WebSocket error:', data.message);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setWsConnected(false);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setWsConnected(false);

        // 5초 후 재연결 시도
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect...');
          connectWebSocket();
        }, 5000);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      setWsConnected(false);
    }
  };

  // 초기 데이터 로드 (통계는 3초마다 업데이트)
  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 3000);
    return () => clearInterval(interval);
  }, []);

  const fetchDashboardData = async () => {
    try {
      const statsRes = await axios.get('/api/dashboard/stats');
      setStats(statsRes.data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      setLoading(false);
    }
  };

  const handleFilterChange = (satellite, subsystem, featureIndex) => {
    console.log('handleFilterChange called:', { satellite, subsystem, featureIndex });
    setSelectedSatellite(satellite);
    setSelectedSubsystem(subsystem);
    // featureIndex가 null이면 "All Features"가 선택된 것
    setSelectedFeatureIndex(featureIndex);
  };

  // 센서 이름을 읽기 쉽게 변환
  const formatSensorName = (featureName) => {
    if (!featureName || featureName === 'N/A') return '-';

    // satellite_ 접두사 제거
    let name = featureName.replace('satellite_', '');

    // 언더스코어를 공백으로 변경하고 각 단어의 첫 글자를 대문자로
    name = name.split('_').map(word =>
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ');

    // 약어를 대문자로 변경
    name = name.replace(/\bSoc\b/g, 'SOC');
    name = name.replace(/\bObc\b/g, 'OBC');
    name = name.replace(/\bComm\b/g, 'Comm');
    name = name.replace(/\bRssi\b/g, 'RSSI');
    name = name.replace(/\bRpm\b/g, 'RPM');
    name = name.replace(/\bTemp\b/g, 'Temperature');

    return name;
  };

  if (loading) {
    return <div className="App"><h2>Loading...</h2></div>;
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>Telemetry Anomaly Detection Dashboard</h1>
        <div style={{
          position: 'absolute',
          right: '20px',
          top: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '12px',
          color: wsConnected ? '#4ade80' : '#ef4444'
        }}>
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: wsConnected ? '#4ade80' : '#ef4444',
            animation: wsConnected ? 'pulse 2s infinite' : 'none'
          }}></div>
          {wsConnected ? 'Live' : 'Disconnected'}
        </div>
      </header>

      <div className="dashboard-container">
        {/* 통계 카드 */}
        <div className="stats-grid">
          <div className="stat-card compact">
            <div className="stat-label">Total Inferences</div>
            <div className="stat-value">{stats?.inference_stats?.total_inferences || 0}</div>
          </div>

          <div className="stat-card compact">
            <div className="stat-label">Anomalies Detected</div>
            <div className="stat-value anomaly">{stats?.inference_stats?.anomalies_detected || 0}</div>
          </div>

          <div className="stat-card compact">
            <div className="stat-label">Anomaly Rate</div>
            <div className="stat-value">{Math.min(stats?.inference_stats?.anomaly_rate || 0, 100).toFixed(2)}%</div>
          </div>

          <div className="stat-card compact">
            <div className="stat-label">Active Satellites</div>
            <div className="stat-value">{stats?.active_satellites || 0} / {stats?.total_satellites || 0}</div>
          </div>

          <div className="stat-card compact highlight">
            <div className="stat-label">Selected Satellite</div>
            <div className="stat-value selected">{selectedSatellite || 'None'}</div>
          </div>
        </div>

        {/* 트렌드 차트 */}
        <TrendChart onFilterChange={handleFilterChange} />

        {/* 최근 추론 결과 */}
        <div className="section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 style={{ margin: 0 }}>Recent Inferences</h2>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Satellite</th>
                  <th>Subsystem</th>
                  <th>Sensor</th>
                  <th>Actual Value</th>
                  <th>Predicted Value</th>
                  <th>Anomaly Score</th>
                  <th>Timestamp</th>
                  <th>Alarm</th>
                </tr>
              </thead>
              <tbody>
                {recentInferences.length > 0 ? (
                  recentInferences.map((inf, idx) => {
                    // Alarm 판단: anomaly_score > 0.7이면 이상
                    const isAlarm = inf.anomaly_score > 0.7;
                    const sensorName = formatSensorName(inf.feature_name);

                    // 디버깅용 로그 (첫 번째 항목만)
                    if (idx === 0) {
                      console.log('Recent Inference Data:', {
                        feature_name: inf.feature_name,
                        formatted: sensorName,
                        full_object: inf
                      });
                    }

                    return (
                      <tr key={idx}>
                        <td>{inf.satellite_id}</td>
                        <td>{inf.subsystem}</td>
                        <td style={{ fontSize: '11px', color: '#c1c2c5' }}>
                          {sensorName}
                        </td>
                        <td>{inf.actual_value !== null ? inf.actual_value.toFixed(3) : '-'}</td>
                        <td>{inf.predicted_value !== null ? inf.predicted_value.toFixed(3) : '-'}</td>
                        <td className={isAlarm ? 'anomaly-score' : ''}>
                          {inf.anomaly_score?.toFixed(3)}
                        </td>
                        <td>{new Date(inf.timestamp * 1000).toLocaleString()}</td>
                        <td>
                          <span className={`alarm-indicator ${isAlarm ? 'alarm' : 'normal'}`}></span>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan="8" style={{textAlign: 'center', color: '#a0a0a0'}}>
                      No data available
                      {selectedSatellite && ` for ${selectedSatellite}`}
                      {selectedSubsystem && ` / ${selectedSubsystem}`}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
