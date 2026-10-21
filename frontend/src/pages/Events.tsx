import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, MapPin, Camera as CameraIcon, Film, CalendarClock } from 'lucide-react'
import { api } from '../lib/api'
import { Panel, EmptyState, PrivacyBadge, formatDate } from '../components/ui'
import { VIDEO_CATEGORIES } from '../lib/types'
import type { CrowdEvent } from '../lib/types'

export default function Events() {
  const navigate = useNavigate()
  const [events, setEvents] = useState<CrowdEvent[]>([])
  const [counts, setCounts] = useState<Record<string, { cameras: number; videos: number }>>({})
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [eventType, setEventType] = useState<string>(VIDEO_CATEGORIES[0])
  const [location, setLocation] = useState('')
  const [crowdContext, setCrowdContext] = useState('')

  async function load() {
    try {
      const list = await api.listEvents()
      setEvents(list)
      const entries = await Promise.all(list.map(async (e) => {
        const d = await api.getEvent(e.id).catch(() => null)
        return [e.id, { cameras: d?.cameras.length ?? 0, videos: d?.video_sources.length ?? 0 }] as const
      }))
      setCounts(Object.fromEntries(entries))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  async function handleCreate() {
    if (!name.trim()) { setErr('Event name is required'); return }
    setBusy(true); setErr(null)
    try {
      const ev = await api.createEvent({
        name: name.trim(), event_type: eventType, location: location.trim(),
        crowd_context: crowdContext.trim(),
      })
      setShowForm(false); setName(''); setLocation(''); setCrowdContext('')
      navigate(`/events/${ev.id}`)
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <CalendarClock size={26} className="text-[var(--accent)]" />
          <div>
            <h1 className="text-xl font-bold leading-tight">Events</h1>
            <p className="text-sm text-[var(--muted)] leading-tight">
              Multi-source video, camera and zone configuration — the foundation layer for crowd analytics
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <PrivacyBadge />
          <button onClick={() => setShowForm((s) => !s)}
            className="px-3 py-2 rounded-md bg-[var(--accent)] text-white text-sm font-medium flex items-center gap-1.5">
            <Plus size={14} /> New Event
          </button>
        </div>
      </div>

      {showForm && (
        <Panel title="Create Event">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Event name">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. City Temple Festival — North Gate"
                className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
            </Field>
            <Field label="Event type">
              <select value={eventType} onChange={(e) => setEventType(e.target.value)}
                className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm">
                {VIDEO_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Location">
              <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Central Grounds, Sector 4"
                className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
            </Field>
            <Field label="Crowd context (optional)">
              <input value={crowdContext} onChange={(e) => setCrowdContext(e.target.value)} placeholder="e.g. dense evening crowd, multiple entry points"
                className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm" />
            </Field>
          </div>
          {err && <p className="text-sm text-red-400 mt-2">{err}</p>}
          <div className="flex gap-2 mt-3">
            <button disabled={busy} onClick={handleCreate}
              className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium disabled:opacity-60">
              {busy ? 'Creating…' : 'Create event'}
            </button>
            <button disabled={busy} onClick={() => setShowForm(false)}
              className="px-3 py-1.5 rounded-md border border-[var(--border)] text-sm">Cancel</button>
          </div>
        </Panel>
      )}

      {loading ? null : events.length === 0 ? (
        <Panel>
          <EmptyState title="No events yet"
            hint="Create an event to group multiple camera/video sources together with shared zones and a common timeline." />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {events.map((ev) => (
            <button key={ev.id} onClick={() => navigate(`/events/${ev.id}`)}
              className="text-left panel p-4 hover:border-[var(--accent)]/50 transition-colors border border-transparent">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold truncate">{ev.name}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--panel-2)] text-[var(--muted)] shrink-0">{ev.event_type}</span>
              </div>
              {ev.location && (
                <p className="text-xs text-[var(--muted)] mt-1 flex items-center gap-1"><MapPin size={11} />{ev.location}</p>
              )}
              <div className="flex items-center gap-4 mt-3 text-xs text-[var(--muted)]">
                <span className="flex items-center gap-1"><CameraIcon size={12} />{counts[ev.id]?.cameras ?? 0} cameras</span>
                <span className="flex items-center gap-1"><Film size={12} />{counts[ev.id]?.videos ?? 0} sources</span>
              </div>
              <p className="text-[11px] text-[var(--muted)] mt-2">Created {formatDate(ev.created_at)}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1">{label}</span>
      {children}
    </label>
  )
}
