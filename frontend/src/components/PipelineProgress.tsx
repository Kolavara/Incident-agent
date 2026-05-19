import React from 'react'

interface PipelineEvent {
  event: string
  data: any
  timestamp: number
}

interface Props {
  events: PipelineEvent[]
  isRunning: boolean
  onStart: () => void
  disabled: boolean
}

const STEPS = [
  { key: 'plan', label: 'Plan', icon: '📋' },
  { key: 'apply', label: 'Fix', icon: '🔧' },
  { key: 'test', label: 'Test', icon: '🧪' },
  { key: 'validate', label: 'Validate', icon: '✅' },
  { key: 'pr', label: 'PR', icon: '🚀' },
]

export default function PipelineProgress({ events, isRunning, onStart, disabled }: Props) {
  const isStepDone = (key: string): boolean => {
    if (key === 'plan') return events.some(e => e.event === 'plan')
    if (key === 'apply') return events.some(e => e.event === 'apply')
    if (key === 'test') return events.some(e => e.event === 'apply' && e.data?.test_tasks_generated > 0)
    if (key === 'validate') return events.some(e => e.event === 'validate')
    if (key === 'pr') return events.some(e => e.event === 'pr')
    return false
  }

  const getStepStatus = (stepKey: string): 'idle' | 'active' | 'done' | 'error' => {
    if (events.some(e => e.event === 'error')) return 'error'
    if (isStepDone(stepKey)) return 'done'

    const stepIndex = STEPS.findIndex(s => s.key === stepKey)
    let lastDoneIndex = -1
    for (let i = 0; i < STEPS.length; i++) {
      if (isStepDone(STEPS[i].key)) lastDoneIndex = i
    }

    if (stepIndex === lastDoneIndex + 1 && isRunning) return 'active'
    if (stepIndex <= lastDoneIndex) return 'done'
    return 'idle'
  }

  const lastStepEvent = events[events.length - 1]
  const currentStep = lastStepEvent && isRunning
    ? STEPS.find(s => s.key === lastStepEvent.event)?.label || 'Processing'
    : events.some(e => e.event === 'complete') ? 'Complete!' : ''

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">🚀 Remediation Pipeline</span>
        {!isRunning && !events.length && (
          <button className="btn btn-primary" onClick={onStart} disabled={disabled}>
            ▶ Run Full Pipeline
          </button>
        )}
      </div>

      {/* Pipeline steps */}
      <div className="pipeline">
        {STEPS.map((step, i) => {
          const status = getStepStatus(step.key)
          return (
            <React.Fragment key={step.key}>
              <div className={`pipeline-step ${status}`}>
                <span>{step.icon}</span>
                <span>{step.label}</span>
                {status === 'active' && <span className="spinner" style={{ width: 14, height: 14 }} />}
                {status === 'done' && <span>✓</span>}
              </div>
              {i < STEPS.length - 1 && <span className="pipeline-arrow">→</span>}
            </React.Fragment>
          )
        })}
      </div>

      {/* Current status */}
      {isRunning && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', color: 'var(--accent-cyan)', fontSize: 14 }}>
          <span className="spinner" />
          <span>{currentStep}...</span>
        </div>
      )}

      {/* Results table */}
      {events.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <table>
            <thead>
              <tr>
                <th>Step</th>
                <th>Status</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {events.filter(e => e.event !== 'step' && e.event !== 'complete').map((evt, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{evt.event}</td>
                  <td>
                    {evt.event === 'error' ? (
                      <span className="badge badge-danger">FAILED</span>
                    ) : (
                      <span className="badge badge-success">PASSED</span>
                    )}
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                    {renderEventData(evt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Error state */}
      {events.some(e => e.event === 'error') && (
        <div className="error-state" style={{ marginTop: 16 }}>
          <span style={{ fontSize: 32 }}>❌</span>
          <p>Pipeline failed. Check the logs for details.</p>
          <button className="btn btn-secondary btn-sm" onClick={onStart}>Retry</button>
        </div>
      )}
    </div>
  )
}

function renderEventData(evt: PipelineEvent): string {
  const d = evt.data
  switch (evt.event) {
    case 'plan':
      return `${d.tasks?.length || 0} tasks · ${d.branch_name || ''}`
    case 'apply':
      return `${d.applied || 0} applied · ${d.failed || 0} failed · ${d.test_tasks_generated || 0} tests`
    case 'validate':
      return `${d.passed_tests || 0}/${d.total_tests || 0} tests passed`
    case 'pr':
      return d.success ? `PR ready · ${d.pr_url || d.branch_url || 'local branch'}` : `Error: ${d.error || 'unknown'}`
    default:
      return JSON.stringify(d).slice(0, 80)
  }
}
