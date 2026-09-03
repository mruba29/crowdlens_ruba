import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { api } from './lib/api'
import type { AnalysisStatus, FrameMetric, HistoryPoint, Zone, Alert, Health } from './lib/types'

interface AppState {
  connected: boolean
  health: Health | null
  status: AnalysisStatus | null
  latest: FrameMetric | null
  history: HistoryPoint[]
  zones: Zone[]
  alerts: Alert[]
  refreshAlerts: () => Promise<void>
  refreshAll: () => Promise<void>
}

const Ctx = createContext<AppState | null>(null)

export function useApp(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp must be used within <AppProvider>')
  return v
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [latest, setLatest] = useState<FrameMetric | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [zones, setZones] = useState<Zone[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  const refreshAlerts = useCallback(async () => {
    try { setAlerts(await api.alerts()) } catch { /* offline */ }
  }, [])

  const refreshAll = useCallback(async () => {
    try {
      const [h, m] = await Promise.all([api.health().catch(() => null), api.metrics()])
      if (h) setHealth(h)
      setStatus((s) => ({ ...(s ?? ({} as AnalysisStatus)), status: m.status } as AnalysisStatus))
      setLatest(m.latest)
      setHistory(m.history)
      setZones(m.zones)
    } catch { /* offline */ }
    refreshAlerts()
  }, [refreshAlerts])

  // health poll (cheap, always)
  useEffect(() => {
    let alive = true
    const ping = () => api.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth(null))
    ping()
    const id = setInterval(ping, 4000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  // status poll (drives fallback + knows when to poll metrics harder)
  useEffect(() => {
    let alive = true
    const tick = () => api.analysisStatus().then((s) => alive && setStatus(s)).catch(() => {})
    tick()
    const id = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  // metrics fallback poll while processing (in case WS drops)
  useEffect(() => {
    if (status?.status !== 'processing') return
    const id = setInterval(async () => {
      try {
        const m = await api.metrics()
        setLatest((prev) => {
          if (m.latest && !m.latest.annotated_frame && prev?.annotated_frame) {
            m.latest.annotated_frame = prev.annotated_frame
          }
          return m.latest
        })
        setHistory(m.history); setZones(m.zones)
      } catch { /* ignore */ }
    }, 1500)
    return () => clearInterval(id)
  }, [status?.status])

  // initial alerts
  useEffect(() => { refreshAlerts() }, [refreshAlerts])

  // websocket
  useEffect(() => {
    let cancelled = false
    let retry: ReturnType<typeof setTimeout>
    const connect = () => {
      if (cancelled) return
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws`)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => { setConnected(false); if (!cancelled) retry = setTimeout(connect, 2000) }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'metrics' && msg.data) {
            if (msg.data.latest) {
              setLatest((prev) => {
                const next = msg.data.latest
                if (!next.annotated_frame && prev?.annotated_frame) {
                  next.annotated_frame = prev.annotated_frame
                }
                return next
              })
              setHistory((h) => {
                const p = msg.data.latest
                const point: HistoryPoint = {
                  t_offset_sec: p.t_offset_sec, people_count: p.people_count,
                  density_ppm2: p.density_ppm2, mean_motion: p.mean_motion,
                  turbulence: p.turbulence, score: p.score, level: p.level,
                }
                return [...h.slice(-599), point]
              })
            }
            if (msg.data.zones) setZones(msg.data.zones)
          } else if (msg.type === 'status' && msg.data) {
            setStatus(msg.data)
          } else if (msg.type === 'alert') {
            refreshAlerts()
          }
        } catch { /* ignore malformed */ }
      }
    }
    connect()
    return () => { cancelled = true; clearTimeout(retry); wsRef.current?.close() }
  }, [refreshAlerts])

  const value: AppState = {
    connected, health, status, latest, history, zones, alerts, refreshAlerts, refreshAll,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
