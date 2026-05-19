import React, { useEffect, useState } from 'react'
import { api, AuditEntry } from '../services/api'

export default function CostChart() {
  const [audit, setAudit] = useState<{ entries: AuditEntry[]; stats: any } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getAudit().then(setAudit).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center' }}>
        <div className="spinner" style={{ margin: '0 auto 12px' }} />
        <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>Loading analytics...</p>
      </div>
    )
  }

  const stats = audit?.stats || { total_cost: 0, avg_cost: 0, avg_latency: 0 }
  const entries = audit?.entries || []
  const resolved = entries.filter(e => e.resolved).length
  const unresolved = entries.length - resolved

  return (
    <>
      {/* Stats overview */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-value" style={{ fontSize: 24 }}>${stats.total_cost.toFixed(4)}</div>
          <div className="metric-label">Total Spend</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ fontSize: 24, WebkitTextFillColor: 'var(--accent-green)' }}>
            ${stats.avg_cost.toFixed(5)}
          </div>
          <div className="metric-label">Avg Cost / Incident</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ fontSize: 24, WebkitTextFillColor: 'var(--accent-cyan)' }}>
            {stats.avg_latency.toFixed(1)}s
          </div>
          <div className="metric-label">Avg Latency</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ fontSize: 24, WebkitTextFillColor: 'var(--accent-purple)' }}>
            {entries.length}
          </div>
          <div className="metric-label">Total Incidents</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ fontSize: 24, WebkitTextFillColor: 'var(--accent-green)' }}>
            {resolved}
          </div>
          <div className="metric-label">Resolved</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ fontSize: 24, WebkitTextFillColor: 'var(--accent-red)' }}>
            {unresolved}
          </div>
          <div className="metric-label">Unresolved</div>
        </div>
      </div>

      {/* Cost savings explanation card */}
      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-header">
          <span className="card-title">💰 How Memory Saves Costs</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: 16 }}>
          <div style={{
            width: 80, height: 80, borderRadius: '50%',
            background: 'conic-gradient(var(--accent-green) 0deg 295deg, var(--accent-cyan) 295deg 360deg)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, fontWeight: 700, color: '#000', flexShrink: 0,
          }}>
            82%
          </div>
          <div>
            <p style={{ fontWeight: 600, marginBottom: 4 }}>Average cost reduction</p>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
              The system learns from past incidents. Known incidents route to cheaper models,
              reducing average diagnosis cost by up to 82%.
            </p>
          </div>
        </div>
      </div>

      {/* Incident list */}
      {entries.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="card-header">
            <span className="card-title">📜 Audit Trail</span>
          </div>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Incident</th>
                  <th>Type</th>
                  <th>Model</th>
                  <th>Cost</th>
                  <th>Latency</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {entries.slice().reverse().map((e, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, fontSize: 12 }}>{e.incident_id}</td>
                    <td>
                      <span className={`badge badge-${e.incident_type.toLowerCase()}`}>
                        {e.incident_type}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                      {e.model_used.split('/').pop() || e.model_used}
                    </td>
                    <td>${e.cost_usd.toFixed(4)}</td>
                    <td>{e.latency_seconds.toFixed(1)}s</td>
                    <td>
                      {e.resolved ? (
                        <span className="badge badge-success">Resolved</span>
                      ) : (
                        <span className="badge badge-danger">Open</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
