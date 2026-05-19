import React from 'react'
import { DiagnoseResult } from '../services/api'

interface Props {
  diagnosis: DiagnoseResult
}

const typeColors: Record<string, { color: string; label: string }> = {
  KNOWN: { color: 'var(--accent-green)', label: 'KNOWN' },
  PARTIAL: { color: 'var(--accent-yellow)', label: 'PARTIAL' },
  NOVEL: { color: 'var(--accent-red)', label: 'NOVEL' },
}

const confidenceColors: Record<string, string> = {
  High: 'var(--accent-green)',
  Medium: 'var(--accent-yellow)',
  Low: 'var(--accent-red)',
}

export default function DiagnosisPanel({ diagnosis }: Props) {
  const typeInfo = typeColors[diagnosis.incident_type] || { color: 'var(--text-muted)', label: diagnosis.incident_type }

  return (
    <div>
      {/* Header metrics */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-value">{diagnosis.incident_id.slice(0, 8)}</div>
          <div className="metric-label">Incident ID</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ color: typeInfo.color, WebkitTextFillColor: typeInfo.color }}>
            {typeInfo.label}
          </div>
          <div className="metric-label">Type</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{(diagnosis.similarity_score * 100).toFixed(0)}%</div>
          <div className="metric-label">Similarity</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">${diagnosis.cost_usd.toFixed(4)}</div>
          <div className="metric-label">Cost</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{diagnosis.latency_seconds.toFixed(1)}s</div>
          <div className="metric-label">Latency</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ fontSize: 16, WebkitTextFillColor: 'var(--text-primary)' }}>
            {diagnosis.model_used.split('/').pop() || diagnosis.model_used}
          </div>
          <div className="metric-label">Model ({diagnosis.model_tier})</div>
        </div>
      </div>

      <div className="two-col">
        {/* Root Cause */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">🔍 Root Cause</span>
            <span style={{ background: `${confidenceColors[diagnosis.confidence]}22`, color: confidenceColors[diagnosis.confidence], padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600 }}>
              {diagnosis.confidence} confidence
            </span>
          </div>
          <p style={{ fontSize: 15, lineHeight: 1.6, color: 'var(--text-primary)' }}>
            {diagnosis.root_cause}
          </p>
          {diagnosis.notes && (
            <p style={{ marginTop: 12, fontSize: 13, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
              {diagnosis.notes}
            </p>
          )}
          <div style={{ marginTop: 16, fontSize: 13, color: 'var(--text-muted)' }}>
            {diagnosis.routing_reason}
          </div>
        </div>

        {/* Fix Steps */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">📋 Fix Steps</span>
          </div>
          <ol className="steps-list">
            {diagnosis.fix_steps.map((step, i) => (
              <li key={i}>
                <span className="step-number">{i + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}
