import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ShieldCheck, ArrowUpRight, TrendingUp, TrendingDown, Minus, Video, AlertTriangle,
  Upload, Play, CheckCircle2, BarChart3, Activity, Gauge, Compass, Layers, Clock, Check,
} from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, StatCard, RiskBadge, EmptyState, PrivacyBadge, Dot, VideoThumb, formatDuration, formatDate } from '../components/ui'
import { RiskTimelineChart, riskTrend } from '../components/charts'
import { LEVEL_CLASS, LEVEL_HEX, LEVEL_RISK_LABEL } from '../lib/types'
import type { ZoneMetrics, DynamicsSignals, RiskLevel } from '../lib/types'

export default function Dashboard() {
  const { latest, history, zones, alerts, incidents, status, health, videos, refreshAlerts, refreshVideos } = useApp()
  const navigate = useNavigate()
  const [zm, setZm] = useState<ZoneMetrics | null>(null)
  const [dyn, setDyn] = useState<DynamicsSignals | null>(null)
  const [acking, setAcking] = useState<number | null>(null)

  const isLive = status?.status === 'processing' || status?.status === 'paused'

  // Poll real zone metrics & dynamics when active
  useEffect(() => {
    if (!isLive) { setZm(null); setDyn(null); return }
    let alive = true
    const tick = () => {
      api.zoneMetrics().then((m) => alive && setZm(m)).catch(() => {})
      api.dynamics().then((d) => alive && setDyn(d)).catch(() => {})
    }
    tick()
    const id = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(id) }
  }, [isLive])

  const activeAlerts = alerts.filter((a) => a.status === 'ACTIVE')
  const activeIncidents = incidents.filter((i) => i.status !== 'RESOLVED')
  const hasData = !!latest
  const trend = riskTrend(history)

  // 1. Overview cards data
  const totalVideoSources = videos.length
  const activeAnalysesCount = videos.filter((v) => v.status === 'processing' || v.status === 'queued').length +
    (status?.status === 'processing' ? 1 : 0)
  const peopleDetected = hasData ? latest!.people_count : (videos.find((v) => v.last_people != null)?.last_people ?? 0)
  
  const analyzedVideos = videos.filter((v) => v.last_density != null)
  const avgDensity = hasData
    ? latest!.density_ppm2
    : analyzedVideos.length > 0
    ? analyzedVideos.reduce((acc, v) => acc + (v.last_density ?? 0), 0) / analyzedVideos.length
    : 0

  const currentLevel: RiskLevel = hasData
    ? latest!.level
    : (videos.find((v) => v.last_level)?.last_level ?? 'GREEN')

  const currentScore = hasData
    ? Math.round(latest!.score)
    : (videos.find((v) => v.last_score != null)?.last_score ? Math.round(videos.find((v) => v.last_score != null)!.last_score!) : 0)

  // Top zones
  const topZones = [...zones].sort((a, b) => b.score - a.score)
  const cameraFeeds = [...videos].sort((a, b) => b.uploaded_at - a.uploaded_at)
  const recentAnalyses = [...videos]
    .filter((v) => v.status === 'completed' || v.last_analyzed_at != null || v.status === 'processing')
    .slice(0, 5)

  async function handleAcknowledge(alertId: number) {
    setAcking(alertId)
    try {
      await api.acknowledgeAlert(alertId)
      await refreshAlerts()
    } finally {
      setAcking(null)
    }
  }

  // Find next ready video to start
  const nextReadyVideo = videos.find((v) => v.status === 'uploaded')

  return (
    <div className="space-y-5">
      {/* Top Command Center Header */}
      <div className="flex items-center justify-between flex-wrap gap-4 bg-[var(--panel)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-[var(--accent)]/15 text-[var(--accent)] border border-[var(--accent)]/30">
            <ShieldCheck size={26} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-[var(--text)]">CROWDLENS COMMAND CENTER</h1>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                ACTIVE
              </span>
            </div>
            <p className="text-xs text-[var(--muted)]">
              Real-Time AI Crowd Safety Intelligence & Density Early Warning System
            </p>
          </div>
        </div>

        {/* Quick Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => navigate('/videos')}
            className="px-3 py-2 rounded-lg bg-[var(--panel-2)] border border-[var(--border)] text-xs font-semibold hover:border-[var(--accent)] transition-colors flex items-center gap-1.5"
          >
            <Upload size={14} className="text-[var(--accent)]" /> Upload Videos
          </button>
          {nextReadyVideo && !isLive && (
            <button
              onClick={() => navigate(`/videos/${nextReadyVideo.id}`)}
              className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-colors flex items-center gap-1.5"
            >
              <Play size={14} /> Start Analysis
            </button>
          )}
          <Link
            to="/alerts"
            className="px-3 py-2 rounded-lg bg-[var(--panel-2)] border border-[var(--border)] text-xs font-semibold hover:border-[var(--accent)] transition-colors flex items-center gap-1.5"
          >
            <AlertTriangle size={14} className={activeAlerts.length > 0 ? 'text-red-400' : 'text-[var(--muted)]'} />
            Alerts {activeAlerts.length > 0 && <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.2 rounded-full font-bold">{activeAlerts.length}</span>}
          </Link>
          <Link
            to="/analytics"
            className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-bold hover:bg-emerald-600 transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <BarChart3 size={14} /> Crowd Analytics
          </Link>
        </div>
      </div>

      {/* 1. Overview Cards (6 Grid) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          label="Total Sources"
          value={totalVideoSources}
          sub={`${videos.filter((v) => v.status === 'completed').length} analyzed`}
        />
        <StatCard
          label="Active Analyses"
          value={isLive ? '1 Active' : 'Idle'}
          sub={status?.video_id ? status.video_id.slice(0, 10) + '…' : 'Ready'}
          subClass={isLive ? 'text-[var(--accent)] font-bold' : 'text-[var(--muted)]'}
        />
        <StatCard
          label="People Detected"
          value={hasData ? latest!.people_count : peopleDetected || '—'}
          sub={hasData ? 'Current frame detection' : 'Last recorded count'}
        />
        <StatCard
          label="Avg Crowd Density"
          value={avgDensity > 0 ? `${avgDensity.toFixed(2)}/m²` : '—'}
          sub="Critical limit: 5.0/m²"
          subClass={avgDensity >= 4.0 ? 'text-orange-400 font-bold' : 'text-[var(--text)]'}
        />
        <div className="panel p-4 flex flex-col justify-between">
          <div className="text-[11px] uppercase tracking-wider text-[var(--muted)]">Current Risk Level</div>
          <div className="my-1">
            <RiskBadge level={currentLevel} />
          </div>
          <div className="text-[11px] text-[var(--muted)]">
            Score: <span className="font-bold text-[var(--text)] tabular-nums">{currentScore}/100</span>
          </div>
        </div>
        <StatCard
          label="Active Alerts"
          value={activeAlerts.length}
          sub={activeAlerts.length > 0 ? 'Requires action' : 'All zones normal'}
          subClass={activeAlerts.length > 0 ? 'text-red-400 font-bold' : 'text-emerald-400'}
        />
      </div>

      {/* 2. Crowd Risk Overview & Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Panel
          title="Crowd Risk Overview & Timeline"
          className="lg:col-span-2"
          actions={
            trend ? (
              <span className="text-xs text-[var(--muted)] flex items-center gap-1 font-medium">
                {trend === 'Increasing' && <TrendingUp size={14} className="text-red-400" />}
                {trend === 'Decreasing' && <TrendingDown size={14} className="text-emerald-400" />}
                {trend === 'Stable' && <Minus size={14} />}
                Trend: <span className="font-bold text-[var(--text)]">{trend}</span>
              </span>
            ) : null
          }
        >
          {/* Risk Level Tiers Scale */}
          <div className="mb-4 p-3 rounded-lg bg-[var(--panel-2)]/60 border border-[var(--border)] space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[var(--muted)] font-medium">Safety Risk Scale</span>
              <span className="font-semibold text-xs" style={{ color: LEVEL_HEX[currentLevel] }}>
                Current: {currentLevel} ({currentScore}/100) — {LEVEL_RISK_LABEL[currentLevel]}
              </span>
            </div>
            {/* Multi-segment color bar */}
            <div className="h-3 w-full rounded-full bg-black/40 overflow-hidden flex p-0.5 border border-[var(--border)] relative">
              <div className="h-full bg-emerald-500 rounded-l" style={{ width: '30%' }} title="GREEN: Normal (<31)" />
              <div className="h-full bg-yellow-400" style={{ width: '25%' }} title="YELLOW: Moderate (31-55)" />
              <div className="h-full bg-orange-400" style={{ width: '20%' }} title="ORANGE: High Risk (56-75)" />
              <div className="h-full bg-red-500" style={{ width: '15%' }} title="RED: Critical (76-90)" />
              <div className="h-full bg-purple-500 rounded-r" style={{ width: '10%' }} title="BLACK: Emergency (91+)" />
              {/* Indicator needle */}
              <div
                className="absolute top-0 bottom-0 w-2 -ml-1 bg-white rounded-full shadow-lg border border-black transition-all"
                style={{ left: `${Math.min(99, Math.max(1, currentScore))}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-[var(--muted)] font-mono">
              <span>0 GREEN</span>
              <span>31 YELLOW</span>
              <span>56 ORANGE</span>
              <span>76 RED</span>
              <span>91 BLACK</span>
              <span>100</span>
            </div>
          </div>

          <RiskTimelineChart history={history} height={200} />
        </Panel>

        {/* 3. Crowd Density Heatmap (Configured Zones) */}
        <Panel title="Crowd Density Heatmap (Configured Zones)">
          <div className="space-y-2.5">
            {zones.map((z, idx) => {
              const density = z.density
              const maxD = 6.0
              const pct = Math.min(100, Math.max(0, (density / maxD) * 100))
              const hex = LEVEL_HEX[z.level]
              return (
                <div key={z.name} className="p-2.5 rounded-lg border border-[var(--border)] bg-[var(--panel-2)]/60 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-[var(--text)] flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: hex }} />
                      {z.name}
                    </span>
                    <span className="tabular-nums font-bold" style={{ color: hex }}>
                      {density.toFixed(1)} <span className="text-[10px] font-normal text-[var(--muted)]">ppm²</span>
                    </span>
                  </div>
                  {/* Heat bar */}
                  <div className="h-2 w-full bg-black/40 rounded-full overflow-hidden border border-[var(--border)]">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: hex,
                        boxShadow: `0 0 8px ${hex}88`,
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-[var(--muted)]">
                    <span>{z.people} people detected</span>
                    <RiskBadge level={z.level} />
                  </div>
                </div>
              )
            })}
          </div>
          <div className="mt-3 pt-2 border-t border-[var(--border)] flex items-center justify-between text-[10px] text-[var(--muted)]">
            <span>Critical limit: 5.0 ppm²</span>
            <span>Anonymous Zone Aggregation</span>
          </div>
        </Panel>
      </div>

      {/* 4. Crowd Flow Analytics (Inflow, outflow, imbalance, accumulation, speed, reverse-flow) */}
      <Panel
        title="Crowd Flow & Dynamics Analytics"
        actions={
          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            {isLive ? 'REAL CV OPTICAL FLOW' : 'OFFLINE'}
          </span>
        }
      >
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--panel-2)]/50">
            <span className="text-[10px] uppercase font-semibold text-[var(--muted)]">Inflow Rate</span>
            <div className="text-xl font-bold mt-1 tabular-nums">
              {zm?.flow?.inflow_rate_per_min != null ? `${zm.flow.inflow_rate_per_min}/min` : (isLive ? 'Calibrating' : '—')}
            </div>
            <span className="text-[10px] text-[var(--muted)]">Entrance gate ingress</span>
          </div>

          <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--panel-2)]/50">
            <span className="text-[10px] uppercase font-semibold text-[var(--muted)]">Outflow Rate</span>
            <div className="text-xl font-bold mt-1 tabular-nums">
              {zm?.flow?.outflow_rate_per_min != null ? `${zm.flow.outflow_rate_per_min}/min` : (isLive ? 'Calibrating' : '—')}
            </div>
            <span className="text-[10px] text-[var(--muted)]">Exit gate egress</span>
          </div>

          <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--panel-2)]/50">
            <span className="text-[10px] uppercase font-semibold text-[var(--muted)]">Flow Imbalance</span>
            <div className={`text-xl font-bold mt-1 tabular-nums ${
              (zm?.flow?.flow_imbalance_per_min ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'
            }`}>
              {zm?.flow?.flow_imbalance_per_min != null
                ? `${zm.flow.flow_imbalance_per_min > 0 ? '+' : ''}${zm.flow.flow_imbalance_per_min}/min`
                : (isLive ? '0/min' : '—')}
            </div>
            <span className="text-[10px] text-[var(--muted)]">Net accumulation delta</span>
          </div>

          <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--panel-2)]/50">
            <span className="text-[10px] uppercase font-semibold text-[var(--muted)]">Accumulation Rate</span>
            <div className="text-xl font-bold mt-1 tabular-nums">
              {zm?.accumulation_rate_ppm2_per_min != null
                ? `${zm.accumulation_rate_ppm2_per_min > 0 ? '+' : ''}${zm.accumulation_rate_ppm2_per_min} ppm²`
                : (isLive ? 'Stable' : '—')}
            </div>
            <span className="text-[10px] text-[var(--muted)]">Density delta / min</span>
          </div>

          <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--panel-2)]/50">
            <span className="text-[10px] uppercase font-semibold text-[var(--muted)]">Movement Speed</span>
            <div className="text-xl font-bold mt-1 tabular-nums">
              {dyn?.mean_velocity != null ? `${dyn.mean_velocity.toFixed(2)} px/f` : (hasData ? `${latest!.mean_motion.toFixed(2)}` : '—')}
            </div>
            <span className="text-[10px] text-[var(--muted)]">Optical flow velocity</span>
          </div>

          <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--panel-2)]/50">
            <span className="text-[10px] uppercase font-semibold text-[var(--muted)]">Reverse Flow</span>
            <div className="text-xl font-bold mt-1 tabular-nums">
              {dyn?.reverse_flow_ratio != null ? `${(dyn.reverse_flow_ratio * 100).toFixed(0)}%` : '0%'}
            </div>
            <span className="text-[10px] text-[var(--muted)]">Counter-flow conflict</span>
          </div>
        </div>
      </Panel>

      {/* 5. Live Crowd Video Feeds */}
      <Panel
        title="Live Video Sources & Feeds"
        actions={
          <Link to="/videos" className="text-xs text-[var(--accent)] flex items-center gap-1 hover:underline">
            Open Video Library <ArrowUpRight size={13} />
          </Link>
        }
      >
        {cameraFeeds.length === 0 ? (
          <EmptyState title="No video sources configured" hint="Upload videos in Crowd Videos to configure monitoring feeds." />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {cameraFeeds.slice(0, 8).map((v, i) => {
              const isCameraLive = status?.video_id === v.id && isLive
              const people = isCameraLive ? latest?.people_count ?? v.last_people : v.last_people
              const density = isCameraLive ? latest?.density_ppm2 ?? v.last_density : v.last_density
              const level = isCameraLive ? latest?.level ?? v.last_level : v.last_level

              return (
                <div
                  key={v.id}
                  onClick={() => navigate(`/videos/${v.id}`)}
                  className="rounded-lg border border-[var(--border)] bg-[var(--panel-2)] overflow-hidden cursor-pointer hover:border-[var(--accent)]/60 transition-all group"
                >
                  <div className="aspect-video bg-black relative">
                    <VideoThumb src={isCameraLive && latest?.annotated_frame ? latest.annotated_frame : v.thumbnail} />
                    <span
                      className={`absolute top-2 left-2 text-[10px] font-bold px-2 py-0.5 rounded shadow ${
                        isCameraLive ? 'bg-red-600 text-white animate-pulse' : 'bg-black/70 text-[var(--muted)]'
                      }`}
                    >
                      {isCameraLive ? '● LIVE' : v.status.toUpperCase()}
                    </span>
                    <span className="absolute bottom-1.5 right-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-black/80 text-white font-mono">
                      {formatDuration(v.duration_sec)}
                    </span>
                  </div>

                  <div className="p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-[var(--text)] truncate">Feed {String(i + 1).padStart(2, '0')}</span>
                      {level ? <RiskBadge level={level} /> : <span className="text-[10px] text-[var(--muted)]">Ready</span>}
                    </div>
                    <p className="text-xs text-[var(--muted)] truncate font-medium">{v.filename}</p>
                    <div className="flex items-center justify-between text-xs text-[var(--muted)] pt-1 border-t border-[var(--border)]">
                      <span>People: <span className="font-semibold text-[var(--text)]">{people ?? '--'}</span></span>
                      <span>Density: <span className="font-semibold text-[var(--text)]">{density != null ? `${density.toFixed(1)}/m²` : '--'}</span></span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Panel>

      {/* 6. Active Alerts & Recent Analyses */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Active Alerts */}
        <Panel
          title="Active Crowd Safety Alerts"
          actions={
            <Link to="/alerts" className="text-xs text-[var(--accent)] flex items-center gap-1 hover:underline">
              View All ({alerts.length}) <ArrowUpRight size={13} />
            </Link>
          }
        >
          {activeAlerts.length === 0 ? (
            <EmptyState title="No active alerts" hint="Alerts automatically appear when density or turbulence breaches safe limits." />
          ) : (
            <div className="space-y-2.5 max-h-[340px] overflow-y-auto pr-1">
              {activeAlerts.map((a) => (
                <div
                  key={a.id}
                  className="p-3 rounded-lg border border-red-500/40 bg-red-500/5 space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <RiskBadge level={a.level} />
                      <span className="text-xs font-bold text-[var(--text)]">{a.zone}</span>
                      <span className="text-[11px] text-[var(--muted)] font-mono">
                        Score: <span className="text-red-400 font-bold">{Math.round(a.score)}</span>
                      </span>
                    </div>
                    <button
                      disabled={acking === a.id}
                      onClick={() => handleAcknowledge(a.id)}
                      className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold flex items-center gap-1"
                    >
                      <Check size={12} /> Ack
                    </button>
                  </div>
                  <p className="text-xs text-[var(--muted)] leading-relaxed">{a.reason}</p>
                  {a.recommended_action && (
                    <p className="text-xs text-amber-300 font-medium">
                      Action: {a.recommended_action}
                    </p>
                  )}
                  <div className="flex items-center justify-between text-[10px] text-[var(--muted)] pt-1 border-t border-[var(--border)]">
                    <span>Source: {a.video_id ?? 'Live CCTV Feed'}</span>
                    <span>{new Date(a.created_at * 1000).toLocaleTimeString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* Recent Analyses Table */}
        <Panel
          title="Recent Video Analyses"
          actions={
            <Link to="/videos" className="text-xs text-[var(--accent)] flex items-center gap-1 hover:underline">
              All Videos <ArrowUpRight size={13} />
            </Link>
          }
        >
          {recentAnalyses.length === 0 ? (
            <EmptyState title="No recent analyses" hint="Start an analysis on an uploaded video to see historical records." />
          ) : (
            <div className="space-y-2 max-h-[340px] overflow-y-auto pr-1">
              {recentAnalyses.map((v) => (
                <div
                  key={v.id}
                  onClick={() => navigate(`/videos/${v.id}`)}
                  className="p-2.5 rounded-lg border border-[var(--border)] bg-[var(--panel-2)] hover:border-[var(--accent)]/50 transition-colors cursor-pointer flex items-center justify-between gap-3"
                >
                  <div className="min-w-0 flex items-center gap-2.5">
                    <div className="w-12 h-8 rounded bg-black shrink-0 overflow-hidden relative">
                      <VideoThumb src={v.thumbnail} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-[var(--text)] truncate">{v.filename}</p>
                      <p className="text-[10px] text-[var(--muted)]">
                        {v.category} · {formatDuration(v.duration_sec)} · {v.last_analyzed_at ? formatDate(v.last_analyzed_at) : 'Pending'}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <div className="text-right text-[11px]">
                      <div className="font-bold text-[var(--text)]">
                        {v.last_people != null ? `${v.last_people} people` : '--'}
                      </div>
                      <div className="text-[10px] text-[var(--muted)]">
                        {v.last_density != null ? `${v.last_density.toFixed(1)}/m²` : '--'}
                      </div>
                    </div>
                    {v.last_level ? (
                      <RiskBadge level={v.last_level} />
                    ) : (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--muted)] uppercase">
                        {v.status}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
