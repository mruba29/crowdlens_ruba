import React, { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Play, Pause, RotateCcw, Square, AlertTriangle,
  ClipboardCheck, Compass, Waves, Video, Eye, Clock, Users,
  Activity, ShieldCheck, Flame, CheckCircle, Info, Layers
} from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, RiskBadge, EmptyState, PrivacyBadge, formatDuration, formatDate } from '../components/ui'
import { RiskTimelineChart, PeopleTimelineChart } from '../components/charts'
import type {
  VideoRecord, ZoneMetrics, ValidationSample, ValidationSummary,
  DynamicsSignals, DynamicsEvent, RollupState, SRIResult, RiskLevel,
} from '../lib/types'
import { LEVEL_HEX } from '../lib/types'

export default function VideoDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { status, latest, history, zones, alerts, health, videos, refreshVideos } = useApp()
  const [record, setRecord] = useState<VideoRecord | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [zm, setZm] = useState<ZoneMetrics | null>(null)
  const [dyn, setDyn] = useState<DynamicsSignals | null>(null)
  const [dynEvents, setDynEvents] = useState<DynamicsEvent[]>([])
  const [sri, setSri] = useState<SRIResult | null>(null)
  const [viewMode, setViewMode] = useState<'annotated' | 'source'>('annotated')

  const videoId = id ?? ''
  const isActive = !!status?.video_id && status.video_id === videoId
  const isProcessing = isActive && status?.status === 'processing'
  const isPaused = isActive && status?.status === 'paused'
  const otherProcessing = !!status?.video_id && status.video_id !== videoId && (status?.status === 'processing' || status?.status === 'paused')

  // Real zone-aware analytics polling when this video is active
  useEffect(() => {
    if (!isActive) { setZm(null); return }
    let alive = true
    const tick = () => api.zoneMetrics().then((m) => alive && setZm(m)).catch(() => {})
    tick()
    const iv = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(iv) }
  }, [isActive])

  // Crowd dynamics polling when active
  useEffect(() => {
    if (!isActive) { setDyn(null); return }
    let alive = true
    const tick = () => api.dynamics().then((d) => alive && setDyn(d)).catch(() => {})
    tick()
    const iv = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(iv) }
  }, [isActive])

  // SRI risk engine polling when active
  useEffect(() => {
    if (!isActive) { setSri(null); return }
    let alive = true
    const tick = () => api.sri().then((s) => alive && setSri(s)).catch(() => {})
    tick()
    const iv = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(iv) }
  }, [isActive])

  useEffect(() => {
    let alive = true
    const load = () => api.dynamicsEvents(videoId).then((e) => alive && setDynEvents(e)).catch(() => {})
    load()
    const iv = setInterval(load, isActive ? 4000 : 15000)
    return () => { alive = false; clearInterval(iv) }
  }, [videoId, isActive])

  useEffect(() => {
    let alive = true
    const load = () => api.getVideo(videoId).then((v) => alive && setRecord(v)).catch(() => alive && setNotFound(true))
    load()
    const iv = setInterval(load, 3000)
    return () => { alive = false; clearInterval(iv) }
  }, [videoId])

  useEffect(() => { refreshVideos() }, [record?.status])

  const source = videos.find((v) => v.id === videoId) ?? record

  async function handleStart() {
    setErr(null); setBusy(true)
    try { await api.startAnalysis(videoId) } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  async function handlePause() {
    setBusy(true)
    try { await api.pauseAnalysis() } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  async function handleResume() {
    setBusy(true)
    try { await api.resumeAnalysis() } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  async function handleReplay() {
    setBusy(true); setErr(null)
    try { await api.replayAnalysis(videoId) } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  async function handleStop() {
    setBusy(true)
    try { await api.stopAnalysis() } finally { setBusy(false) }
  }

  if (notFound) {
    return (
      <Panel>
        <EmptyState title="Video not found" hint="It may have been removed from the library." />
        <div className="flex justify-center mt-3">
          <Link to="/videos" className="text-sm text-[var(--accent)] hover:underline flex items-center gap-1">
            <ArrowLeft size={14} /> Back to Crowd Videos
          </Link>
        </div>
      </Panel>
    )
  }
  if (!source) return <Panel><EmptyState title="Loading video details…" /></Panel>

  // Metrics from active stream or recorded summary
  const summary = source.metrics_summary
  const people = isActive ? latest?.people_count ?? source.last_people : (source.last_people ?? summary?.peak_people)
  const density = isActive ? latest?.density_ppm2 ?? source.last_density : (source.last_density ?? summary?.peak_density)
  const score = isActive ? latest?.score ?? source.last_score : (source.last_score ?? summary?.max_score)
  const level = isActive ? latest?.level ?? source.last_level : (source.last_level ?? summary?.final_level)

  // People timeline history data (either live history or persisted summary history)
  const timelineData = isActive
    ? history.map((h) => ({ t_offset_sec: h.t_offset_sec, people_count: h.people_count, density_ppm2: h.density_ppm2 }))
    : summary?.people_timeline ?? []

  const riskTimelineHistory = isActive
    ? history
    : (summary?.people_timeline ?? []).map((p: any) => ({
        t_offset_sec: p.t_offset_sec,
        score: p.score ?? 0,
        level: (p.level as RiskLevel) ?? 'GREEN',
        people_count: p.people_count,
        density_ppm2: p.density_ppm2 ?? 0,
        mean_motion: 0,
        turbulence: 0,
      }))

  const effectiveStatus = isActive ? status?.status ?? source.status : source.status

  const statusBadgeColor: Record<string, string> = {
    uploaded: 'bg-zinc-800 text-zinc-400 border-zinc-700',
    queued: 'bg-amber-950/70 text-amber-400 border-amber-700/60',
    processing: 'bg-blue-950/70 text-blue-400 border-blue-700/60 animate-pulse',
    paused: 'bg-yellow-950/70 text-yellow-400 border-yellow-700/60',
    completed: 'bg-emerald-950/70 text-emerald-400 border-emerald-700/60',
    failed: 'bg-red-950/70 text-red-400 border-red-700/60',
  }

  // Recommended actions based on risk level
  const recommendationsByLevel: Record<string, string[]> = {
    GREEN: [
      'Normal monitoring cadence in effect.',
      'All flow corridors operating within design capacity.',
      'No steward intervention required.',
    ],
    YELLOW: [
      'Elevated occupancy detected — alert primary station supervisors.',
      'Ensure exit egress doors are fully unlocked and unobstructed.',
      'Monitor accumulation trends on main ingress gates.',
    ],
    ORANGE: [
      'Implement staged metering at entry gates to throttle inflow.',
      'Deploy rapid-response stewards to primary bottleneck zones.',
      'Prepare secondary diversion barriers if density increases further.',
    ],
    RED: [
      'IMMEDIATE ACTION: Halt ticket turnstiles and initiate entry pauses.',
      'Activate public address announcements instructing crowds to keep moving.',
      'Mobilize medical and safety personnel at designated exit corridors.',
    ],
    BLACK: [
      'CRITICAL DISASTER MITIGATION: Execute full crowd dispersion protocol.',
      'Open all emergency egress gates and barrier relief locks.',
      'Coordinate rapid transit dispatch to clear station platforms immediately.',
    ],
  }

  const recommendations = recommendationsByLevel[level ?? 'GREEN'] ?? recommendationsByLevel.GREEN

  return (
    <div className="space-y-5">
      {/* Top Header Navigation */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/videos')}
            className="p-2 rounded-lg bg-[var(--panel-2)] hover:bg-white/10 text-[var(--muted)] hover:text-white transition-colors"
            title="Back to Crowd Videos"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold tracking-tight truncate">{source.filename}</h1>
              <span className={`text-[11px] font-semibold uppercase px-2.5 py-0.5 rounded-full border ${statusBadgeColor[effectiveStatus] ?? 'bg-zinc-800 text-zinc-400 border-zinc-700'}`}>
                {effectiveStatus}
              </span>
              {level && <RiskBadge level={level} />}
            </div>
            <p className="text-xs text-[var(--muted)] flex items-center gap-2 mt-0.5">
              <span>{source.category}</span>
              <span>•</span>
              <span>Uploaded {formatDate(source.uploaded_at)}</span>
              <span>•</span>
              <span>Duration: {formatDuration(source.duration_sec)}</span>
              {source.size_bytes && (
                <>
                  <span>•</span>
                  <span>{(source.size_bytes / (1024 * 1024)).toFixed(1)} MB</span>
                </>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PrivacyBadge />
        </div>
      </div>

      {health && !health.detector.available && (
        <Panel className="border-yellow-500/40 bg-yellow-950/20">
          <div className="flex items-center gap-2 text-sm text-yellow-400">
            <AlertTriangle size={16} />
            <span>Analysis service degraded: no person detector loaded on server. Install Ultralytics YOLO to activate real-time detection.</span>
          </div>
        </Panel>
      )}

      {/* Main Workspace Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left Column: Player, Controls, and Timelines */}
        <div className="lg:col-span-2 space-y-5">
          {/* Video Player Card */}
          <Panel
            title="Analysis Video Stream"
            actions={
              isActive && latest?.annotated_frame ? (
                <div className="flex items-center gap-1 bg-[var(--panel-2)] p-0.5 rounded-lg border border-[var(--border)] text-xs">
                  <button
                    onClick={() => setViewMode('annotated')}
                    className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1.5 ${viewMode === 'annotated' ? 'bg-[var(--accent)] text-white font-medium' : 'text-[var(--muted)] hover:text-white'}`}
                  >
                    <Eye size={12} /> AI Detections
                  </button>
                  <button
                    onClick={() => setViewMode('source')}
                    className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1.5 ${viewMode === 'source' ? 'bg-[var(--accent)] text-white font-medium' : 'text-[var(--muted)] hover:text-white'}`}
                  >
                    <Video size={12} /> Source Video
                  </button>
                </div>
              ) : undefined
            }
          >
            <div className="aspect-video w-full rounded-lg bg-black flex items-center justify-center overflow-hidden relative shadow-inner border border-zinc-900">
              {isActive && latest?.annotated_frame && viewMode === 'annotated' ? (
                <div className="relative w-full h-full flex items-center justify-center">
                  <img
                    src={latest.annotated_frame}
                    alt="Active AI Computer Vision Detection"
                    className="w-full h-full object-contain"
                  />
                  <div className="absolute top-3 left-3 bg-red-600/90 backdrop-blur-sm text-white px-2.5 py-0.5 rounded text-[11px] font-bold flex items-center gap-1.5 tracking-wider shadow">
                    <span className="w-2 h-2 rounded-full bg-white animate-ping" />
                    LIVE CV INFERENCE
                  </div>
                  {status?.fps && (
                    <div className="absolute top-3 right-3 bg-black/75 backdrop-blur-sm text-zinc-300 px-2 py-0.5 rounded text-[11px] font-mono">
                      {status.fps.toFixed(1)} FPS
                    </div>
                  )}
                </div>
              ) : (
                <video
                  controls
                  src={api.videoUrl(videoId)}
                  poster={source.thumbnail ?? undefined}
                  className="w-full h-full object-contain"
                />
              )}
            </div>

            {/* Analysis Workspace Controls */}
            <div className="mt-4 pt-3 border-t border-[var(--border)] flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                {isProcessing ? (
                  <>
                    <button
                      disabled={busy}
                      onClick={handlePause}
                      className="px-3.5 py-1.5 rounded-lg bg-yellow-600 hover:bg-yellow-500 text-white text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      title="Pause current analysis"
                    >
                      <Pause size={14} /> Pause
                    </button>
                    <button
                      disabled={busy}
                      onClick={handleStop}
                      className="px-3.5 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      title="Stop analysis session"
                    >
                      <Square size={14} /> Stop
                    </button>
                  </>
                ) : isPaused ? (
                  <>
                    <button
                      disabled={busy}
                      onClick={handleResume}
                      className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                    >
                      <Play size={14} /> Resume
                    </button>
                    <button
                      disabled={busy}
                      onClick={handleStop}
                      className="px-3.5 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                    >
                      <Square size={14} /> Stop
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      disabled={busy || otherProcessing || !health?.detector.available}
                      onClick={handleStart}
                      className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40 disabled:hover:bg-emerald-600"
                    >
                      <Play size={14} /> {busy ? 'Starting…' : 'Start Analysis'}
                    </button>
                    {source.status === 'completed' && (
                      <button
                        disabled={busy || otherProcessing}
                        onClick={handleReplay}
                        className="px-3.5 py-1.5 rounded-lg bg-[var(--panel-2)] hover:bg-white/10 text-white text-sm font-medium flex items-center gap-1.5 border border-[var(--border)] transition-colors disabled:opacity-50"
                        title="Re-run analysis pipeline from the beginning"
                      >
                        <RotateCcw size={14} /> Re-analyze
                      </button>
                    )}
                  </>
                )}
              </div>

              <div className="text-xs text-[var(--muted)]">
                {otherProcessing && (
                  <span className="text-amber-400 flex items-center gap-1">
                    <AlertTriangle size={12} /> Another video is currently being analyzed ({status?.video_id}). Stop it first.
                  </span>
                )}
                {!otherProcessing && isProcessing && 'Analysis pipeline actively tracking pedestrians & crowd flow.'}
                {!otherProcessing && isPaused && 'Analysis paused. Click Resume to continue.'}
                {!otherProcessing && !isActive && source.status === 'completed' && (
                  <span className="text-emerald-400 flex items-center gap-1">
                    <CheckCircle size={12} /> Analysis complete. Historical crowd curve recorded below.
                  </span>
                )}
                {!otherProcessing && !isActive && source.status === 'uploaded' && 'Video ready for AI analysis.'}
              </div>
            </div>

            {err && (
              <div className="mt-2 p-2 rounded bg-red-950/40 border border-red-800/60 text-xs text-red-300">
                {err}
              </div>
            )}
          </Panel>

          {/* People Count Timeline */}
          <Panel
            title="People Detection Timeline"
            actions={
              <span className="text-xs text-[var(--muted)] flex items-center gap-1">
                <Users size={13} /> {isActive ? 'Live detection trend' : 'Recorded pedestrian curve'}
              </span>
            }
          >
            <div className="mb-2 flex items-center justify-between text-xs text-[var(--muted)]">
              <span>Timeline: seconds into video stream</span>
              <span>Metric: count of detected bounding boxes</span>
            </div>
            <PeopleTimelineChart data={timelineData} height={200} />
          </Panel>

          {/* Risk Timeline Chart */}
          <Panel
            title="Crowd Risk Timeline (SRI Index)"
            actions={
              <span className="text-xs text-[var(--muted)] flex items-center gap-1">
                <Activity size={13} /> Orange (56+) & Red (76+) thresholds
              </span>
            }
          >
            <RiskTimelineChart history={riskTimelineHistory} height={200} />
          </Panel>

          {/* Crowd State Timeline & Transitions */}
          {dynEvents.length > 0 && <CrowdStateTimeline events={dynEvents} />}
        </div>

        {/* Right Column: Metrics, Heatmap, SRI, Dynamics, and Actions */}
        <div className="space-y-5">
          {/* Overview Snapshot */}
          <Panel title="Crowd Telemetry Snapshot">
            <dl className="text-sm space-y-2">
              <Row k="Current Status" v={<span className="font-semibold capitalize">{effectiveStatus}</span>} />
              <Row k="People Detected" v={<span className="font-bold text-base text-[var(--accent)]">{people ?? '--'}</span>} />
              <Row k="Crowd Density" v={density != null ? `${Number(density).toFixed(2)} people/m²` : '--'} />
              <Row k="Safety Risk Index" v={score != null ? <span className="font-bold">{Math.round(score)}/100</span> : '--'} />
              <Row k="Risk Category" v={level ? <RiskBadge level={level} /> : <span className="text-[var(--muted)]">--</span>} />
              {summary?.peak_people != null && <Row k="Peak People" v={`${summary.peak_people}`} />}
              {summary?.avg_density != null && <Row k="Average Density" v={`${summary.avg_density.toFixed(2)}/m²`} />}
            </dl>
          </Panel>

          {/* Zone Density & Heatmap Card */}
          <Panel
            title="Zone Density Heatmap"
            actions={<span className="text-xs text-[var(--muted)] flex items-center gap-1"><Flame size={12} /> Spatial breakdown</span>}
          >
            {zones.length > 0 ? (
              <div className="space-y-3">
                {zones.map((z) => {
                  const maxEst = Math.max(...zones.map((item) => item.people), 20)
                  const pct = Math.min(100, Math.round((z.people / maxEst) * 100))
                  const color = LEVEL_HEX[z.level] ?? '#34d399'
                  return (
                    <div key={z.name} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-[var(--text)]">{z.name}</span>
                        <div className="flex items-center gap-2">
                          <span className="tabular-nums font-semibold">{z.people} people</span>
                          <RiskBadge level={z.level} />
                        </div>
                      </div>
                      <div className="h-2 rounded-full bg-[var(--panel-2)] overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${pct}%`,
                            backgroundColor: color,
                            boxShadow: `0 0 8px ${color}66`,
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : summary?.zone_distribution && summary.zone_distribution.length > 0 ? (
              <div className="space-y-3">
                {summary.zone_distribution.map((z: any) => (
                  <div key={z.name} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-[var(--text)]">{z.name}</span>
                      <span className="tabular-nums font-semibold">{z.count} people ({z.pct}%)</span>
                    </div>
                    <div className="h-2 rounded-full bg-[var(--panel-2)] overflow-hidden">
                      <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${z.pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No zones configured" hint="Add polygon zones on the Crowd Analytics page to track spatial density." />
            )}
          </Panel>

          {/* Crowd Safety Risk Index (SRI) breakdown */}
          {isActive && sri?.available ? (
            <RiskEnginePanel sri={sri} />
          ) : (
            <Panel title="Crowd Risk Engine (SRI)">
              <div className="flex items-center gap-3">
                <div className="text-center shrink-0">
                  <div className="text-3xl font-bold tabular-nums" style={{ color: level ? ((LEVEL_HEX as Record<string, string>)[level] ?? '#8a938d') : '#8a938d' }}>
                    {score != null ? Math.round(score) : '--'}
                  </div>
                  {level && <RiskBadge level={level} />}
                </div>
                <div className="text-xs text-[var(--muted)]">
                  <p className="font-medium text-[var(--text)]">10-Factor Multi-Signal Risk Engine</p>
                  <p className="mt-0.5">Integrates density, velocity, flow imbalance, accumulation rate, turbulence, and venue geometry.</p>
                </div>
              </div>
              {!isActive && (
                <p className="text-[11px] text-[var(--muted)] mt-3 pt-2 border-t border-[var(--border)]">
                  {source.status === 'completed'
                    ? 'Historical analysis recorded. Live multi-factor weights displayed during active stream.'
                    : 'Start analysis to view live signal contributions and vulnerability breakdown.'}
                </p>
              )}
            </Panel>
          )}

          {/* Crowd Dynamics & Flow Metrics */}
          {isActive && dyn?.available ? (
            <CrowdDynamicsPanel dyn={dyn} />
          ) : (
            <Panel title="Crowd Dynamics & Flow">
              <dl className="text-sm space-y-2">
                <Row k="Flow Imbalance" v={summary?.flow_imbalance != null ? `${summary.flow_imbalance}/min` : 'Not Available (requires gate)'} />
                <Row k="Accumulation Rate" v={summary?.accumulation_rate != null ? `${summary.accumulation_rate} /m²/min` : 'Not Available'} />
                <Row k="Mean Velocity" v={summary?.mean_velocity != null ? `${summary.mean_velocity.toFixed(2)} px/frame` : 'Not Available'} />
                <Row k="Turbulence / Stop-Wave" v={<span className="text-zinc-400">Normal flow</span>} />
              </dl>
              <p className="text-[10px] text-[var(--muted)] mt-2">
                Flow dynamics are computed via Lucas-Kanade optical flow on tracked pedestrian centroids.
              </p>
            </Panel>
          )}

          {/* Zone Analytics if active */}
          {isActive && zm?.available && <ZoneAnalyticsPanel zm={zm} />}

          {/* Active Alerts for this video/source */}
          <Panel
            title="Safety Alerts & Recommendations"
            actions={<Link to="/alerts" className="text-xs text-[var(--accent)] hover:underline">All alerts</Link>}
          >
            <div className="space-y-3">
              {alerts.filter((a) => a.video_id === videoId).slice(0, 3).map((a) => (
                <div key={a.id} className="p-2.5 rounded-lg bg-red-950/30 border border-red-800/40 text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <RiskBadge level={a.level} />
                    <span className="text-[10px] text-[var(--muted)] font-mono">{new Date(a.created_at * 1000).toLocaleTimeString()}</span>
                  </div>
                  <p className="font-semibold text-red-200">{a.reason}</p>
                  <p className="text-[var(--muted)]">{a.zone} • {a.recommended_action}</p>
                </div>
              ))}

              {alerts.filter((a) => a.video_id === videoId).length === 0 && (
                <p className="text-xs text-[var(--muted)]">No critical risk alerts generated for this video source.</p>
              )}

              {/* Recommended Public-Safety Procedures */}
              <div className="pt-2 border-t border-[var(--border)]">
                <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text)] mb-1.5 flex items-center gap-1">
                  <ShieldCheck size={13} className="text-emerald-400" />
                  Recommended Operational Protocol
                </p>
                <ul className="text-xs space-y-1 text-[var(--muted)]">
                  {recommendations.map((rec, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-[var(--accent)] mt-0.5">•</span>
                      <span>{rec}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Panel>

          {/* AI vs Manual Validation */}
          {source.status !== 'uploaded' && (
            <ValidationPanel videoId={videoId} zoneId={zm?.zone_id} zoneName={zm?.zone_name} zm={zm} />
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center text-xs">
      <dt className="text-[var(--muted)]">{k}</dt>
      <dd className="tabular-nums text-right">{v}</dd>
    </div>
  )
}

// Phase 4: Risk engine component
function RiskEnginePanel({ sri }: { sri: SRIResult }) {
  const hex = LEVEL_HEX[sri.level!] ?? '#8a938d'
  const demo = sri.demographic_estimate
  const vuln = sri.vulnerability
  return (
    <Panel title="Crowd Risk Engine (SRI)">
      <div className="flex items-center gap-4">
        <div className="text-center shrink-0">
          <div className="text-4xl font-bold tabular-nums" style={{ color: hex }}>{Math.round(sri.sri!)}</div>
          <RiskBadge level={sri.level!} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1">SRI {Math.round(sri.sri!)} — {sri.level}</p>
          {sri.notable_signals?.length ? (
            <ul className="text-xs space-y-0.5">
              {sri.notable_signals.map((s, i) => <li key={i} style={{ color: hex }}>{s}</li>)}
            </ul>
          ) : (
            <p className="text-xs text-[var(--muted)]">No individually elevated signals right now.</p>
          )}
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-[var(--border)]">
        <p className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1.5">All 10 inputs (weighted)</p>
        <div className="space-y-1">
          {sri.contributions?.map((c) => (
            <div key={c.factor} className="flex items-center gap-2 text-xs">
              <span className="w-32 shrink-0 text-[var(--muted)] truncate">{c.label}</span>
              <div className="flex-1 h-1.5 rounded-full bg-[var(--panel-2)] overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${c.value}%`, backgroundColor: hex }} />
              </div>
              <span className="tabular-nums w-10 text-right">{c.value}</span>
            </div>
          ))}
        </div>
      </div>

      {(demo || vuln) && (
        <div className="mt-3 pt-3 border-t border-[var(--border)] grid grid-cols-2 gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1">Demographic estimate</p>
            {demo?.available ? (
              <>
                <p className="text-xs">Children: <b>{demo.estimated_children}</b> · Adults: <b>{demo.estimated_adults}</b> · Elderly: <b>{demo.estimated_elderly}</b></p>
                <p className="text-[10px] text-[var(--muted)] mt-0.5">{demo.basis}</p>
              </>
            ) : <p className="text-xs text-[var(--muted)]">Not Available — configure composition on the event page.</p>}
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1">Vulnerability</p>
            {vuln?.available ? (
              <>
                <p className="text-xs tabular-nums">{vuln.score}/100</p>
                <p className="text-[10px] text-[var(--muted)] mt-0.5">{vuln.disclaimer}</p>
              </>
            ) : <p className="text-xs text-[var(--muted)]">Not Available — requires composition.</p>}
          </div>
        </div>
      )}
      <p className="text-[10px] text-[var(--muted)] mt-2">{sri.disclaimer}</p>
    </Panel>
  )
}

// Phase 3: Crowd dynamics
const STATE_COLOR: Record<string, string> = {
  STATIONARY: '#8a938d', FLOW: '#34d399', DISTURBED: '#22d3ee',
  VOLATILE: '#f87171', REVERSE_FLOW: '#fb923c', STOP_WAVE: '#c084fc',
}
const ROLLUP_COLOR: Record<RollupState, string> = {
  NORMAL: '#8a938d', FLOW: '#34d399', DISTURBED: '#facc15', HIGH_RISK: '#f87171',
}

function CrowdDynamicsPanel({ dyn }: { dyn: DynamicsSignals }) {
  const stateColor = STATE_COLOR[dyn.dynamic_state ?? ''] ?? '#8a938d'
  return (
    <Panel title="Crowd Dynamics" actions={
      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ color: stateColor, backgroundColor: `${stateColor}22`, border: `1px solid ${stateColor}55` }}>
        {dyn.dynamic_state?.replace('_', ' ')}
      </span>
    }>
      {!!dyn.contributing_signals?.length && (
        <div className="mb-3 pb-3 border-b border-[var(--border)]">
          <p className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1">Contributing signals</p>
          <ul className="text-xs space-y-1">
            {dyn.contributing_signals.map((s, i) => (
              <li key={i} className="flex items-start gap-1.5"><span style={{ color: stateColor }}>—</span><span>{s}</span></li>
            ))}
          </ul>
        </div>
      )}

      <dl className="text-sm space-y-1.5">
        <Row k="Spatial context" v={dyn.spatial_context_status === 'ok' ? dyn.spatial_context : 'Not Available (no zone attached)'} />
        <Row k="Mean velocity" v={dyn.mean_velocity != null ? `${dyn.mean_velocity.toFixed(2)} px/frame` : '--'} />
        <Row k="Velocity variance" v={dyn.velocity_variance != null ? dyn.velocity_variance.toFixed(2) : '--'} />
        <Row k="Dominant direction" v={
          dyn.dominant_direction_deg != null
            ? `${dyn.dominant_direction_deg}° (${Math.round((dyn.dominant_direction_confidence ?? 0) * 100)}% conf.)`
            : 'Not Available'
        } />
        <Row k="Direction entropy" v={dyn.direction_entropy_status === 'ok' ? dyn.direction_entropy : 'Not Available'} />
        <Row k="Reverse-flow ratio" v={dyn.reverse_flow_status === 'ok' ? `${Math.round((dyn.reverse_flow_ratio ?? 0) * 100)}%` : 'Not Available'} />
        <Row k="Flow imbalance" v={dyn.flow_imbalance_per_min != null ? `${dyn.flow_imbalance_per_min}/min` : 'Not Available'} />
        <Row k="Accumulation rate" v={dyn.accumulation_trend !== 'not_available' ? `${dyn.accumulation_rate_ppm2_per_min ?? 0} /m²/min (${dyn.accumulation_trend})` : 'Not Available'} />
      </dl>

      <div className="mt-3 pt-3 border-t border-[var(--border)] space-y-2">
        <div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-[var(--muted)]">Compression Proxy</span>
            <span className="tabular-nums font-semibold">{dyn.compression_proxy}/100</span>
          </div>
          <p className="text-[10px] text-[var(--muted)]">{dyn.compression_disclaimer}{dyn.interpersonal_distance_m != null && ` Spacing: ${dyn.interpersonal_distance_m}m.`}</p>
        </div>
        <div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-[var(--muted)]">Edge Pressure Proxy</span>
            <span className="tabular-nums font-semibold">
              {dyn.edge_pressure_status === 'ok' ? `${Math.round((dyn.edge_pressure_proxy ?? 0) * 100)}%` : 'Not Available'}
              {dyn.edge_pressure_elevated && <span className="text-orange-400 ml-1">●</span>}
            </span>
          </div>
          <p className="text-[10px] text-[var(--muted)]">{dyn.edge_pressure_disclaimer}</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Waves size={13} className={dyn.stop_wave?.possible_stop_wave ? 'text-purple-400' : 'text-[var(--muted)]'} />
          <span>{dyn.stop_wave?.possible_stop_wave ? 'Possible stop-wave signal' : 'No stop-wave signal'}</span>
          {dyn.stop_wave?.drop_ratio != null && <span className="text-[var(--muted)] text-[10px]">(drop {Math.round(dyn.stop_wave.drop_ratio * 100)}%)</span>}
        </div>
      </div>
      <p className="text-[10px] text-[var(--muted)] mt-2 flex items-center gap-1"><Compass size={10} />Early signals only — feeds the risk engine, not a stampede detector.</p>
    </Panel>
  )
}

function CrowdStateTimeline({ events }: { events: DynamicsEvent[] }) {
  const runs: { events: DynamicsEvent[] }[] = []
  events.forEach((e) => {
    if (e.previous_state === null || runs.length === 0) runs.push({ events: [] })
    runs[runs.length - 1].events.push(e)
  })
  const latestRun = runs[runs.length - 1]?.events ?? []
  if (latestRun.length === 0) return null
  const tMax = Math.max(...latestRun.map((e) => e.t_offset_sec), 1)

  return (
    <Panel title="Crowd State Timeline" actions={<span className="text-[10px] text-[var(--muted)]">NORMAL → FLOW → DISTURBED → HIGH RISK</span>}>
      <div className="flex h-6 rounded overflow-hidden border border-[var(--border)]">
        {latestRun.map((e, i) => {
          const next = latestRun[i + 1]
          const start = (e.t_offset_sec / tMax) * 100
          const end = ((next ? next.t_offset_sec : tMax) / tMax) * 100
          return (
            <div key={e.id} title={`${e.dynamic_state} @ ${e.t_offset_sec.toFixed(1)}s — ${e.contributing_signals.join(' ')}`}
              style={{ width: `${Math.max(0.5, end - start)}%`, backgroundColor: ROLLUP_COLOR[e.rollup_state] }} />
          )
        })}
      </div>
      <div className="flex gap-3 mt-2 flex-wrap">
        {(['NORMAL', 'FLOW', 'DISTURBED', 'HIGH_RISK'] as RollupState[]).map((r) => (
          <span key={r} className="flex items-center gap-1 text-[10px] text-[var(--muted)]">
            <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ backgroundColor: ROLLUP_COLOR[r] }} />{r.replace('_', ' ')}
          </span>
        ))}
      </div>
      <div className="mt-2 max-h-28 overflow-y-auto space-y-1">
        {[...latestRun].reverse().slice(0, 10).map((e) => (
          <div key={e.id} className="text-[11px] text-[var(--muted)] flex gap-2">
            <span className="tabular-nums shrink-0">{e.t_offset_sec.toFixed(1)}s</span>
            <span>{e.previous_state ?? '—'} → <b className="text-[var(--text)]">{e.dynamic_state}</b></span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

function ZoneAnalyticsPanel({ zm }: { zm: ZoneMetrics }) {
  const trendLabel: Record<string, string> = {
    increasing: 'Increasing ↑', decreasing: 'Decreasing ↓', stable: 'Stable →', not_available: 'Not Available',
  }
  const flow = zm.flow
  return (
    <Panel title={`Zone Analytics — ${zm.zone_name}`} actions={
      zm.bottleneck?.flagged
        ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-400 border border-orange-500/40">BOTTLENECK</span>
        : undefined
    }>
      <dl className="text-sm space-y-1.5">
        <Row k="Zone role" v={zm.zone_role} />
        <Row k="People count" v={zm.people_count} />
        <Row k="Zone area" v={`${zm.zone_area_m2} m²`} />
        <Row k="Density" v={zm.density_status === 'ok' ? `${zm.density_ppm2?.toFixed(2)} /m²` : 'Not Available'} />
        <Row k="Capacity" v={zm.capacity ?? 'Not Available'} />
        <Row k="Occupancy" v={zm.occupancy_status === 'ok' ? `${zm.occupancy_pct}%` : 'Not Available'} />
        <Row k="Accumulation trend" v={trendLabel[zm.accumulation_trend ?? 'not_available']} />
        <Row k="Accumulation rate" v={zm.accumulation_rate_ppm2_per_min != null ? `${zm.accumulation_rate_ppm2_per_min} /m²/min` : 'Not Available'} />
        <Row k="Dominant direction" v={
          zm.dominant_direction_status === 'ok'
            ? `${zm.dominant_direction_deg}° (${Math.round((zm.dominant_direction_confidence ?? 0) * 100)}% confidence)`
            : 'Not Available'
        } />
      </dl>

      <div className="mt-3 pt-3 border-t border-[var(--border)]">
        <p className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1.5">Inflow / Outflow</p>
        {!flow?.supported ? (
          <p className="text-xs text-[var(--muted)]">Not Available — this zone's role ({zm.zone_role}) has no gate to measure crossings on.</p>
        ) : flow.reason === 'requires_calibration' ? (
          <p className="text-xs text-yellow-400">Requires Calibration — collecting real tracked crossings, ready shortly.</p>
        ) : (
          <dl className="text-sm space-y-1.5">
            <Row k="Inflow rate" v={`${flow.inflow_rate_per_min} /min`} />
            <Row k="Outflow rate" v={`${flow.outflow_rate_per_min} /min`} />
            <Row k="Flow imbalance" v={
              <span className={flow.accumulation_risk ? 'text-orange-400 font-semibold' : ''}>
                {(flow.flow_imbalance_per_min ?? 0) > 0 ? '+' : ''}{flow.flow_imbalance_per_min} /min
                {flow.accumulation_risk && ' — accumulation risk'}
              </span>
            } />
          </dl>
        )}
      </div>
    </Panel>
  )
}

function ValidationPanel({ videoId, zoneId, zoneName, zm }: {
  videoId: string; zoneId?: string; zoneName?: string; zm: ZoneMetrics | null
}) {
  const [manualCount, setManualCount] = useState('')
  const [samples, setSamples] = useState<ValidationSample[]>([])
  const [summary, setSummary] = useState<ValidationSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  function load() {
    api.listValidationSamples(videoId).then(setSamples).catch(() => {})
    api.validationSummary(videoId).then(setSummary).catch(() => {})
  }
  useEffect(() => { load() }, [videoId])

  async function submit() {
    if (manualCount.trim() === '') { setErr('Enter a manual reference count'); return }
    setBusy(true); setErr(null)
    try {
      await api.addValidationSample({
        video_id: videoId, zone_id: zoneId ?? null, zone_name: zoneName ?? null,
        ai_count: zm?.people_count ?? null, manual_count: parseInt(manualCount, 10),
        ai_density: zm?.density_ppm2 ?? null, manual_density: null,
        ai_inflow_rate: zm?.flow?.inflow_rate_per_min ?? null, manual_inflow_rate: null,
        ai_outflow_rate: zm?.flow?.outflow_rate_per_min ?? null, manual_outflow_rate: null,
      })
      setManualCount(''); load()
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Panel title="Validation — AI vs Manual Count">
      <div className="flex items-end gap-2">
        <label className="flex-1">
          <span className="block text-[11px] text-[var(--muted)] mb-1">Manual reference count right now</span>
          <input type="number" value={manualCount} onChange={(e) => setManualCount(e.target.value)} placeholder="e.g. 12"
            className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
        </label>
        <button disabled={busy} onClick={submit}
          className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium disabled:opacity-60 flex items-center gap-1.5">
          <ClipboardCheck size={14} /> Record
        </button>
      </div>
      <p className="text-[10px] text-[var(--muted)] mt-1">
        Compares against the AI count at the moment you click Record ({zm?.people_count ?? '—'} right now). Error is always computed from these two real numbers — never invented.
      </p>
      {err && <p className="text-xs text-red-400 mt-1">{err}</p>}

      {summary && summary.sample_count > 0 ? (
        <div className="mt-3 pt-3 border-t border-[var(--border)] text-sm space-y-1.5">
          <Row k="Samples recorded" v={summary.sample_count} />
          <Row k="Mean count error" v={`${summary.mean_abs_count_error} people (${summary.mean_abs_count_error_pct}%)`} />
          {summary.mean_abs_density_error != null && <Row k="Mean density error" v={`${summary.mean_abs_density_error} /m²`} />}
        </div>
      ) : (
        <p className="text-xs text-[var(--muted)] mt-3">No validation samples yet.</p>
      )}

      {samples.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[var(--border)] space-y-1.5 max-h-40 overflow-y-auto">
          {samples.slice(0, 8).map((s) => (
            <div key={s.id} className="flex items-center justify-between text-xs text-[var(--muted)]">
              <span>{new Date(s.created_at * 1000).toLocaleTimeString()}</span>
              <span>AI {s.ai_count} vs manual {s.manual_count} <span className={s.count_error ? 'text-yellow-400' : 'text-emerald-400'}>({s.count_error! >= 0 ? '+' : ''}{s.count_error})</span></span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
