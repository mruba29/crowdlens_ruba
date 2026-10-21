import type {
  AnalysisStatus, Metrics, Alert, Health, Settings, RiskLevel, VideoRecord,
  CrowdEvent, EventDetail, EventZone, EventCamera, EventVideoSource, TimelineEntry, SourceType,
  ZoneMetrics, ValidationSample, ValidationSummary, DynamicsSignals, DynamicsEvent, SRIResult,
  Incident, PredictiveForecast, SampleVideo,
} from './types'

// Local dev uses the Vite proxy at /api and /ml. In a hosted build set
// VITE_API_BASE (e.g. /api or https://backend.domain/api) and
// VITE_ML_API_BASE (e.g. /ml or https://ml.domain/ml)
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || '/api'
export const ML_API_BASE = (import.meta.env.VITE_ML_API_BASE as string | undefined)?.replace(/\/$/, '') || '/ml'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
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
  mlHealth: async () => {
    const res = await fetch(`${ML_API_BASE}/health`)
    if (!res.ok) throw new Error(`ML health check failed: ${res.status}`)
    return res.json()
  },

  uploadVideo: async (file: File, category?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (category) form.append('category', category)
    const res = await fetch(`${API_BASE}/video/upload`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(`upload failed: ${res.status}`)
    return res.json() as Promise<VideoRecord & { video_id: string }>
  },

  batchUploadVideos: async (files: File[], category?: string) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    if (category) form.append('category', category)
    const res = await fetch(`${API_BASE}/videos/batch-upload`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(`batch upload failed: ${res.status}`)
    return res.json() as Promise<{ uploaded: (VideoRecord & { video_id: string })[]; errors: string[]; count: number }>
  },

  // ---- crowd video library (Crowd Videos page + dashboard camera cards) ----
  listVideos: () => req<VideoRecord[]>('/videos'),
  getVideo: (id: string) => req<VideoRecord>(`/videos/${id}`),
  deleteVideo: (id: string) => req<{ ok: boolean }>(`/videos/${id}`, { method: 'DELETE' }),
  updateVideo: (id: string, patch: { filename?: string; category?: string }) =>
    req<VideoRecord>(`/videos/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  videoCategories: () => req<string[]>('/videos/categories'),
  /** Direct URL to stream/play back an uploaded file (served by the backend's /uploads mount). */
  videoUrl: (id: string) => `${API_BASE.replace(/\/api$/, '')}/uploads/${id}`,

  // ---- sample video library (7 event categories + research datasets) ----
  listSamples: () => req<SampleVideo[]>('/samples'),
  importSample: (sample_id: string) =>
    req<{ ok: boolean; video: VideoRecord; message?: string }>('/samples/import', {
      method: 'POST',
      body: JSON.stringify({ sample_id }),
    }),

  startAnalysis: (video_id: string) =>
    req<AnalysisStatus>('/analysis/start', { method: 'POST', body: JSON.stringify({ video_id }) }),
  batchStartAnalysis: (video_ids: string[]) =>
    req<AnalysisStatus>('/analysis/batch-start', { method: 'POST', body: JSON.stringify({ video_ids }) }),
  pauseAnalysis: () => req<AnalysisStatus>('/analysis/pause', { method: 'POST' }),
  resumeAnalysis: () => req<AnalysisStatus>('/analysis/resume', { method: 'POST' }),
  replayAnalysis: (video_id: string) =>
    req<AnalysisStatus>('/analysis/replay', { method: 'POST', body: JSON.stringify({ video_id }) }),
  cancelAnalysis: (video_id: string) =>
    req<AnalysisStatus>(`/analysis/cancel/${video_id}`, { method: 'POST' }),
  analysisQueue: () => req<string[]>('/analysis/queue'),
  stopAnalysis: () => req<AnalysisStatus>('/analysis/stop', { method: 'POST' }),
  analysisStatus: () => req<AnalysisStatus>('/analysis/status'),

  metrics: () => req<Metrics>('/metrics'),
  zones: () => req<Metrics['zones']>('/zones'),

  alerts: (level?: RiskLevel | 'ALL') =>
    req<Alert[]>(`/alerts${level && level !== 'ALL' ? `?level=${level}` : ''}`),
  acknowledgeAlert: (id: number) => req<Alert>(`/alerts/${id}/acknowledge`, { method: 'POST' }),

  // ---- incidents management ----
  listIncidents: (status?: string) =>
    req<Incident[]>(`/incidents${status && status !== 'ALL' ? `?status=${status}` : ''}`),
  createIncident: (payload: { zone: string; title: string; severity?: string; description?: string; recommended_action?: string; alert_id?: number; video_id?: string }) =>
    req<Incident>('/incidents', { method: 'POST', body: JSON.stringify(payload) }),
  updateIncident: (id: number, patch: { status: string; operator_notes?: string }) =>
    req<Incident>(`/incidents/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  // ---- predictive risk forecast ----
  predictiveForecast: () => req<PredictiveForecast>('/predictive/forecast'),

  getSettings: () => req<Settings>('/settings'),
  updateSettings: (patch: Partial<Settings>) =>
    req<Settings>('/settings', { method: 'PUT', body: JSON.stringify(patch) }),

  // ---- Phase 1: events / cameras / zones / video sources / timeline ----
  listEvents: () => req<CrowdEvent[]>('/events'),
  createEvent: (payload: { name: string; event_type: string; location?: string
    start_time?: number | null; end_time?: number | null; crowd_context?: string }) =>
    req<CrowdEvent>('/events', { method: 'POST', body: JSON.stringify(payload) }),
  getEvent: (id: string) => req<EventDetail>(`/events/${id}`),
  updateEvent: (id: string, patch: Partial<CrowdEvent>) =>
    req<CrowdEvent>(`/events/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteEvent: (id: string) => req<{ ok: boolean }>(`/events/${id}`, { method: 'DELETE' }),

  createZone: (eventId: string, payload: Partial<EventZone> & { name: string }) =>
    req<EventZone>(`/events/${eventId}/zones`, { method: 'POST', body: JSON.stringify(payload) }),
  updateZone: (id: string, patch: Partial<EventZone>) =>
    req<EventZone>(`/zones/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteZone: (id: string) => req<{ ok: boolean }>(`/zones/${id}`, { method: 'DELETE' }),

  createCamera: (eventId: string, payload: Partial<EventCamera> & { name: string }) =>
    req<EventCamera>(`/events/${eventId}/cameras`, { method: 'POST', body: JSON.stringify(payload) }),
  updateCamera: (id: string, patch: Partial<EventCamera>) =>
    req<EventCamera>(`/cameras/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteCamera: (id: string) => req<{ ok: boolean }>(`/cameras/${id}`, { method: 'DELETE' }),

  attachVideo: (eventId: string, videoId: string, payload: {
    camera_id?: string | null; zone_id?: string | null; source_type?: SourceType
    capture_start_ts?: number | null; inflow_direction?: 'left' | 'right' }) =>
    req<EventVideoSource>(`/events/${eventId}/videos/${videoId}/attach`,
      { method: 'POST', body: JSON.stringify(payload) }),
  detachVideo: (eventId: string, videoId: string) =>
    req<{ ok: boolean }>(`/events/${eventId}/videos/${videoId}`, { method: 'DELETE' }),
  listEventVideos: (eventId: string) => req<EventVideoSource[]>(`/events/${eventId}/videos`),

  /** Upload a new file straight into an event with full source context, in one step. */
  uploadEventVideo: async (eventId: string, file: File, opts: {
    camera_id?: string | null; zone_id?: string | null; source_type?: SourceType
    capture_start_ts?: number | null; inflow_direction?: 'left' | 'right'; category?: string
  }) => {
    const form = new FormData()
    form.append('file', file)
    if (opts.camera_id) form.append('camera_id', opts.camera_id)
    if (opts.zone_id) form.append('zone_id', opts.zone_id)
    if (opts.source_type) form.append('source_type', opts.source_type)
    if (opts.capture_start_ts != null) form.append('capture_start_ts', String(opts.capture_start_ts))
    if (opts.inflow_direction) form.append('inflow_direction', opts.inflow_direction)
    if (opts.category) form.append('category', opts.category)
    const res = await fetch(`${API_BASE}/events/${eventId}/upload`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(`upload failed: ${res.status}`)
    return res.json() as Promise<EventVideoSource>
  },

  eventTimeline: (eventId: string, t: number) =>
    req<TimelineEntry[]>(`/events/${eventId}/timeline?t=${t}`),

  // ---- Phase 2: zone-aware crowd analytics + AI-vs-manual validation ----
  zoneMetrics: () => req<ZoneMetrics>('/analysis/zone-metrics'),

  addValidationSample: (payload: {
    video_id: string; zone_id?: string | null; zone_name?: string | null
    ai_count?: number | null; manual_count?: number | null
    ai_density?: number | null; manual_density?: number | null
    ai_inflow_rate?: number | null; manual_inflow_rate?: number | null
    ai_outflow_rate?: number | null; manual_outflow_rate?: number | null
    note?: string
  }) => req<ValidationSample>('/validation/samples', { method: 'POST', body: JSON.stringify(payload) }),
  listValidationSamples: (videoId?: string) =>
    req<ValidationSample[]>(`/validation/samples${videoId ? `?video_id=${videoId}` : ''}`),
  validationSummary: (videoId?: string) =>
    req<ValidationSummary>(`/validation/summary${videoId ? `?video_id=${videoId}` : ''}`),

  // ---- Phase 3: crowd dynamics ----
  dynamics: () => req<DynamicsSignals>('/analysis/dynamics'),
  dynamicsEvents: (videoId: string) => req<DynamicsEvent[]>(`/dynamics/events?video_id=${videoId}`),

  // ---- Phase 4: demographic vulnerability + the Crowd Risk Engine ----
  sri: () => req<SRIResult>('/analysis/sri'),
}
