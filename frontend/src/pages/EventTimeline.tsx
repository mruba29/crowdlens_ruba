import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Play, Pause, AlertTriangle, CheckCircle2, CircleSlash } from 'lucide-react'
import { api } from '../lib/api'
import { Panel, EmptyState, PrivacyBadge } from '../components/ui'
import type { EventDetail, TimelineEntry } from '../lib/types'

export default function EventTimeline() {
  const { id } = useParams<{ id: string }>()
  const eventId = id ?? ''
  const [ev, setEv] = useState<EventDetail | null>(null)
  const [t, setT] = useState<number | null>(null)
  const [entries, setEntries] = useState<TimelineEntry[]>([])
  const [playing, setPlaying] = useState(false)
  const videoRefs = useRef<Record<string, HTMLVideoElement | null>>({})

  useEffect(() => { api.getEvent(eventId).then(setEv).catch(() => {}) }, [eventId])

  // derive a sensible global range: prefer the event's own start/end, else
  // span every synchronized source's real clip coverage, else "now ± 30min".
  const range = useMemo(() => {
    if (!ev) return null
    if (ev.start_time && ev.end_time && ev.end_time > ev.start_time) {
      return { start: ev.start_time, end: ev.end_time }
    }
    const timed = ev.video_sources.filter((v) => v.capture_start_ts != null)
    if (timed.length) {
      const start = Math.min(...timed.map((v) => v.capture_start_ts!))
      const end = Math.max(...timed.map((v) => v.capture_start_ts! + (v.duration_sec ?? 0)))
      return { start, end: Math.max(end, start + 1) }
    }
    const now = Date.now() / 1000
    return { start: now - 1800, end: now + 1800 }
  }, [ev])

  useEffect(() => { if (range && t === null) setT(range.start) }, [range, t])

  // fetch synchronization state for the chosen instant
  useEffect(() => {
    if (t == null) return
    let alive = true
    api.eventTimeline(eventId, t).then((r) => alive && setEntries(r)).catch(() => {})
    return () => { alive = false }
  }, [eventId, t])

  // drive playback: advance t once per second while playing, seek each
  // synced <video> to its real computed offset, and never touch an
  // unsynchronized source's playback state.
  useEffect(() => {
    if (!playing || !range) return
    const iv = setInterval(() => {
      setT((prev) => {
        const next = (prev ?? range.start) + 1
        return next > range.end ? range.start : next
      })
    }, 1000)
    return () => clearInterval(iv)
  }, [playing, range])

  useEffect(() => {
    entries.forEach((e) => {
      const el = videoRefs.current[e.video_id]
      if (!el) return
      if (e.sync_status === 'synced' && e.source_offset_sec != null) {
        if (Math.abs(el.currentTime - e.source_offset_sec) > 0.75) el.currentTime = e.source_offset_sec
        if (playing && el.paused) el.play().catch(() => {})
        if (!playing && !el.paused) el.pause()
      } else if (!el.paused) {
        el.pause()
      }
    })
  }, [entries, playing])

  if (!ev || !range || t == null) return <Panel><EmptyState title="Loading…" /></Panel>

  const pct = ((t - range.start) / (range.end - range.start)) * 100

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to={`/events/${eventId}`} className="p-1.5 rounded-md hover:bg-white/5"><ArrowLeft size={18} /></Link>
          <div className="min-w-0">
            <h1 className="text-lg font-bold truncate">{ev.name} — Global Timeline</h1>
            <p className="text-xs text-[var(--muted)]">Time frame of reference · one shared clock across every attached source</p>
          </div>
        </div>
        <PrivacyBadge />
      </div>

      <Panel>
        <div className="flex items-center gap-3">
          <button onClick={() => setPlaying((p) => !p)}
            className="p-2 rounded-md bg-[var(--accent)] text-white shrink-0">
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <div className="flex-1">
            <input type="range" min={range.start} max={range.end} step={1} value={t}
              onChange={(e) => setT(parseFloat(e.target.value))}
              className="w-full accent-[var(--accent)]" />
            <div className="flex justify-between text-[10px] text-[var(--muted)] mt-0.5">
              <span>{new Date(range.start * 1000).toLocaleTimeString()}</span>
              <span className="tabular-nums text-[var(--text)] font-semibold text-xs">{new Date(t * 1000).toLocaleTimeString()}</span>
              <span>{new Date(range.end * 1000).toLocaleTimeString()}</span>
            </div>
          </div>
        </div>
        <p className="text-[10px] text-[var(--muted)] mt-2">
          Position {pct.toFixed(0)}% across the event window. Sources with a declared recording start time seek to their real computed offset; sources without one never fake a position.
        </p>
      </Panel>

      {entries.length === 0 ? (
        <Panel><EmptyState title="No video sources on this event" /></Panel>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {entries.map((e) => (
            <Panel key={e.video_id} title={e.camera_name ?? e.filename} actions={<SyncPill status={e.sync_status} />}>
              <div className="aspect-video rounded-md bg-black overflow-hidden flex items-center justify-center">
                {e.sync_status === 'synced' ? (
                  <video ref={(el) => { videoRefs.current[e.video_id] = el }} muted playsInline
                    src={api.videoUrl(e.video_id)} className="w-full h-full object-contain" />
                ) : e.sync_status === 'out_of_range' ? (
                  <div className="text-center px-3">
                    <AlertTriangle size={20} className="mx-auto text-yellow-400 mb-1" />
                    <p className="text-[11px] text-[var(--muted)]">Outside this clip's recorded range at the selected time.</p>
                  </div>
                ) : (
                  <div className="text-center px-3">
                    <CircleSlash size={20} className="mx-auto text-[var(--muted)] mb-1" />
                    <p className="text-[11px] text-[var(--muted)] font-medium">Synchronization unavailable</p>
                    <p className="text-[10px] text-[var(--muted)] mt-0.5">No recording start time was set for this source.</p>
                  </div>
                )}
              </div>
              <dl className="text-[11px] text-[var(--muted)] mt-2 space-y-0.5">
                <Row k="Zone" v={e.zone_name ?? '—'} />
                <Row k="Source type" v={e.source_type} />
                <Row k="Source-level timestamp" v={e.capture_start_ts ? new Date(e.capture_start_ts * 1000).toLocaleString() : '—'} />
                <Row k="Sync offset" v={e.sync_offset_sec != null ? `${e.sync_offset_sec.toFixed(1)}s` : '—'} />
              </dl>
            </Panel>
          ))}
        </div>
      )}
    </div>
  )
}

function SyncPill({ status }: { status: TimelineEntry['sync_status'] }) {
  if (status === 'synced')
    return <span className="text-[10px] font-semibold text-emerald-400 flex items-center gap-1"><CheckCircle2 size={11} />SYNCED</span>
  if (status === 'out_of_range')
    return <span className="text-[10px] font-semibold text-yellow-400 flex items-center gap-1"><AlertTriangle size={11} />OUT OF RANGE</span>
  return <span className="text-[10px] font-semibold text-[var(--muted)] flex items-center gap-1"><CircleSlash size={11} />UNAVAILABLE</span>
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between gap-2"><dt>{k}</dt><dd className="text-[var(--text)] text-right truncate">{v}</dd></div>
}
