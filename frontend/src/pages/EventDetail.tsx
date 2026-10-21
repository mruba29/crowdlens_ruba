import React, { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Plus, Trash2, Camera as CameraIcon, MapPin, Clock, CalendarClock,
  Grid3x3, Radio, Upload, Link2, X,
} from 'lucide-react'
import { api } from '../lib/api'
import { Panel, EmptyState, PrivacyBadge, RiskBadge, VideoThumb, formatDate, formatDuration } from '../components/ui'
import { VIDEO_CATEGORIES, SOURCE_TYPES, ZONE_ROLES, SPATIAL_CONTEXTS, LEVEL_HEX } from '../lib/types'
import type { EventDetail as EventDetailT, EventZone, EventCamera, VideoRecord, SourceType, ZoneRole, SpatialContext, RiskLevel } from '../lib/types'

const ROLE_COLOR: Record<ZoneRole, string> = {
  entrance: '#34d399', exit: '#60a5fa', bottleneck: '#fb923c', restricted: '#f87171', general: '#8a938d',
}

/** For a zone, the highest last-known risk level among its attached video
 * sources — real, already-computed data (never recomputed here). Powers the
 * map's heatmap shading. null when no attached source has ever been
 * analyzed, which the map shows as "no data" rather than guessing a color. */
function zoneHeat(zone: EventZone, ev: EventDetailT): RiskLevel | null {
  const order: RiskLevel[] = ['GREEN', 'YELLOW', 'ORANGE', 'RED', 'BLACK']
  const levels = ev.video_sources.filter((v) => v.zone_id === zone.id && v.last_level).map((v) => v.last_level as RiskLevel)
  if (!levels.length) return null
  return levels.reduce((worst, l) => order.indexOf(l) > order.indexOf(worst) ? l : worst, levels[0])
}

export default function EventDetail() {
  const { id } = useParams<{ id: string }>()
  const eventId = id ?? ''
  const navigate = useNavigate()
  const [ev, setEv] = useState<EventDetailT | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = React.useCallback(() => {
    api.getEvent(eventId).then(setEv).catch(() => setNotFound(true))
  }, [eventId])

  useEffect(() => { load() }, [load])
  useEffect(() => { const iv = setInterval(load, 5000); return () => clearInterval(iv) }, [load])

  if (notFound) {
    return (
      <Panel>
        <EmptyState title="Event not found" hint="It may have been deleted." />
        <div className="flex justify-center"><Link to="/events" className="text-sm text-[var(--accent)]">Back to Events</Link></div>
      </Panel>
    )
  }
  if (!ev) return <Panel><EmptyState title="Loading…" /></Panel>

  async function handleDeleteEvent() {
    if (!confirm(`Delete event "${ev!.name}"? Attached videos are kept, just detached.`)) return
    await api.deleteEvent(eventId)
    navigate('/events')
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => navigate('/events')} className="p-1.5 rounded-md hover:bg-white/5"><ArrowLeft size={18} /></button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold truncate">{ev.name}</h1>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--panel-2)] text-[var(--muted)] shrink-0">{ev.event_type}</span>
            </div>
            <p className="text-xs text-[var(--muted)] flex items-center gap-3 mt-0.5">
              {ev.location && <span className="flex items-center gap-1"><MapPin size={11} />{ev.location}</span>}
              <span>{ev.cameras.length} cameras · {ev.zones.length} zones · {ev.video_sources.length} sources</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PrivacyBadge />
          <button onClick={handleDeleteEvent} title="Delete event"
            className="p-1.5 rounded-md border border-[var(--border)] text-[var(--muted)] hover:text-red-400 hover:border-red-400/40">
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      <div className="flex gap-2">
        <Link to={`/events/${eventId}/timeline`}
          className={`px-3 py-1.5 rounded-md text-sm border flex items-center gap-1.5 ${
            ev.video_sources.length ? 'border-[var(--accent)]/50 text-[var(--accent)]' : 'border-[var(--border)] text-[var(--muted)] pointer-events-none opacity-50'}`}>
          <Clock size={14} /> Global Timeline
        </Link>
        <Link to={`/events/${eventId}/multicam`}
          className={`px-3 py-1.5 rounded-md text-sm border flex items-center gap-1.5 ${
            ev.video_sources.length ? 'border-[var(--accent)]/50 text-[var(--accent)]' : 'border-[var(--border)] text-[var(--muted)] pointer-events-none opacity-50'}`}>
          <Grid3x3 size={14} /> Multi-Camera View
        </Link>
        {ev.video_sources.length === 0 && (
          <span className="text-xs text-[var(--muted)] self-center">Attach a video source below to unlock the timeline and multi-camera views.</span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <DigitalTwinMap ev={ev} onChange={load} />
          <VideoSourcesPanel ev={ev} onChange={load} />
        </div>
        <div className="space-y-4">
          <DemographicCompositionForm ev={ev} onChange={load} />
          <ZoneForm eventId={eventId} onChange={load} />
          <CameraForm eventId={eventId} zones={ev.zones} onChange={load} />
        </div>
      </div>
    </div>
  )
}

// ============================================================ Phase 4: demographic composition
function DemographicCompositionForm({ ev, onChange }: { ev: EventDetailT; onChange: () => void }) {
  const [children, setChildren] = useState(ev.demo_children_pct ?? 0)
  const [adults, setAdults] = useState(ev.demo_adults_pct ?? 0)
  const [elderly, setElderly] = useState(ev.demo_elderly_pct ?? 0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const configured = ev.demo_children_pct != null

  async function submit() {
    setBusy(true); setErr(null)
    try {
      await api.updateEvent(ev.id, { demo_children_pct: children, demo_adults_pct: adults, demo_elderly_pct: elderly })
      onChange()
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Panel title="Demographic Composition">
      <p className="text-[11px] text-[var(--muted)] mb-2">
        Estimated attendee mix — from ticketing, registration, or your knowledge of the event. Not AI-detected: CROWDLENS has no per-person age/gender classifier. This apportions the real live headcount and feeds the vulnerability estimate.
      </p>
      <div className="grid grid-cols-3 gap-1.5">
        <NumField label="children %" value={children} set={setChildren} step={1} min={0} max={100} />
        <NumField label="adults %" value={adults} set={setAdults} step={1} min={0} max={100} />
        <NumField label="elderly %" value={elderly} set={setElderly} step={1} min={0} max={100} />
      </div>
      {err && <p className="text-xs text-red-400 mt-2">{err}</p>}
      <button disabled={busy} onClick={submit}
        className="w-full mt-2 px-3 py-1.5 rounded-md bg-[var(--panel-2)] border border-[var(--border)] text-sm disabled:opacity-60">
        {busy ? 'Saving…' : configured ? 'Update composition' : 'Set composition'}
      </button>
      {!configured && <p className="text-[10px] text-[var(--muted)] mt-1">Not configured — demographic estimate and vulnerability score will show "Not Available" until set.</p>}
    </Panel>
  )
}

// ============================================================ digital twin map
function DigitalTwinMap({ ev, onChange }: { ev: EventDetailT; onChange: () => void }) {
  const [selected, setSelected] = useState<{ kind: 'zone' | 'camera'; id: string } | null>(null)

  async function removeZone(id: string) {
    await api.deleteZone(id); setSelected(null); onChange()
  }
  async function removeCamera(id: string) {
    await api.deleteCamera(id); setSelected(null); onChange()
  }

  return (
    <Panel title="Site Map & Zone Heatmap" actions={
      <span className="text-[10px] text-[var(--muted)]">shaded by each zone's last-known risk level</span>
    }>
      <div className="relative w-full aspect-video rounded-md border border-[var(--border)] bg-[var(--panel-2)] overflow-hidden">
        {/* grid backdrop */}
        <svg className="absolute inset-0 w-full h-full opacity-20 pointer-events-none">
          {Array.from({ length: 9 }).map((_, i) => (
            <line key={'v' + i} x1={`${(i + 1) * 10}%`} y1="0" x2={`${(i + 1) * 10}%`} y2="100%" stroke="var(--muted)" strokeWidth={1} />
          ))}
          {Array.from({ length: 5 }).map((_, i) => (
            <line key={'h' + i} x1="0" y1={`${(i + 1) * 16.6}%`} x2="100%" y2={`${(i + 1) * 16.6}%`} stroke="var(--muted)" strokeWidth={1} />
          ))}
        </svg>

        {ev.zones.length === 0 && ev.cameras.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-xs text-[var(--muted)]">Add zones and cameras with the forms on the right — they'll appear here.</p>
          </div>
        )}

        {ev.zones.map((z) => {
          const heat = zoneHeat(z, ev)
          const heatColor = heat ? LEVEL_HEX[heat] : null
          return (
            <div key={z.id}
              onClick={() => setSelected({ kind: 'zone', id: z.id })}
              className="absolute border-2 rounded cursor-pointer flex items-start justify-start p-1"
              style={{
                left: `${z.x * 100}%`, top: `${z.y * 100}%`, width: `${z.w * 100}%`, height: `${z.h * 100}%`,
                borderColor: heatColor ?? ROLE_COLOR[z.role],
                backgroundColor: heatColor ? `${heatColor}33` : `${ROLE_COLOR[z.role]}18`,
                outline: selected?.kind === 'zone' && selected.id === z.id ? `2px solid ${heatColor ?? ROLE_COLOR[z.role]}` : undefined,
              }}>
              <span className="text-[9px] font-semibold px-1 py-0.5 rounded flex items-center gap-1"
                style={{ color: heatColor ?? ROLE_COLOR[z.role], backgroundColor: 'var(--panel)' }}>
                {z.name}{!heat && <span className="opacity-60">· no data</span>}
              </span>
            </div>
          )
        })}

        {ev.cameras.map((c) => (
          <div key={c.id}
            onClick={() => setSelected({ kind: 'camera', id: c.id })}
            className="absolute cursor-pointer group"
            style={{ left: `${c.x * 100}%`, top: `${c.y * 100}%`, transform: 'translate(-50%, -50%)' }}>
            <div className="relative flex items-center justify-center">
              <div className="w-3 h-3 rounded-full bg-[var(--accent)] ring-2 ring-[var(--panel)]"
                style={selected?.kind === 'camera' && selected.id === c.id ? { boxShadow: '0 0 0 3px var(--accent)' } : undefined} />
              <div className="absolute w-6 h-0.5 bg-[var(--accent)] origin-left"
                style={{ transform: `rotate(${c.orientation_deg}deg)`, left: '50%' }} />
            </div>
            <span className="absolute top-3 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] bg-[var(--panel)] px-1 rounded text-[var(--text)] opacity-0 group-hover:opacity-100 transition-opacity">
              {c.name} · {c.source_type}
            </span>
          </div>
        ))}
      </div>

      {selected && (
        <div className="mt-3 flex items-center justify-between text-xs bg-[var(--panel-2)] rounded-md px-3 py-2">
          {selected.kind === 'zone' ? (() => {
            const z = ev.zones.find((zz) => zz.id === selected.id)
            if (!z) return null
            return <span>Zone <b className="text-[var(--text)]">{z.name}</b> · role: {z.role}</span>
          })() : (() => {
            const c = ev.cameras.find((cc) => cc.id === selected.id)
            if (!c) return null
            return <span>Camera <b className="text-[var(--text)]">{c.name}</b> · {c.source_type} · {c.orientation_deg}° · {c.location_label || 'no location label'}</span>
          })()}
          <div className="flex items-center gap-2">
            <button onClick={() => selected.kind === 'zone' ? removeZone(selected.id) : removeCamera(selected.id)}
              className="text-red-400 hover:text-red-300 flex items-center gap-1"><Trash2 size={12} /> Remove</button>
            <button onClick={() => setSelected(null)} className="text-[var(--muted)]"><X size={12} /></button>
          </div>
        </div>
      )}

      <div className="flex gap-4 mt-3 text-[10px] text-[var(--muted)] flex-wrap">
        {ZONE_ROLES.map((r) => (
          <span key={r} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ backgroundColor: ROLE_COLOR[r] }} />{r}
          </span>
        ))}
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full inline-block bg-[var(--accent)]" />camera (line = viewing direction)</span>
      </div>
    </Panel>
  )
}

// ============================================================ zone form
function ZoneForm({ eventId, onChange }: { eventId: string; onChange: () => void }) {
  const [name, setName] = useState('')
  const [role, setRole] = useState<ZoneRole>('general')
  const [x, setX] = useState(0.1); const [y, setY] = useState(0.1)
  const [w, setW] = useState(0.2); const [h, setH] = useState(0.2)
  const [areaM2, setAreaM2] = useState(100)
  const [capacity, setCapacity] = useState(500)
  const [spatialContext, setSpatialContext] = useState<SpatialContext>('open')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    if (!name.trim()) { setErr('Zone name is required'); return }
    setBusy(true); setErr(null)
    try {
      await api.createZone(eventId, { name: name.trim(), role, x, y, w, h, area_m2: areaM2, capacity, spatial_context: spatialContext })
      setName(''); onChange()
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Panel title="Add Zone">
      <div className="space-y-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Zone name — e.g. Main Entrance"
          className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
        <select value={role} onChange={(e) => setRole(e.target.value as ZoneRole)}
          className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
          {ZONE_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <div className="grid grid-cols-4 gap-1.5">
          <NumField label="x" value={x} set={setX} />
          <NumField label="y" value={y} set={setY} />
          <NumField label="w" value={w} set={setW} />
          <NumField label="h" value={h} set={setH} />
        </div>
        <p className="text-[10px] text-[var(--muted)]">Position/size as a fraction (0–1) of the site map, left-to-right / top-to-bottom.</p>
        <div className="grid grid-cols-2 gap-1.5">
          <NumField label="area (m²)" value={areaM2} set={setAreaM2} step={1} min={1} max={100000} />
          <NumField label="capacity (people)" value={capacity} set={setCapacity} step={1} min={1} max={1000000} />
        </div>
        <p className="text-[10px] text-[var(--muted)]">Real-world ground area and safe capacity — feeds the zone's density and occupancy analytics.</p>
        <select value={spatialContext} onChange={(e) => setSpatialContext(e.target.value as SpatialContext)}
          className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
          {SPATIAL_CONTEXTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <p className="text-[10px] text-[var(--muted)]">Spatial crowd context — how this zone is actually laid out. Set by you, not guessed frame-by-frame.</p>
        {err && <p className="text-xs text-red-400">{err}</p>}
        <button disabled={busy} onClick={submit}
          className="w-full px-3 py-1.5 rounded-md bg-[var(--panel-2)] border border-[var(--border)] text-sm flex items-center justify-center gap-1.5 disabled:opacity-60">
          <Plus size={13} /> Add zone
        </button>
      </div>
    </Panel>
  )
}

// ============================================================ camera form
function CameraForm({ eventId, zones, onChange }: { eventId: string; zones: EventZone[]; onChange: () => void }) {
  const [name, setName] = useState('')
  const [sourceType, setSourceType] = useState<SourceType>('CCTV')
  const [locationLabel, setLocationLabel] = useState('')
  const [x, setX] = useState(0.5); const [y, setY] = useState(0.5)
  const [orientation, setOrientation] = useState(0)
  const [zoneId, setZoneId] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    if (!name.trim()) { setErr('Camera name is required'); return }
    setBusy(true); setErr(null)
    try {
      await api.createCamera(eventId, {
        name: name.trim(), source_type: sourceType, location_label: locationLabel.trim(),
        x, y, orientation_deg: orientation, zone_id: zoneId || null,
      })
      setName(''); setLocationLabel(''); onChange()
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Panel title="Add Camera">
      <div className="space-y-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Camera name — e.g. CAM-01 North Gate"
          className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
        <select value={sourceType} onChange={(e) => setSourceType(e.target.value as SourceType)}
          className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
          {SOURCE_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input value={locationLabel} onChange={(e) => setLocationLabel(e.target.value)} placeholder="Location label — e.g. North Gate"
          className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
        <select value={zoneId} onChange={(e) => setZoneId(e.target.value)}
          className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
          <option value="">No zone assigned</option>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
        </select>
        <div className="grid grid-cols-3 gap-1.5">
          <NumField label="x" value={x} set={setX} />
          <NumField label="y" value={y} set={setY} />
          <NumField label="°" value={orientation} set={setOrientation} step={5} min={0} max={360} />
        </div>
        <p className="text-[10px] text-[var(--muted)]">Position (0–1 fraction of the map) and compass orientation the camera faces (0–360°).</p>
        {err && <p className="text-xs text-red-400">{err}</p>}
        <button disabled={busy} onClick={submit}
          className="w-full px-3 py-1.5 rounded-md bg-[var(--panel-2)] border border-[var(--border)] text-sm flex items-center justify-center gap-1.5 disabled:opacity-60">
          <CameraIcon size={13} /> Add camera
        </button>
      </div>
    </Panel>
  )
}

function NumField({ label, value, set, step = 0.01, min = 0, max = 1 }: {
  label: string; value: number; set: (n: number) => void; step?: number; min?: number; max?: number
}) {
  return (
    <label className="block">
      <span className="block text-[10px] text-[var(--muted)] mb-0.5">{label}</span>
      <input type="number" value={value} step={step} min={min} max={max}
        onChange={(e) => set(parseFloat(e.target.value) || 0)}
        className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded px-1.5 py-1 text-xs" />
    </label>
  )
}

// ============================================================ video sources
function VideoSourcesPanel({ ev, onChange }: { ev: EventDetailT; onChange: () => void }) {
  const navigate = useNavigate()
  const [allVideos, setAllVideos] = useState<VideoRecord[]>([])
  const [mode, setMode] = useState<'attach' | 'upload' | null>(null)
  const [videoId, setVideoId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [category, setCategory] = useState<string>(VIDEO_CATEGORIES[0])
  const [cameraId, setCameraId] = useState('')
  const [zoneId, setZoneId] = useState('')
  const [sourceType, setSourceType] = useState<SourceType>('Uploaded Video')
  const [startLocal, setStartLocal] = useState('')
  const [inflowDirection, setInflowDirection] = useState<'left' | 'right'>('right')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const selectedZone = ev.zones.find((z) => z.id === zoneId)
  const isFlowZone = selectedZone && ['entrance', 'exit', 'bottleneck'].includes(selectedZone.role)

  useEffect(() => { if (mode === 'attach') api.listVideos().then(setAllVideos).catch(() => {}) }, [mode])

  const attachedIds = new Set(ev.video_sources.map((v) => v.id))
  const availableVideos = allVideos.filter((v) => !attachedIds.has(v.id))
  const captureStartTs = startLocal ? new Date(startLocal).getTime() / 1000 : null

  async function submitAttach() {
    if (!videoId) { setErr('Choose a video to attach'); return }
    setBusy(true); setErr(null)
    try {
      await api.attachVideo(ev.id, videoId, {
        camera_id: cameraId || null, zone_id: zoneId || null, source_type: sourceType,
        capture_start_ts: captureStartTs, inflow_direction: inflowDirection,
      })
      resetForm(); onChange()
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  async function submitUpload() {
    if (!file) { setErr('Choose a file to upload'); return }
    setBusy(true); setErr(null)
    try {
      await api.uploadEventVideo(ev.id, file, {
        camera_id: cameraId || null, zone_id: zoneId || null, source_type: sourceType,
        capture_start_ts: captureStartTs, inflow_direction: inflowDirection, category,
      })
      resetForm(); onChange()
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  function resetForm() {
    setMode(null); setVideoId(''); setFile(null); setCameraId(''); setZoneId('')
    setSourceType('Uploaded Video'); setStartLocal(''); setInflowDirection('right')
    if (fileRef.current) fileRef.current.value = ''
  }

  async function detach(id: string) {
    await api.detachVideo(ev.id, id); onChange()
  }

  return (
    <Panel title="Video Sources" actions={
      <div className="flex gap-2">
        <button onClick={() => setMode(mode === 'attach' ? null : 'attach')}
          className="text-xs text-[var(--accent)] flex items-center gap-1"><Link2 size={12} /> Attach existing</button>
        <button onClick={() => setMode(mode === 'upload' ? null : 'upload')}
          className="text-xs text-[var(--accent)] flex items-center gap-1"><Upload size={12} /> Upload new</button>
      </div>
    }>
      {mode && (
        <div className="mb-4 p-3 rounded-md bg-[var(--panel-2)] space-y-2">
          {mode === 'attach' ? (
            <select value={videoId} onChange={(e) => setVideoId(e.target.value)}
              className="w-full bg-[var(--panel)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
              <option value="">Choose an uploaded video…</option>
              {availableVideos.map((v) => <option key={v.id} value={v.id}>{v.filename}</option>)}
            </select>
          ) : (
            <>
              <input ref={fileRef} type="file" accept="video/mp4,video/x-msvideo,video/quicktime,.mkv,.webm"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="w-full text-xs text-[var(--muted)] file:mr-2 file:px-2.5 file:py-1.5 file:rounded-md file:border-0 file:bg-[var(--accent)] file:text-white file:text-xs" />
              <select value={category} onChange={(e) => setCategory(e.target.value)}
                className="w-full bg-[var(--panel)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
                {VIDEO_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </>
          )}
          <div className="grid grid-cols-2 gap-2">
            <select value={cameraId} onChange={(e) => setCameraId(e.target.value)}
              className="bg-[var(--panel)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
              <option value="">No camera</option>
              {ev.cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select value={zoneId} onChange={(e) => setZoneId(e.target.value)}
              className="bg-[var(--panel)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
              <option value="">No zone</option>
              {ev.zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select value={sourceType} onChange={(e) => setSourceType(e.target.value as SourceType)}
              className="bg-[var(--panel)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
              {SOURCE_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <input type="datetime-local" value={startLocal} onChange={(e) => setStartLocal(e.target.value)}
              className="bg-[var(--panel)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
          </div>
          <p className="text-[10px] text-[var(--muted)]">
            Recording start time — leave blank if unknown. Without it this source shows "Synchronization unavailable" on the global timeline; it is never guessed.
          </p>
          {isFlowZone && (
            <div>
              <select value={inflowDirection} onChange={(e) => setInflowDirection(e.target.value as 'left' | 'right')}
                className="w-full bg-[var(--panel)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
                <option value="right">Movement left → right counts as inflow</option>
                <option value="left">Movement right → left counts as inflow</option>
              </select>
              <p className="text-[10px] text-[var(--muted)] mt-1">
                "{selectedZone!.name}" is a {selectedZone!.role} zone — inflow/outflow will be counted from real tracked crossings of the frame's midline. This direction assumption is configurable, never silently guessed.
              </p>
            </div>
          )}
          {err && <p className="text-xs text-red-400">{err}</p>}
          <div className="flex gap-2">
            <button disabled={busy} onClick={mode === 'attach' ? submitAttach : submitUpload}
              className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium disabled:opacity-60">
              {busy ? 'Saving…' : mode === 'attach' ? 'Attach video' : 'Upload & attach'}
            </button>
            <button disabled={busy} onClick={resetForm} className="px-3 py-1.5 rounded-md border border-[var(--border)] text-sm">Cancel</button>
          </div>
        </div>
      )}

      {ev.video_sources.length === 0 ? (
        <EmptyState title="No video sources attached" hint="Attach an existing upload or upload a new file above." />
      ) : (
        <div className="space-y-2">
          {ev.video_sources.map((v) => (
            <div key={v.id} className="flex items-center gap-3 rounded-md border border-[var(--border)] p-2.5">
              <div className="w-20 aspect-video rounded overflow-hidden bg-black shrink-0">
                <VideoThumb src={v.thumbnail} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <button onClick={() => navigate(`/videos/${v.id}`)} className="text-sm font-medium truncate hover:text-[var(--accent)]">{v.filename}</button>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--panel-2)] text-[var(--muted)] shrink-0 flex items-center gap-1">
                    {v.source_type === 'CCTV' ? <Radio size={9} /> : <CameraIcon size={9} />}{v.source_type}
                  </span>
                  {v.last_level && <RiskBadge level={v.last_level} />}
                </div>
                <p className="text-[11px] text-[var(--muted)] truncate">
                  {v.camera_name ?? 'No camera'} · {v.zone_name ?? 'No zone'} · {formatDuration(v.duration_sec)}
                  {v.capture_start_ts ? ` · starts ${formatDate(v.capture_start_ts)}` : ' · no timestamp (unsynchronized)'}
                </p>
              </div>
              <button onClick={() => detach(v.id)} title="Detach from this event"
                className="p-1.5 rounded-md text-[var(--muted)] hover:text-red-400 shrink-0"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
