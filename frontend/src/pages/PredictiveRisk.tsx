import React, { useEffect, useState } from 'react'
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { TrendingUp, AlertTriangle, ShieldCheck, Gauge, Clock, ArrowRight, Layers, Sliders } from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, StatCard, RiskBadge, EmptyState, PrivacyBadge, Dot } from '../components/ui'
import type { PredictiveForecast, RiskLevel } from '../lib/types'
import { LEVEL_HEX } from '../lib/types'

const axis = { fontSize: 11, fill: '#8a938d' }
const grid = '#2b3230'
const tip = { background: '#191d1c', border: '1px solid #2b3230', fontSize: 12, borderRadius: 8 }

export default function PredictiveRisk() {
  const { latest, status, health } = useApp()
  const [forecast, setForecast] = useState<PredictiveForecast | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeScenario, setActiveScenario] = useState<number>(0)

  useEffect(() => {
    let alive = true
    const fetchForecast = () => {
      api.predictiveForecast()
        .then((data) => {
          if (alive) {
            setForecast(data)
            setLoading(false)
          }
        })
        .catch(() => {
          if (alive) setLoading(false)
        })
    }
    fetchForecast()
    const id = setInterval(fetchForecast, 3000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const isLive = status?.status === 'processing' || status?.status === 'paused'
  const timeToCrit = forecast?.time_to_critical_min
  const accumRate = forecast?.accumulation_rate_ppm2_per_min ?? 0

  const chartData = forecast?.projections.map((p) => ({
    time: `+${p.minutes_ahead}m`,
    density: p.projected_density_ppm2,
    score: p.projected_risk_score,
    people: p.projected_people,
    level: p.projected_level,
  })) ?? []

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <TrendingUp size={28} className="text-[var(--accent)]" />
          <div>
            <h1 className="text-xl font-bold leading-tight">Predictive Crowd Risk & Trend Forecasting</h1>
            <p className="text-sm text-[var(--muted)] leading-tight">
              Dynamic extrapolation based on real optical flow & accumulation rates · Modelled surge simulations
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Dot ok={isLive} label={isLive ? 'LIVE CV DYNAMICS' : 'STATIC BASELINE'} />
          <PrivacyBadge />
        </div>
      </div>

      {/* Critical Early Warning Banner if Time-to-Critical is active */}
      {timeToCrit != null && timeToCrit < 15 && (
        <div className="rounded-lg border border-red-500/50 bg-red-500/10 p-4 flex items-start gap-3">
          <AlertTriangle size={22} className="text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold text-red-400 uppercase tracking-wide">
              Critical Density Threshold Forecast — Action Recommended
            </h3>
            <p className="text-xs text-[var(--text)] mt-1">
              At the current accumulation rate of <span className="font-semibold text-red-300">+{accumRate.toFixed(2)} ppm²/min</span>,
              crowd density is projected to breach the safety limit of <span className="font-semibold">5.0 people/m²</span> in approximately{' '}
              <span className="font-bold underline text-red-300">{timeToCrit} minutes</span>.
            </p>
            <p className="text-[11px] text-[var(--muted)] mt-1">
              Recommended operational action: Initiate early ingress throttling and activate auxiliary exit gates.
            </p>
          </div>
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Current Density"
          value={forecast ? `${forecast.current_density.toFixed(2)}/m²` : '—'}
          sub={`Critical threshold: ${forecast?.critical_threshold.toFixed(1) ?? '5.0'}/m²`}
        />
        <StatCard
          label="Accumulation Rate"
          value={forecast ? `${accumRate >= 0 ? '+' : ''}${accumRate.toFixed(2)}/min` : '—'}
          sub={accumRate > 0.05 ? 'Crowd accumulating' : accumRate < -0.05 ? 'Crowd dispersing' : 'Equilibrium'}
          subClass={accumRate > 0.05 ? 'text-orange-400' : 'text-emerald-400'}
        />
        <StatCard
          label="Time to Critical"
          value={timeToCrit != null ? `${timeToCrit} min` : 'Stable / >30m'}
          sub={timeToCrit != null ? 'Predicted threshold breach' : 'No imminent surge breach'}
          subClass={timeToCrit != null && timeToCrit < 15 ? 'text-red-400 font-semibold' : 'text-[var(--muted)]'}
        />
        <StatCard
          label="Projected 15m Risk"
          value={
            chartData.length > 4 ? (
              <span className="flex items-center gap-2">
                <span>{Math.round(chartData[4].score)}</span>
                <RiskBadge level={chartData[4].level} />
              </span>
            ) : '—'
          }
          sub="30-minute forecasting horizon"
        />
      </div>

      {/* Projections & Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Panel title="Crowd Density Horizon (Next 30 Minutes)" className="lg:col-span-2">
          {chartData.length < 2 ? (
            <EmptyState title="No forecast data" hint="Start video analysis to calculate real-time accumulation trends." />
          ) : (
            <div className="space-y-3">
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={chartData}>
                  <CartesianGrid stroke={grid} strokeDasharray="3 3" />
                  <XAxis dataKey="time" tick={axis} />
                  <YAxis domain={[0, Math.max(6, Math.ceil(Math.max(...chartData.map((d) => d.density)) + 1))]} tick={axis} />
                  <Tooltip contentStyle={tip} />
                  <ReferenceLine y={forecast?.critical_threshold ?? 5.0} stroke="#f87171" strokeDasharray="4 4" label={{ value: 'CRITICAL 5.0/m²', fill: '#f87171', fontSize: 10 }} />
                  <Area type="monotone" dataKey="density" stroke="#34d399" fill="#34d39922" strokeWidth={2.5} name="Projected Density (ppm²)" />
                </AreaChart>
              </ResponsiveContainer>
              <div className="flex items-center justify-between text-xs text-[var(--muted)] pt-2 border-t border-[var(--border)]">
                <span>Provenance: Linear-trend extrapolation of real CV optical flow</span>
                <span>Critical Safety Limit: 5.0 people/m²</span>
              </div>
            </div>
          )}
        </Panel>

        {/* Risk Score Projection */}
        <Panel title="Predicted Safety Risk Index">
          {chartData.length < 2 ? (
            <EmptyState title="No risk data" hint="Analyzing video feed..." />
          ) : (
            <div className="space-y-4">
              <ResponsiveContainer width="100%" height={190}>
                <LineChart data={chartData}>
                  <CartesianGrid stroke={grid} strokeDasharray="3 3" />
                  <XAxis dataKey="time" tick={axis} />
                  <YAxis domain={[0, 100]} tick={axis} />
                  <Tooltip contentStyle={tip} />
                  <ReferenceLine y={56} stroke="#fb923c" strokeDasharray="3 3" />
                  <ReferenceLine y={76} stroke="#f87171" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="score" stroke="#fb923c" strokeWidth={2} dot={false} name="Risk Score" />
                </LineChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[var(--muted)]">Now (+0m):</span>
                  <span className="font-semibold">{chartData[0]?.score ?? '--'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[var(--muted)]">Projected (+10m):</span>
                  <span className="font-semibold">{chartData[3]?.score ?? '--'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[var(--muted)]">Projected (+30m):</span>
                  <span className="font-semibold">{chartData[6]?.score ?? '--'}</span>
                </div>
              </div>
            </div>
          )}
        </Panel>
      </div>

      {/* Scenario Modeling / What-If Simulations */}
      <Panel title="Public Safety What-If Scenario Simulations">
        <div className="mb-3">
          <p className="text-xs text-[var(--muted)]">
            Explore predictive impact under simulated stress conditions to plan preventative crowd control measures.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {forecast?.scenarios.map((sc, i) => {
            const isSelected = activeScenario === i
            return (
              <div
                key={sc.name}
                onClick={() => setActiveScenario(i)}
                className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-[var(--accent)] bg-[var(--accent)]/10 ring-1 ring-[var(--accent)]'
                    : 'border-[var(--border)] bg-[var(--panel-2)] hover:border-white/20'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                    sc.type === 'observed'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                      : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                  }`}>
                    {sc.type === 'observed' ? 'REAL CV BASELINE' : 'MODELLED SCENARIO'}
                  </span>
                  <span className="text-xs text-[var(--muted)]">
                    {sc.time_to_critical_min ? `${sc.time_to_critical_min}m to crit` : 'Stable'}
                  </span>
                </div>
                <h4 className="text-sm font-semibold mt-2">{sc.name}</h4>
                <p className="text-xs text-[var(--muted)] mt-1 leading-relaxed">{sc.description}</p>
                <div className="mt-3 pt-2.5 border-t border-[var(--border)] flex items-center justify-between text-xs">
                  <span className="text-[var(--muted)]">Projected Peak:</span>
                  <span className="font-bold tabular-nums text-[var(--text)]">{sc.projected_peak_density} ppm²</span>
                </div>
              </div>
            )
          })}
        </div>
        <p className="text-[11px] text-[var(--muted)] mt-3">
          Disclaimer: Observed dynamic baseline is calculated directly from live video detections; scenario simulations are modelled projections for emergency preparedness.
        </p>
      </Panel>
    </div>
  )
}
