import React from 'react'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { useApp } from '../store'
import { Panel, EmptyState, PrivacyBadge } from '../components/ui'

const axis = { fontSize: 11, fill: '#8b93a7' }
const grid = '#262c3a'
const tip = { background: '#131722', border: '1px solid #262c3a', fontSize: 12, borderRadius: 8 }

export default function CrowdAnalytics() {
  const { history } = useApp()

  if (history.length < 2) {
    return (
      <div className="space-y-5">
        <Header />
        <Panel><EmptyState title="No crowd data available" hint="Run an analysis in Live Analysis — charts fill in as frames are processed." /></Panel>
      </div>
    )
  }

  const data = history.map((h) => ({
    t: Number(h.t_offset_sec.toFixed(1)),
    people: h.people_count,
    density: Number(h.density_ppm2.toFixed(2)),
    movement: Number(h.mean_motion.toFixed(2)),
    score: Number(h.score.toFixed(1)),
  }))

  return (
    <div className="space-y-5">
      <Header />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Chart title="People Count Over Time">
          <LineChart data={data}>
            <CartesianGrid stroke={grid} strokeDasharray="3 3" />
            <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} allowDecimals={false} />
            <Tooltip contentStyle={tip} />
            <Line type="monotone" dataKey="people" stroke="#3b82f6" strokeWidth={2} dot={false} />
          </LineChart>
        </Chart>

        <Chart title="Crowd Density (people/m²)">
          <AreaChart data={data}>
            <CartesianGrid stroke={grid} strokeDasharray="3 3" />
            <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} />
            <Tooltip contentStyle={tip} />
            <Area type="monotone" dataKey="density" stroke="#22d3ee" fill="#22d3ee22" strokeWidth={2} />
          </AreaChart>
        </Chart>

        <Chart title="Movement (mean optical flow)">
          <LineChart data={data}>
            <CartesianGrid stroke={grid} strokeDasharray="3 3" />
            <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} />
            <Tooltip contentStyle={tip} />
            <Line type="monotone" dataKey="movement" stroke="#a855f7" strokeWidth={2} dot={false} />
          </LineChart>
        </Chart>

        <Chart title="Risk Score Over Time">
          <AreaChart data={data}>
            <CartesianGrid stroke={grid} strokeDasharray="3 3" />
            <XAxis dataKey="t" tick={axis} /><YAxis domain={[0, 100]} tick={axis} />
            <Tooltip contentStyle={tip} />
            <ReferenceLine y={56} stroke="#fb923c" strokeDasharray="4 4" />
            <ReferenceLine y={76} stroke="#f87171" strokeDasharray="4 4" />
            <Area type="monotone" dataKey="score" stroke="#fb923c" fill="#fb923c22" strokeWidth={2} />
          </AreaChart>
        </Chart>
      </div>
    </div>
  )
}

function Header() {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-xl font-bold">Crowd Analytics</h1>
        <p className="text-sm text-[var(--muted)]">Core metrics over the current analysis</p>
      </div>
      <PrivacyBadge />
    </div>
  )
}

function Chart({ title, children }: { title: string; children: React.ReactElement }) {
  return (
    <Panel title={title}>
      <ResponsiveContainer width="100%" height={220}>{children}</ResponsiveContainer>
    </Panel>
  )
}
