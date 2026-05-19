import React, { useEffect, useState } from 'react'
import { api, HistoryEntry } from '../services/api'

interface Props {
  incidents?: HistoryEntry[]
}

export default function IncidentTable({ incidents: _ }: Props) {
  const [history, setHistory] = useState<{ incidents: HistoryEntry[]; total: number } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getHistory()
      .then(setHistory)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center' }}>
        <div className="spinner" style={{ margin: '0 auto 12px' }} />
        <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>Loading history...</p>
      </div>
    )
  }

  const incidents = history?.incidents || []

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">📋 Incident History</span>
        <span className="badge badge-known">{history?.total || 0} total</span>
      </div>

      {incidents.length === 0 ? (
        <div className="warning-state" style={{ marginTop: 12 }}>
          <span>💡</span>
          <span>No incidents in memory yet. Run a diagnosis first!</span>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Root Cause</th>
                <th>Service</th>
                <th>Model</th>
                <th>Cost</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {incidents.slice().reverse().map((inc, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600, fontSize: 12, color: 'var(--accent-cyan)' }}>
                    {inc.incident_id}
                  </td>
                  <td>
                    <span className={`badge badge-${inc.incident_type.toLowerCase()}`}>
                      {inc.incident_type}
                    </span>
                  </td>
                  <td style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {inc.root_cause}
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>{inc.service}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {inc.model_used.split('/').pop() || inc.model_used}
                  </td>
                  <td>${inc.cost_usd.toFixed(4)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {new Date(inc.timestamp).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      <div style={{ marginTop: 16, display: 'flex', gap: 24, fontSize: 13, color: 'var(--text-secondary)' }}>
        <span>Total: <strong style={{ color: 'var(--text-primary)' }}>{incidents.length}</strong></span>
        <span>
          Known: <strong style={{ color: 'var(--accent-green)' }}>
            {incidents.filter(i => i.incident_type === 'KNOWN').length}
          </strong>
        </span>
        <span>
          Novel: <strong style={{ color: 'var(--accent-red)' }}>
            {incidents.filter(i => i.incident_type === 'NOVEL').length}
          </strong>
        </span>
        <span>
          Total cost: <strong style={{ color: 'var(--text-primary)' }}>
            ${incidents.reduce((s, i) => s + i.cost_usd, 0).toFixed(4)}
          </strong>
        </span>
      </div>
    </div>
  )
}
