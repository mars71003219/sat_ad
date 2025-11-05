import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [stats, setStats] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 10000); // 10초마다 갱신
    return () => clearInterval(interval);
  }, []);

  const fetchDashboardData = async () => {
    try {
      const [statsRes, anomaliesRes] = await Promise.all([
        axios.get('/api/dashboard/stats'),
        axios.get('/api/dashboard/anomalies?hours=24')
      ]);

      setStats(statsRes.data);
      setAnomalies(anomaliesRes.data.anomalies || []);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="App"><h2>Loading...</h2></div>;
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>Telemetry Anomaly Detection Dashboard</h1>
      </header>

      <div className="dashboard-container">
        {/* 통계 카드 */}
        <div className="stats-grid">
          <div className="stat-card">
            <h3>Total Inferences</h3>
            <p className="stat-value">{stats?.inference_stats?.total_inferences || 0}</p>
          </div>

          <div className="stat-card">
            <h3>Anomalies Detected</h3>
            <p className="stat-value anomaly">{stats?.inference_stats?.anomalies_detected || 0}</p>
          </div>

          <div className="stat-card">
            <h3>Anomaly Rate</h3>
            <p className="stat-value">{stats?.inference_stats?.anomaly_rate?.toFixed(2) || 0}%</p>
          </div>

          <div className="stat-card">
            <h3>Active Satellites</h3>
            <p className="stat-value">{stats?.active_satellites || 0} / {stats?.total_satellites || 0}</p>
          </div>
        </div>

        {/* 최근 추론 결과 */}
        <div className="section">
          <h2>Recent Inferences</h2>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Satellite</th>
                  <th>Subsystem</th>
                  <th>Batch ID</th>
                  <th>Anomaly Score</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {stats?.recent_inferences?.map((inf, idx) => (
                  <tr key={idx}>
                    <td>{inf.satellite_id}</td>
                    <td>{inf.subsystem}</td>
                    <td>{inf.batch_id?.substring(0, 20)}...</td>
                    <td className={inf.anomaly_score > 0.7 ? 'anomaly-score' : ''}>
                      {inf.anomaly_score?.toFixed(3)}
                    </td>
                    <td>{new Date(inf.timestamp * 1000).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 최근 이상 감지 */}
        <div className="section">
          <h2>Recent Anomalies (24h)</h2>
          <p>Total: {anomalies.length} anomalies detected</p>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Satellite</th>
                  <th>Subsystem</th>
                  <th>Score</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.slice(0, 10).map((anom, idx) => (
                  <tr key={idx}>
                    <td>{anom.satellite_id}</td>
                    <td>{anom.subsystem}</td>
                    <td className="anomaly-score">{anom.anomaly_score?.toFixed(3)}</td>
                    <td>{new Date(anom.timestamp * 1000).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
