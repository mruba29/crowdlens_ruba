import React from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { HistoryPoint } from '../lib/types'
import { EmptyState } from './ui'

const axis = { fontSize: 11, fill: '#8a938d' }
const grid = '#2b3230'
const tip = { background: '#191d1c', border: '1px solid #2b3230', fontSize: 12, borderRadius: 8 }

/** Risk Score vs Time — shared by the Dashboard's "Crowd Risk Overview" and
 * the video detail page's "Risk Timeline". Reads straight off the same
 * `history` the app already collects (see store.tsx); never invents points. */
export function RiskTimelineChart({ history, height = 220 }: { history: HistoryPoint[]; height?: number }) {
  if (history.length < 2) {
    return <EmptyState title="No risk data available" hint="Start an analysis on a crowd video — the risk trend appears here as frames are processed." />
  }
  const data = history.map((h) => ({ t: Number(h.t_offset_sec.toFixed(1)), score: Number(h.score.toFixed(1)) }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data}>
        <CartesianGrid stroke={grid} strokeDasharray="3 3" />
        <XAxis dataKey="t" tick={axis} unit="s" />
        <YAxis domain={[0, 100]} tick={axis} />
        <Tooltip contentStyle={tip} />
        <ReferenceLine y={56} stroke="#fb923c" strokeDasharray="4 4" label={{ value: 'ORANGE (56)', fill: '#fb923c', fontSize: 10 }} />
        <ReferenceLine y={76} stroke="#f87171" strokeDasharray="4 4" label={{ value: 'RED (76)', fill: '#f87171', fontSize: 10 }} />
        <Area type="monotone" dataKey="score" stroke="#fb923c" fill="#fb923c22" strokeWidth={2} name="Risk Score" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** People count vs Time timeline */
export function PeopleTimelineChart({
  data,
  height = 200,
}: {
  data: { t_offset_sec: number; people_count: number; density_ppm2?: number }[]
  height?: number
}) {
  if (data.length < 2) {
    return <EmptyState title="No people count history" hint="Timeline populates dynamically as frames are analyzed by the CV pipeline." />
  }
  const chartData = data.map((d) => ({
    t: Number(d.t_offset_sec.toFixed(1)),
    people: d.people_count,
    density: d.density_ppm2 != null ? Number(d.density_ppm2.toFixed(2)) : undefined,
  }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData}>
        <CartesianGrid stroke={grid} strokeDasharray="3 3" />
        <XAxis dataKey="t" tick={axis} unit="s" />
        <YAxis tick={axis} />
        <Tooltip contentStyle={tip} />
        <Area type="monotone" dataKey="people" stroke="#34d399" fill="#34d39922" strokeWidth={2} name="People Detected" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Reads the trend direction straight from the same history — "Increasing /
 * Stable / Decreasing", no separate model. */
export function riskTrend(history: HistoryPoint[]): 'Increasing' | 'Stable' | 'Decreasing' | null {
  if (history.length < 4) return null
  const n = history.length
  const recent = history.slice(-Math.max(3, Math.floor(n / 3)))
  const earlier = history.slice(0, Math.max(3, Math.floor(n / 3)))
  const avg = (arr: HistoryPoint[]) => arr.reduce((s, h) => s + h.score, 0) / arr.length
  const delta = avg(recent) - avg(earlier)
  if (delta > 4) return 'Increasing'
  if (delta < -4) return 'Decreasing'
  return 'Stable'
}

