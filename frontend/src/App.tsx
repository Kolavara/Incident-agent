import React, { useState, useEffect } from 'react'
import { api, DiagnoseResult } from './services/api'
import DiagnosisPanel from './components/DiagnosisPanel'
import PipelineProgress from './components/PipelineProgress'
import CostChart from './components/CostChart'
import IncidentTable from './components/IncidentTable'

type Page = 'home' | 'diagnosis' | 'analytics'

function App() {
  const [page, setPage] = useState<Page>('home')
  const [errorLog, setErrorLog] = useState('')
  const [loading, setLoading] = useState(false)
  const [diagnosis, setDiagnosis] = useState<DiagnoseResult | null>(null)
  const [remediating, setRemediating] = useState(false)
  const [pipelineEvents, setPipelineEvents] = useState<any[]>([])
  const [presets, setPresets] = useState<any[]>([])
  const [useLlm, setUseLlm] = useState(true)

  useEffect(() => {
    api.getDemoPresets().then(d => setPresets(d.presets)).catch(() => {})
  }, [])

  const handleDiagnose = async (log?: string) => {
    const input = log || errorLog
    if (!input || input.length < 20) return
    setLoading(true)
    setDiagnosis(null)
    setPipelineEvents([])
    try {
      const result = await api.diagnose(input, useLlm)
      setDiagnosis(result)
      setPage('diagnosis')
    } catch (e: any) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleRemediate = async () => {
    if (!diagnosis) return
    setRemediating(true)
    setPipelineEvents([])
    try {
      await api.remediateRun(
        {
          incident_id: diagnosis.incident_id,
          root_cause: diagnosis.root_cause,
          fix_steps: diagnosis.fix_steps,
          incident_type: diagnosis.incident_type,
        },
        (event, data) => {
          setPipelineEvents(prev => [...prev, { event, data, timestamp: Date.now() }])
        }
      )
    } catch (e: any) {
      alert(e.message)
    } finally {
      setRemediating(false)
    }
  }

  const handlePreset = (preset: any) => {
    setErrorLog(preset.error_log)
    handleDiagnose(preset.error_log)
  }

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-logo">
          <span className="shield">🛡️</span>
          <span>Incident Agent</span>
        </div>
        <nav className="header-nav">
          <a href="#" className={page === 'home' ? 'active' : ''} onClick={() => setPage('home')}>Home</a>
          {diagnosis && (
            <a href="#" className={page === 'diagnosis' ? 'active' : ''} onClick={() => setPage('diagnosis')}>Diagnosis</a>
          )}
          <a href="#" className={page === 'analytics' ? 'active' : ''} onClick={() => setPage('analytics')}>Analytics</a>
        </nav>
      </header>

      {/* Pages */}
      {page === 'home' && (
        <div className="animate-fade-in">
          <div className="two-col">
            {/* Left: Input */}
            <div>
              <div className="card" style={{ minHeight: 400 }}>
                <div className="card-header">
                  <span className="card-title">📥 Paste Error Log</span>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-secondary)' }}>
                    <input type="checkbox" checked={useLlm} onChange={e => setUseLlm(e.target.checked)} />
                    Use LLM
                  </label>
                </div>
                <textarea
                  className="textarea"
                  placeholder={`Paste an error log here...\n\ne.g.:\n[ERROR] 2025-03-15 14:32:11 - redis.exceptions.ConnectionPool: Connection pool exhausted. Max size: 10, current connections: 10\n  File "/app/payment_processor.py", line 142, in process_payment\n    redis_client.setex(f"session:{session_id}", 3600, session_data)`}
                  value={errorLog}
                  onChange={e => setErrorLog(e.target.value)}
                />
                <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
                  <button className="btn btn-primary" onClick={() => handleDiagnose()} disabled={loading || errorLog.length < 20}>
                    {loading ? <><span className="spinner" /> Diagnosing...</> : '🔍 Diagnose'}
                  </button>
                </div>
              </div>
            </div>

            {/* Right: Quick Demo */}
            <div>
              <div className="card" style={{ minHeight: 400 }}>
                <div className="card-header">
                  <span className="card-title">⚡ Quick Demo</span>
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 16 }}>
                  Click a preset incident to see the agent in action:
                </p>
                <div className="presets-grid">
                  {presets.map((p, i) => (
                    <button key={i} className="preset-btn" onClick={() => handlePreset(p)} disabled={loading}>
                      <span className="preset-service">{p.service}</span>
                      <span>{p.title}</span>
                    </button>
                  ))}
                </div>
                <div className="warning-state" style={{ marginTop: 24 }}>
                  <span>💡</span>
                  <span>No API keys needed for demo — uses offline simulation</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {page === 'diagnosis' && diagnosis && (
        <div className="animate-fade-in">
          <DiagnosisPanel diagnosis={diagnosis} />

          <div style={{ marginTop: 24 }}>
            <PipelineProgress
              events={pipelineEvents}
              isRunning={remediating}
              onStart={handleRemediate}
              disabled={remediating}
            />
          </div>

          {pipelineEvents.filter(e => e.event === 'apply').length > 0 && (
            <div style={{ marginTop: 24 }}>
              <IncidentTable />
            </div>
          )}
        </div>
      )}

      {page === 'analytics' && (
        <div className="animate-fade-in">
          <CostChart />
          <div style={{ marginTop: 24 }}>
            <IncidentTable />
          </div>
        </div>
      )}
    </div>
  )
}

export default App
