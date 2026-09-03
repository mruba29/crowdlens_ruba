import type { AnalysisStatus, Metrics, Alert, Health, Settings, RiskLevel } from './types'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText} — ${body}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => req<Health>('/health'),

  uploadVideo: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/video/upload', { method: 'POST', body: form })
    if (!res.ok) throw new Error(`upload failed: ${res.status}`)
    return res.json() as Promise<{ video_id: string; filename: string; size_bytes: number }>
  },

  startAnalysis: (video_id: string) =>
    req<AnalysisStatus>('/analysis/start', { method: 'POST', body: JSON.stringify({ video_id }) }),
  stopAnalysis: () => req<AnalysisStatus>('/analysis/stop', { method: 'POST' }),
  analysisStatus: () => req<AnalysisStatus>('/analysis/status'),

  metrics: () => req<Metrics>('/metrics'),
  zones: () => req<Metrics['zones']>('/zones'),

  alerts: (level?: RiskLevel | 'ALL') =>
    req<Alert[]>(`/alerts${level && level !== 'ALL' ? `?level=${level}` : ''}`),
  acknowledgeAlert: (id: number) => req<Alert>(`/alerts/${id}/acknowledge`, { method: 'POST' }),

  getSettings: () => req<Settings>('/settings'),
  updateSettings: (patch: Partial<Settings>) =>
    req<Settings>('/settings', { method: 'PUT', body: JSON.stringify(patch) }),
}
