import React, { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Panel, PrivacyBadge } from '../components/ui'
import type { Settings as S } from '../lib/types'

export default function Settings() {
  const [s, setS] = useState<S | null>(null)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.getSettings().then(setS).catch((e) => setErr(e.message)) }, [])

  async function save() {
    if (!s) return
    setErr(null)
    try {
      const next = await api.updateSettings({
        detection_confidence: s.detection_confidence,
        analysis_sample_every_n: s.analysis_sample_every_n,
        zone_area_m2: s.zone_area_m2,
        critical_density_ppm2: s.critical_density_ppm2,
        risk_thresholds: s.risk_thresholds,
      })
      setS(next); setSaved(true); setTimeout(() => setSaved(false), 1500)
    } catch (e: any) { setErr(e.message) }
  }

  if (!s) return <Panel>{err ? <p className="text-red-400 text-sm">{err}</p> : 'Loading…'}</Panel>

  return (
    <div className="space-y-5 max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Settings</h1>
        <PrivacyBadge />
      </div>

      <Panel title="Privacy">
        <p className="text-sm text-[var(--muted)]">
          Privacy Mode is <span className="text-emerald-400 font-medium">always ON</span> and cannot be disabled.
          CROWDLENS performs no facial recognition, stores no faces, names, or personal identifiers,
          and uses only temporary anonymous tracking.
        </p>
      </Panel>

      <Panel title="Detection">
        <Field label="Detection confidence" hint="0.05–0.95. Higher = fewer, more certain detections.">
          <input type="number" step="0.05" min="0.05" max="0.95" value={s.detection_confidence}
            onChange={(e) => setS({ ...s, detection_confidence: +e.target.value })} className={inp} />
        </Field>
        <Field label="Analysis frame step" hint="Process every Nth frame. Higher = faster, coarser.">
          <input type="number" step="1" min="1" max="15" value={s.analysis_sample_every_n}
            onChange={(e) => setS({ ...s, analysis_sample_every_n: +e.target.value })} className={inp} />
        </Field>
      </Panel>

      <Panel title="Crowd / Risk">
        <Field label="Estimated zone area (m²)" hint="Visible ground area of the camera view, used for density.">
          <input type="number" step="5" min="5" value={s.zone_area_m2}
            onChange={(e) => setS({ ...s, zone_area_m2: +e.target.value })} className={inp} />
        </Field>
        <Field label="Critical density (people/m²)" hint="Density that maps to maximum density-risk.">
          <input type="number" step="0.5" min="0.5" value={s.critical_density_ppm2}
            onChange={(e) => setS({ ...s, critical_density_ppm2: +e.target.value })} className={inp} />
        </Field>
        <div className="grid grid-cols-4 gap-2 mt-2">
          {(['YELLOW', 'ORANGE', 'RED', 'BLACK'] as const).map((k) => (
            <Field key={k} label={k}>
              <input type="number" min="1" max="100" value={s.risk_thresholds[k]}
                onChange={(e) => setS({ ...s, risk_thresholds: { ...s.risk_thresholds, [k]: +e.target.value } })}
                className={inp} />
            </Field>
          ))}
        </div>
        <p className="text-[11px] text-[var(--muted)] mt-1">
          Threshold changes are stored but the scoring bands (0–30 / 31–55 / 56–75 / 76–90 / 91–100) are fixed in this version.
        </p>
      </Panel>

      <div className="flex items-center gap-3">
        <button onClick={save} className="px-4 py-2 rounded-md bg-[var(--accent)] text-white text-sm font-medium">
          Save settings
        </button>
        {saved && <span className="text-emerald-400 text-sm">Saved</span>}
        {err && <span className="text-red-400 text-sm">{err}</span>}
      </div>
      <p className="text-xs text-[var(--muted)]">Settings apply to the next analysis you start.</p>
    </div>
  )
}

const inp = 'w-full bg-[var(--panel-2)] border border-[var(--border)] rounded px-2 py-1.5 text-sm'

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block mb-3">
      <span className="text-xs text-[var(--muted)] block mb-1">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-[var(--muted)] block mt-0.5">{hint}</span>}
    </label>
  )
}
