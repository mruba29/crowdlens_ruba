export type RiskLevel = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED' | 'BLACK'

export interface FrameMetric {
  kind: 'frame'
  frame_idx: number
  t_offset_sec: number
  people_count: number
  density_ppm2: number
  mean_motion: number
  turbulence: number
  interpersonal_distance_m: number
  score: number
  level: RiskLevel
  label: string
  factors: { density: number; movement: number; density_increase: number; compression: number }
  contributions: { factor: string; value: number; weight: number; contribution: number }[]
  boxes: number[][]
  progress: number | null
  annotated_frame?: string
}

export interface HistoryPoint {
  t_offset_sec: number
  people_count: number
  density_ppm2: number
  mean_motion: number
  turbulence: number
  score: number
  level: RiskLevel
}

export interface Zone {
  name: string
  people: number
  density: number
  score: number
  level: RiskLevel
}

export interface AnalysisStatus {
  status: 'idle' | 'processing' | 'completed' | 'stopped' | 'error'
  video_id: string | null
  detector_backend: string | null
  started_at: number | null
  fps: number | null
  frame_count: number | null
  frames_processed: number
  error: string | null
  has_data: boolean
}

export interface Metrics {
  status: AnalysisStatus['status']
  latest: FrameMetric | null
  history: HistoryPoint[]
  zones: Zone[]
}

export interface Alert {
  id: number
  created_at: number
  zone: string
  level: RiskLevel
  score: number
  reason: string
  factors: Record<string, number>
  status: 'ACTIVE' | 'ACKNOWLEDGED'
  acknowledged_at: number | null
}

export interface Health {
  status: string
  service: string
  detector: { backend: string; available: boolean; is_yolo: boolean }
  privacy_mode: boolean
  analysis_status: string
  websocket_clients: number
}

export interface Settings {
  privacy_mode: boolean
  detection_confidence: number
  analysis_sample_every_n: number
  zone_area_m2: number
  critical_density_ppm2: number
  risk_thresholds: Record<string, number>
}

export const LEVEL_CLASS: Record<RiskLevel, string> = {
  GREEN: 'risk-green',
  YELLOW: 'risk-yellow',
  ORANGE: 'risk-orange',
  RED: 'risk-red',
  BLACK: 'risk-black',
}

export const LEVEL_HEX: Record<RiskLevel, string> = {
  GREEN: '#4ade80',
  YELLOW: '#facc15',
  ORANGE: '#fb923c',
  RED: '#f87171',
  BLACK: '#c084fc',
}
