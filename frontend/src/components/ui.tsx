import React from 'react'
import type { RiskLevel } from '../lib/types'
import { LEVEL_HEX } from '../lib/types'

export function Panel({ title, children, className = '', actions }: {
  title?: string; children: React.ReactNode; className?: string; actions?: React.ReactNode
}) {
  return (
    <section className={`panel p-4 ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between mb-3">
          {title && <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function StatCard({ label, value, sub, subClass }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; subClass?: string
}) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {sub != null && <div className={`mt-0.5 text-xs ${subClass ?? 'text-[var(--muted)]'}`}>{sub}</div>}
    </div>
  )
}

export function RiskBadge({ level }: { level: RiskLevel | string }) {
  const hex = LEVEL_HEX[level as RiskLevel] ?? '#8b93a7'
  return (
    <span className="px-2 py-0.5 rounded text-xs font-bold tracking-wide"
      style={{ color: hex, backgroundColor: `${hex}1f`, border: `1px solid ${hex}55` }}>
      {level}
    </span>
  )
}

export function RiskGauge({ score, level, label, size = 200 }: {
  score: number; level: RiskLevel; label: string; size?: number
}) {
  const hex = LEVEL_HEX[level] ?? '#8b93a7'
  const r = size / 2 - 14
  const circ = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, score)) / 100
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#2b3230" strokeWidth={12} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={hex} strokeWidth={12} fill="none"
          strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ * (1 - pct)}
          style={{ transition: 'stroke-dashoffset .5s ease, stroke .3s ease' }} />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-4xl font-bold tabular-nums" style={{ color: hex }}>{Math.round(score)}</span>
        <span className="text-sm font-semibold mt-0.5" style={{ color: hex }}>{level}</span>
        <span className="text-[11px] uppercase tracking-wider text-[var(--muted)]">{label}</span>
      </div>
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-1 py-12 px-4">
      <p className="text-sm text-[var(--text)]">{title}</p>
      {hint && <p className="text-xs text-[var(--muted)] max-w-sm">{hint}</p>}
    </div>
  )
}

export function PrivacyBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-semibold
      bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
      PRIVACY MODE: ON
    </span>
  )
}

export function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
      <span className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-400 pulse-dot' : 'bg-red-400'}`} />
      {label}
    </span>
  )
}
