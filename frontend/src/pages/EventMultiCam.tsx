import React, { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Radio, Camera as CameraIcon, Film, CheckCircle2, CircleSlash } from 'lucide-react'
import { api } from '../lib/api'
import { Panel, EmptyState, PrivacyBadge, RiskBadge, VideoThumb, formatDate } from '../components/ui'
import { useApp } from '../store'
import type { EventVideoSource } from '../lib/types'

const SOURCE_ICON: Record<string, React.ComponentType<{ size?: number }>> = {
  CCTV: Radio, Drone: Radio, 'Uploaded Video': Film,
}

export default function EventMultiCam() {
  const { id } = useParams<{ id: string }>()
  const eventId = id ?? ''
  const navigate = useNavigate()
  const { status, latest } = useApp()
  const [sources, setSources] = useState<EventVideoSource[]>([])
  const [eventName, setEventName] = useState('')

  useEffect(() => {
    let alive = true
    const load = () => {
      api.getEvent(eventId).then((ev) => { if (alive) { setEventName(ev.name); setSources(ev.video_sources) } }).catch(() => {})
    }
    load()
    const iv = setInterval(load, 4000)
    return () => { alive = false; clearInterval(iv) }
  }, [eventId])

  const shown = sources.slice(0, 6)
  const extra = sources.length - shown.length

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to={`/events/${eventId}`} className="p-1.5 rounded-md hover:bg-white/5"><ArrowLeft size={18} /></Link>
          <div className="min-w-0">
            <h1 className="text-lg font-bold truncate">{eventName || 'Event'} — Multi-Camera View</h1>
            <p className="text-xs text-[var(--muted)]">Simultaneous monitoring across {sources.length} source{sources.length === 1 ? '' : 's'}</p>
          </div>
        </div>
        <PrivacyBadge />
      </div>

      {sources.length === 0 ? (
        <Panel><EmptyState title="No sources attached" hint="Attach video sources on the event page first." /></Panel>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {shown.map((v) => {
              const Icon = SOURCE_ICON[v.source_type] ?? CameraIcon
              const isLive = status?.video_id === v.id && status?.status === 'processing'
              const level = isLive ? latest?.level ?? v.last_level : v.last_level
              const people = isLive ? latest?.people_count ?? v.last_people : v.last_people
              return (
                <button key={v.id} onClick={() => navigate(`/videos/${v.id}`)}
                  className="text-left panel overflow-hidden border border-transparent hover:border-[var(--accent)]/50 transition-colors">
                  <div className="aspect-video bg-black relative">
                    <VideoThumb src={isLive && latest?.annotated_frame ? latest.annotated_frame : v.thumbnail} />
                    <span className={`absolute top-1.5 left-1.5 text-[10px] font-bold px-1.5 py-0.5 rounded ${
                      isLive ? 'bg-red-500 text-white' : 'bg-black/60 text-[var(--muted)]'}`}>
                      {isLive ? '● ANALYZING' : v.status.toUpperCase()}
                    </span>
                    <span className="absolute top-1.5 right-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-black/60 text-[var(--text)] flex items-center gap-1">
                      <Icon size={10} />{v.source_type}
                    </span>
                  </div>
                  <div className="p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium truncate">{v.camera_name ?? v.filename}</span>
                      {level ? <RiskBadge level={level} /> : <span className="text-[10px] text-[var(--muted)]">no data</span>}
                    </div>
                    <p className="text-[11px] text-[var(--muted)] truncate mt-0.5">{v.zone_name ?? 'No zone'} · People: <span className="text-[var(--text)]">{people ?? '--'}</span></p>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="text-[10px] text-[var(--muted)]">{v.capture_start_ts ? formatDate(v.capture_start_ts) : 'no timestamp'}</span>
                      {v.capture_start_ts ? (
                        <span className="text-[10px] text-emerald-400 flex items-center gap-0.5"><CheckCircle2 size={10} />sync ready</span>
                      ) : (
                        <span className="text-[10px] text-[var(--muted)] flex items-center gap-0.5"><CircleSlash size={10} />unavailable</span>
                      )}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
          {extra > 0 && (
            <p className="text-xs text-[var(--muted)] text-center">
              +{extra} more source{extra === 1 ? '' : 's'} — open the <Link to={`/events/${eventId}`} className="text-[var(--accent)]">event page</Link> or the timeline to see all of them.
            </p>
          )}
        </>
      )}
    </div>
  )
}
