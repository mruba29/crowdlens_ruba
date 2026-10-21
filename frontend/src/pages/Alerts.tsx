import React, { useState } from 'react'
import { AlertTriangle, Check } from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, RiskBadge, EmptyState } from '../components/ui'
import type { RiskLevel } from '../lib/types'

const FILTERS: { label: string; match: (l: RiskLevel) => boolean }[] = [
  { label: 'All', match: () => true },
  { label: 'Warning', match: (l) => l === 'YELLOW' },
  { label: 'High Risk', match: (l) => l === 'ORANGE' },
  { label: 'Critical', match: (l) => l === 'RED' || l === 'BLACK' },
]

export default function Alerts() {
  const { alerts, refreshAlerts } = useApp()
  const [filter, setFilter] = useState(0)
  const [busy, setBusy] = useState<number | null>(null)

  const shown = alerts.filter((a) => FILTERS[filter].match(a.level))

  async function ack(id: number) {
    setBusy(id)
    try { await api.acknowledgeAlert(id); await refreshAlerts() } finally { setBusy(null) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Alerts</h1>
          <p className="text-sm text-[var(--muted)]">
            Generated automatically when crowd risk reaches RED or BLACK. Decision-support only —
            a human operator must acknowledge.
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        {FILTERS.map((f, i) => (
          <button key={f.label} onClick={() => setFilter(i)}
            className={`px-3 py-1.5 rounded-md text-sm border ${
              filter === i ? 'bg-[var(--accent)]/15 border-[var(--accent)]/50 text-[var(--text)]'
                : 'border-[var(--border)] text-[var(--muted)]'
            }`}>
            {f.label}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <Panel><EmptyState title="No alerts" hint="When a zone reaches critical risk during analysis, an alert appears here." /></Panel>
      ) : (
        <div className="space-y-3">
          {shown.map((a) => (
            <Panel key={a.id} className={a.status === 'ACTIVE' ? 'border-red-500/50' : ''}>
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={16} className="text-red-400" />
                    <span className="font-bold">{a.alert_type ? a.alert_type.replace(/_/g, ' ') : 'HIGH CROWD RISK'}</span>
                    <RiskBadge level={a.level} />
                    <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--panel-2)] border border-[var(--border)] text-[var(--muted)]">
                      {a.status}
                    </span>
                  </div>
                  <p className="text-sm mt-1.5">Zone: <span className="font-medium">{a.zone}</span> · Risk Score: <span className="tabular-nums">{Math.round(a.score)}</span></p>
                  <p className="text-sm text-[var(--muted)] mt-1">Trigger signals: {a.reason}</p>
                  {a.recommended_action && (
                    <p className="text-sm mt-1"><span className="text-[var(--muted)]">Recommended action:</span> <span className="font-medium">{a.recommended_action}</span></p>
                  )}
                  <p className="text-xs text-[var(--muted)] mt-1">
                    #{String(a.id).padStart(3, '0')} · {new Date(a.created_at * 1000).toLocaleTimeString()}
                    {a.acknowledged_at && <> · acknowledged {new Date(a.acknowledged_at * 1000).toLocaleTimeString()}</>}
                  </p>
                </div>
                <button disabled={a.status !== 'ACTIVE' || busy === a.id} onClick={() => ack(a.id)}
                  className="px-3 py-1.5 rounded-md bg-emerald-600 text-white text-sm flex items-center gap-1.5">
                  <Check size={14} /> Acknowledge
                </button>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  )
}
