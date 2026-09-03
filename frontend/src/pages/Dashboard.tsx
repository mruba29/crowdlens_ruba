import React from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../store'
import { Panel, StatCard, RiskGauge, RiskBadge, EmptyState, PrivacyBadge } from '../components/ui'
import { LEVEL_CLASS } from '../lib/types'

export default function Dashboard() {
  const { latest, history, zones, alerts, status } = useApp()
  const activeAlerts = alerts.filter((a) => a.status === 'ACTIVE')
  const maxDensity = history.length ? Math.max(...history.map((h) => h.density_ppm2)) : (latest?.density_ppm2 ?? 0)
  const hasData = !!latest

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Dashboard</h1>
          <p className="text-sm text-[var(--muted)]">Live crowd safety overview</p>
        </div>
        <PrivacyBadge />
      </div>

      {!hasData ? (
        <Panel>
          <EmptyState
            title="No video selected"
            hint="Go to Live Analysis, upload a crowd video and start analysis. Metrics shown here come only from real detection — nothing is simulated."
          />
          <div className="flex justify-center">
            <Link to="/live" className="px-4 py-2 rounded-md bg-[var(--accent)] text-white text-sm font-medium">
              Open Live Analysis
            </Link>
          </div>
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard label="Total People" value={latest!.people_count} sub="detected this frame" />
            <StatCard label="Max Density" value={`${maxDensity.toFixed(1)}/m²`} sub="peak this analysis" />
            <StatCard label="Crowd Risk (SRI)" value={Math.round(latest!.score)}
              sub={<RiskBadge level={latest!.level} />} />
            <StatCard label="Active Alerts" value={activeAlerts.length}
              sub={activeAlerts.length ? 'require acknowledgement' : 'none'}
              subClass={activeAlerts.length ? 'text-red-400' : 'text-[var(--muted)]'} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Panel title="Current Risk" className="lg:col-span-1 flex flex-col items-center">
              <RiskGauge score={latest!.score} level={latest!.level} label={latest!.label} />
              <p className="text-xs text-[var(--muted)] mt-3 text-center">
                Status: {status?.status ?? '—'} · t = {latest!.t_offset_sec.toFixed(1)}s
              </p>
            </Panel>

            <Panel title="Risk Factors" className="lg:col-span-2">
              <div className="space-y-2">
                {latest!.contributions.map((c) => (
                  <div key={c.factor}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="capitalize text-[var(--muted)]">{c.factor.replace('_', ' ')}</span>
                      <span className="tabular-nums">{c.value.toFixed(0)} / 100</span>
                    </div>
                    <div className="h-1.5 rounded bg-[var(--panel-2)] overflow-hidden">
                      <div className="h-full bg-[var(--accent)]" style={{ width: `${c.value}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          <Panel title="Zones">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {zones.map((z) => (
                <div key={z.name}
                  className={`rounded-md p-3 border ${
                    z.level === 'RED' || z.level === 'BLACK'
                      ? 'border-red-500/50 bg-red-500/5'
                      : z.level === 'ORANGE'
                      ? 'border-orange-500/40 bg-orange-500/5'
                      : 'border-[var(--border)]'
                  }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{z.name}</span>
                    <RiskBadge level={z.level} />
                  </div>
                  <div className="mt-2 text-xs text-[var(--muted)] space-y-0.5">
                    <div>People: <span className="text-[var(--text)]">{z.people}</span></div>
                    <div>Density: <span className="text-[var(--text)]">{z.density.toFixed(1)}/m²</span></div>
                    <div>Risk: <span className={LEVEL_CLASS[z.level]}>{Math.round(z.score)}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}
