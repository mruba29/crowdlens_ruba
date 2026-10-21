import React from 'react'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import { useApp } from '../store'
import { Panel, EmptyState, PrivacyBadge } from '../components/ui'

const axis = { fontSize: 11, fill: '#8a938d' }
const grid = '#2b3230'
const tip = { background: '#191d1c', border: '1px solid #2b3230', fontSize: 12, borderRadius: 8 }

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

  // Phase 2: zone-aware series — only present on frames where the video was
  // attached to an event zone. Real values only; never backfilled/guessed.
  const zoneData = history
    .filter((h) => h.zone_metrics?.available)
    .map((h) => {
      const zm = h.zone_metrics!
      return {
        t: Number(h.t_offset_sec.toFixed(1)),
        zoneDensity: zm.density_status === 'ok' ? zm.density_ppm2 : null,
        occupancy: zm.occupancy_status === 'ok' ? zm.occupancy_pct : null,
        inflow: zm.flow?.reason === null ? zm.flow.inflow_rate_per_min : null,
        outflow: zm.flow?.reason === null ? zm.flow.outflow_rate_per_min : null,
        imbalance: zm.flow?.reason === null ? zm.flow.flow_imbalance_per_min : null,
      }
    })
  const zoneName = history.find((h) => h.zone_metrics?.available)?.zone_metrics?.zone_name
  const hasFlow = zoneData.some((d) => d.inflow != null)

  return (
    <div className="space-y-5">
      <Header />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Chart title="People Count Over Time">
          <LineChart data={data}>
            <CartesianGrid stroke={grid} strokeDasharray="3 3" />
            <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} allowDecimals={false} />
            <Tooltip contentStyle={tip} />
            <Line type="monotone" dataKey="people" stroke="#34d399" strokeWidth={2} dot={false} />
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

      <div>
        <h2 className="text-sm font-semibold text-[var(--muted)] mb-2 uppercase tracking-wider">
          Zone Analytics {zoneName ? `— ${zoneName}` : ''}
        </h2>
        {zoneData.length === 0 ? (
          <Panel>
            <EmptyState title="Not Available" hint="This video isn't attached to an event zone, so occupancy/inflow/outflow can't be computed — attach it to a zone on the event page to unlock these charts." />
          </Panel>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Chart title="Occupancy vs Time (%)">
              <AreaChart data={zoneData}>
                <CartesianGrid stroke={grid} strokeDasharray="3 3" />
                <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} domain={[0, 'auto']} />
                <Tooltip contentStyle={tip} />
                <Area type="monotone" dataKey="occupancy" stroke="#facc15" fill="#facc1522" strokeWidth={2} connectNulls />
              </AreaChart>
            </Chart>

            <Chart title="Zone Density vs Time (people/m²)">
              <AreaChart data={zoneData}>
                <CartesianGrid stroke={grid} strokeDasharray="3 3" />
                <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} />
                <Tooltip contentStyle={tip} />
                <Area type="monotone" dataKey="zoneDensity" stroke="#34d399" fill="#34d39922" strokeWidth={2} connectNulls />
              </AreaChart>
            </Chart>

            {!hasFlow ? (
              <Panel title="Inflow vs Outflow" className="lg:col-span-2">
                <EmptyState title="Not Available / Requires Calibration"
                  hint="This zone isn't an entrance/exit/bottleneck, or the tracker hasn't collected enough real crossings yet." />
              </Panel>
            ) : (
              <>
                <Chart title="Inflow vs Outflow (people/min)">
                  <LineChart data={zoneData}>
                    <CartesianGrid stroke={grid} strokeDasharray="3 3" />
                    <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} />
                    <Tooltip contentStyle={tip} /><Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="inflow" name="Inflow" stroke="#34d399" strokeWidth={2} dot={false} connectNulls />
                    <Line type="monotone" dataKey="outflow" name="Outflow" stroke="#f87171" strokeWidth={2} dot={false} connectNulls />
                  </LineChart>
                </Chart>

                <Chart title="Flow Imbalance vs Time (inflow − outflow)">
                  <AreaChart data={zoneData}>
                    <CartesianGrid stroke={grid} strokeDasharray="3 3" />
                    <XAxis dataKey="t" tick={axis} /><YAxis tick={axis} />
                    <Tooltip contentStyle={tip} />
                    <ReferenceLine y={0} stroke="#8a938d" />
                    <Area type="monotone" dataKey="imbalance" stroke="#fb923c" fill="#fb923c22" strokeWidth={2} connectNulls />
                  </AreaChart>
                </Chart>
              </>
            )}
          </div>
        )}
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
