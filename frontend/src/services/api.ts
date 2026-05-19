const API_BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export interface DiagnoseResult {
  incident_id: string;
  incident_type: string;
  similarity_score: number;
  root_cause: string;
  confidence: string;
  fix_steps: string[];
  notes: string;
  model_used: string;
  model_tier: string;
  cost_usd: number;
  latency_seconds: number;
  routing_reason: string;
}

export interface FixTask {
  id: string;
  description: string;
  change_type: string;
  file_path: string;
  status: string;
  priority: number;
}

export interface PlanResult {
  incident_id: string;
  branch_name: string;
  pr_title: string;
  tasks: FixTask[];
  summary: string;
}

export interface ApplyResult {
  success: boolean;
  applied: number;
  failed: number;
  test_tasks_generated: number;
}

export interface ValidateResult {
  passed: boolean;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  errors: string[];
  output: string;
}

export interface PRResult {
  success: boolean;
  branch_url: string;
  pr_url: string;
  pr_number: number | null;
  error: string | null;
}

export interface DemoPreset {
  id: string;
  title: string;
  error_log: string;
  service: string;
}

export interface HistoryEntry {
  incident_id: string;
  incident_type: string;
  root_cause: string;
  service: string;
  fix_applied: string;
  resolution_time_minutes: number;
  model_used: string;
  cost_usd: number;
  timestamp: string;
}

export interface AuditEntry {
  incident_id: string;
  incident_type: string;
  root_cause: string;
  model_used: string;
  cost_usd: number;
  latency_seconds: number;
  timestamp: string;
  resolved: boolean;
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  diagnose: (errorLog: string, useLlm: boolean = true) =>
    request<DiagnoseResult>('/diagnose', {
      method: 'POST',
      body: JSON.stringify({ error_log: errorLog, use_llm: useLlm }),
    }),

  remediatePlan: (params: {
    incident_id: string;
    root_cause: string;
    fix_steps: string[];
    incident_type?: string;
  }) =>
    request<PlanResult>('/remediate/plan', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  remediateRun: (
    params: {
      incident_id: string;
      root_cause: string;
      fix_steps: string[];
      incident_type?: string;
    },
    onEvent: (event: string, data: any) => void
  ): Promise<void> => {
    return new Promise((resolve, reject) => {
      fetch(`${API_BASE}/remediate/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      }).then(async (response) => {
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          reject(new Error(err.detail || 'Remediation failed'));
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          reject(new Error('No response body'));
          return;
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let currentEvent = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              const dataStr = line.slice(6);
              try {
                const data = JSON.parse(dataStr);
                onEvent(currentEvent || 'message', data);
              } catch {
                // ignore parse errors
              }
            }
          }
        }
        resolve();
      }).catch(reject);
    });
  },

  getDemoPresets: () =>
    request<{ presets: DemoPreset[] }>('/demo/presets'),

  getHistory: () =>
    request<{ incidents: HistoryEntry[]; total: number }>('/history'),

  getAudit: () =>
    request<{
      entries: AuditEntry[];
      total: number;
      stats: { total_cost: number; avg_cost: number; avg_latency: number };
    }>('/audit'),
};
