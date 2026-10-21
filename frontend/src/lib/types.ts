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
  /** Present only for frames where the video was attached to an event zone —
   * powers the zone-aware charts (density/occupancy/inflow-outflow/flow
   * imbalance vs time). Absent, not zeroed, when not applicable. */
  zone_metrics?: ZoneMetrics
  /** Present on every frame of an active analysis (zone-attached or not) —
   * powers the Crowd Dynamics module. */
  dynamics?: DynamicsSignals
  /** Present on every frame — the Phase 4 risk engine. */
  sri?: SRIResult
}

export interface Zone {
  name: string
  people: number
  density: number
  score: number
  level: RiskLevel
}

export interface AnalysisStatus {
  status: 'idle' | 'processing' | 'paused' | 'completed' | 'stopped' | 'error'
  video_id: string | null
  detector_backend: string | null
  started_at: number | null
  fps: number | null
  frame_count: number | null
  frames_processed: number
  error: string | null
  has_data: boolean
  is_paused?: boolean
  queue_length?: number
  queue?: string[]
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
  /** Phase 4: which of the 10 early-warning types fired, its recommended
   * operator action, and the video it came from — null on older/legacy
   * alerts raised before these columns existed. */
  alert_type: string | null
  recommended_action: string | null
  video_id: string | null
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

// A human label for each level — used on Crowd Videos cards ("High Risk" etc.)
export const LEVEL_RISK_LABEL: Record<RiskLevel, string> = {
  GREEN: 'Normal',
  YELLOW: 'Moderate Risk',
  ORANGE: 'High Risk',
  RED: 'Critical Risk',
  BLACK: 'Emergency',
}

export type VideoStatus = 'uploaded' | 'queued' | 'processing' | 'paused' | 'completed' | 'stopped' | 'error' | 'failed'

export interface VideoRecord {
  id: string
  filename: string
  category: string
  uploaded_at: number
  size_bytes: number | null
  duration_sec: number | null
  thumbnail: string | null
  status: VideoStatus
  last_people: number | null
  last_density: number | null
  last_score: number | null
  last_level: RiskLevel | null
  last_analyzed_at: number | null
  metrics_summary?: {
    history?: HistoryPoint[]
    zones?: Zone[]
    dynamics?: DynamicsSignals
    sri?: SRIResult
    frames_processed?: number
    peak_people?: number
    peak_density?: number
    avg_people?: number
    avg_density?: number
    max_score?: number
    final_level?: RiskLevel
    flow_imbalance?: number
    accumulation_rate?: number
    mean_velocity?: number
    people_timeline?: { t_offset_sec: number; people_count: number; density_ppm2?: number; score?: number; level?: RiskLevel }[]
    zone_distribution?: { name: string; count: number; pct: number }[]
  } | null
}

export const VIDEO_CATEGORIES = [
  'Temple/Festival', 'Stadium', 'Concert', 'Public Gathering', 'Transport Hub', 'Procession', 'Protest', 'Other',
] as const

export interface Incident {
  id: number
  created_at: number
  alert_id: number | null
  video_id: string | null
  zone: string
  severity: RiskLevel | string
  title: string
  description: string | null
  status: 'OPEN' | 'INVESTIGATING' | 'DISPATCHED' | 'RESOLVED'
  recommended_action: string | null
  operator_notes: string | null
  resolved_at: number | null
}

export interface ProjectionPoint {
  minutes_ahead: number
  projected_density_ppm2: number
  projected_people: number
  projected_risk_score: number
  projected_level: RiskLevel
  critical_exceeded: boolean
}

export interface ScenarioModel {
  name: string
  type: 'observed' | 'modelled'
  description: string
  inflow_change_pct: number
  outflow_change_pct?: number
  projected_peak_density: number
  time_to_critical_min: number | null
  status: string
}

export interface PredictiveForecast {
  is_active: boolean
  video_id: string | null
  current_density: number
  current_people: number
  current_level: RiskLevel
  critical_threshold: number
  accumulation_rate_ppm2_per_min: number
  time_to_critical_min: number | null
  projections: ProjectionPoint[]
  scenarios: ScenarioModel[]
  disclaimer: string
}

// ---------------------------------------------------------------- Phase 1: foundation layer
// Multi-source video management, event/camera/zone entities, and the global
// timeline. A plain uploaded video (VideoRecord above) keeps working exactly
// as before — these are additive, for videos attached to an Event.

export const SOURCE_TYPES = ['CCTV', 'Drone', 'Uploaded Video'] as const
export type SourceType = typeof SOURCE_TYPES[number]

export const ZONE_ROLES = ['entrance', 'exit', 'bottleneck', 'restricted', 'general'] as const
export type ZoneRole = typeof ZONE_ROLES[number]

// Phase 3: operator-declared spatial crowd context — a zone property, not a
// per-frame guess (see backend/cv/dynamics.py's module docstring).
export const SPATIAL_CONTEXTS = ['open', 'constrained', 'unidirectional', 'multidirectional', 'converging', 'dispersing'] as const
export type SpatialContext = typeof SPATIAL_CONTEXTS[number]

export const DYNAMIC_STATES = ['STATIONARY', 'FLOW', 'DISTURBED', 'VOLATILE', 'REVERSE_FLOW', 'STOP_WAVE'] as const
export type DynamicState = typeof DYNAMIC_STATES[number]

export const ROLLUP_STATES = ['NORMAL', 'FLOW', 'DISTURBED', 'HIGH_RISK'] as const
export type RollupState = typeof ROLLUP_STATES[number]

export interface CrowdEvent {
  id: string
  name: string
  event_type: string
  location: string
  start_time: number | null
  end_time: number | null
  crowd_context: string
  /** Operator-configured, aggregate — never AI-inferred per person. Powers
   * the Phase 4 demographic estimate + vulnerability proxy. All null until
   * the operator sets them. */
  demo_children_pct: number | null
  demo_adults_pct: number | null
  demo_elderly_pct: number | null
  demo_gender_male_pct: number | null
  demo_gender_female_pct: number | null
  created_at: number
}

export interface EventDetail extends CrowdEvent {
  zones: EventZone[]
  cameras: EventCamera[]
  video_sources: EventVideoSource[]
}

/** Normalized [0..1] rectangle on the event's digital-twin map, plus the
 * real-world area/capacity Phase 2 analytics (density, occupancy) need. */
export interface EventZone {
  id: string
  event_id: string
  name: string
  role: ZoneRole
  x: number; y: number; w: number; h: number
  area_m2: number
  capacity: number
  spatial_context: SpatialContext
  created_at: number
}

/** Normalized [0..1] position + compass bearing on the same map. */
export interface EventCamera {
  id: string
  event_id: string
  name: string
  source_type: SourceType
  location_label: string
  x: number; y: number
  orientation_deg: number
  zone_id: string | null
  created_at: number
}

/** A video attached to an event — the video's own real data (thumbnail,
 * duration, last-known analysis) joined with its camera/zone/timestamp
 * context. `capture_start_ts` is operator-declared real-world clock time;
 * null means this source has never been synchronized. */
export interface EventVideoSource {
  id: string
  event_id: string
  camera_id: string | null
  camera_name: string | null
  zone_id: string | null
  zone_name: string | null
  source_type: SourceType
  capture_start_ts: number | null
  /** Which real-motion crossing direction ("left"|"right" across the frame's
   * vertical midline) counts as inflow — an operator-declared assumption,
   * only meaningful when the zone's role is entrance/exit/bottleneck. */
  inflow_direction: 'left' | 'right'
  filename: string
  category: string
  status: VideoStatus
  thumbnail: string | null
  duration_sec: number | null
  size_bytes: number | null
  uploaded_at: number
  last_people: number | null
  last_density: number | null
  last_score: number | null
  last_level: RiskLevel | null
  last_analyzed_at: number | null
}

export type SyncStatus = 'synced' | 'out_of_range' | 'unavailable'

/** One source's position on the global timeline at a chosen instant t. */
export interface TimelineEntry {
  video_id: string
  filename: string
  camera_id: string | null
  camera_name: string | null
  zone_id: string | null
  zone_name: string | null
  source_type: SourceType
  capture_start_ts: number | null
  sync_status: SyncStatus
  /** Seconds into this clip to seek to — null unless sync_status === 'synced'. */
  source_offset_sec: number | null
  /** t minus capture_start_ts, even when out of range — null only when unavailable. */
  sync_offset_sec: number | null
}

// ---------------------------------------------------------------- Phase 2: crowd analytics
// Every field here is either a real number computed from the running CV
// pipeline (see backend/analysis.py::_update_zone_metrics), or an explicit
// "not available" / "requires calibration" status — never a guess.

export type MetricStatus = 'ok' | 'not_available'
export type FlowReason = null | 'zone_role_not_flow_relevant' | 'requires_calibration'
export type TrendStatus = 'increasing' | 'decreasing' | 'stable' | 'not_available'

export interface ZoneFlow {
  supported: boolean
  reason: FlowReason
  inflow_direction: 'left' | 'right'
  inflow_rate_per_min: number | null
  outflow_rate_per_min: number | null
  flow_imbalance_per_min: number | null
  accumulation_risk: boolean
  total_in?: number
  total_out?: number
}

export interface ZoneMetrics {
  available: boolean
  reason: null | 'no_active_analysis' | 'not_zone_attached'
  video_id?: string
  event_id?: string | null
  zone_id?: string
  zone_name?: string
  zone_role?: ZoneRole
  people_count?: number
  zone_area_m2?: number
  density_ppm2?: number
  density_status?: MetricStatus
  capacity?: number | null
  occupancy_pct?: number | null
  occupancy_status?: MetricStatus
  accumulation_rate_ppm2_per_min?: number | null
  accumulation_trend?: TrendStatus
  flow?: ZoneFlow
  bottleneck?: { is_bottleneck_zone: boolean; flagged: boolean }
  dominant_direction_deg?: number | null
  dominant_direction_confidence?: number | null
  dominant_direction_status?: MetricStatus
}

export interface ValidationSample {
  id: number
  created_at: number
  video_id: string
  zone_id: string | null
  zone_name: string | null
  ai_count: number | null
  manual_count: number | null
  count_error: number | null
  count_error_pct: number | null
  ai_density: number | null
  manual_density: number | null
  density_error: number | null
  density_error_pct: number | null
  ai_inflow_rate: number | null
  manual_inflow_rate: number | null
  inflow_error: number | null
  ai_outflow_rate: number | null
  manual_outflow_rate: number | null
  outflow_error: number | null
  note: string
}

export interface ValidationSummary {
  sample_count: number
  mean_abs_count_error: number | null
  mean_abs_count_error_pct: number | null
  mean_abs_density_error: number | null
  mean_abs_density_error_pct: number | null
  mean_abs_inflow_error: number | null
  mean_abs_outflow_error: number | null
}

// ---------------------------------------------------------------- Phase 3: crowd dynamics
// Flow features, compression/edge-pressure proxies, a possible-stop-wave
// signal, and the dynamic-state classification — see backend/cv/dynamics.py
// for exactly what each field is computed from. Every "proxy" field is
// labeled that way deliberately: not a physical measurement.

export interface StopWaveSignal {
  possible_stop_wave: boolean
  reason: string | null
  prior_avg_motion?: number
  current_motion?: number
  drop_ratio?: number
}

export interface DynamicsSignals {
  available: boolean
  reason?: 'no_active_analysis'
  mean_velocity?: number
  velocity_variance?: number
  dominant_direction_deg?: number | null
  dominant_direction_confidence?: number | null
  direction_entropy?: number | null
  direction_entropy_status?: MetricStatus
  reverse_flow_ratio?: number | null
  reverse_flow_status?: MetricStatus
  flow_imbalance_per_min?: number | null
  accumulation_rate_ppm2_per_min?: number | null
  accumulation_trend?: TrendStatus
  compression_proxy?: number
  interpersonal_distance_m?: number | null
  compression_disclaimer?: string
  edge_pressure_proxy?: number | null
  edge_pressure_status?: MetricStatus
  edge_pressure_elevated?: boolean
  edge_pressure_disclaimer?: string
  stop_wave?: StopWaveSignal
  dynamic_state?: DynamicState
  contributing_signals?: string[]
  rollup_state?: RollupState
  spatial_context?: SpatialContext | null
  spatial_context_status?: 'ok' | 'not_zone_attached'
}

export interface DynamicsEvent {
  id: number
  created_at: number
  video_id: string
  zone_id: string | null
  zone_name: string | null
  t_offset_sec: number
  dynamic_state: DynamicState
  rollup_state: RollupState
  previous_state: DynamicState | null
  contributing_signals: string[]
}

// ---------------------------------------------------------------- Phase 4: demographic
// vulnerability + the Crowd Risk Engine (SRI). See backend/cv/sri.py — the
// module docstring there is the authoritative explanation of what's a real
// CV signal vs an operator-configured estimate.

export interface DemographicEstimate {
  available: boolean
  reason?: 'not_configured'
  estimated_children?: number
  estimated_adults?: number
  estimated_elderly?: number
  basis?: string
}

export interface VulnerabilityProxy {
  available: boolean
  reason?: 'not_configured'
  score: number | null
  composition_component?: number
  crowd_condition_component?: number
  disclaimer?: string
}

export interface SRIContribution {
  factor: string
  label: string
  value: number
  weight: number
  contribution: number
}

export interface SRIResult {
  available: boolean
  reason?: 'no_active_analysis'
  sri?: number
  level?: RiskLevel
  label?: string
  contributions?: SRIContribution[]
  notable_signals?: string[]
  demographic_estimate?: DemographicEstimate
  vulnerability?: VulnerabilityProxy
  active_alert_types?: string[]
  disclaimer?: string
}
