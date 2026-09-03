import React, { useRef, useState } from 'react'
import { Upload, Play, Square } from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, RiskGauge, RiskBadge, EmptyState, PrivacyBadge } from '../components/ui'

export default function LiveAnalysis() {
  const { latest, status, zones, health } = useApp()
  const [file, setFile] = useState<File | null>(null)
  const [videoId, setVideoId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const processing = status?.status === 'processing'
  const detectorOk = health?.detector?.available

  async function handleUpload() {
    if (!file) return
    setErr(null); setBusy(true)
    try {
      const r = await api.uploadVideo(file)
      setVideoId(r.video_id)
      return r.video_id
    } catch (e: any) {
      setErr(`Upload failed: ${e.message}`)
    } finally { setBusy(false) }
  }

  async function handleStart() {
    // upload automatically if the chosen file hasn't been uploaded yet
    let id = videoId
    if (!id) {
      id = (await handleUpload()) ?? null
      if (!id) return
    }
    setErr(null); setBusy(true)
    try {
      await api.startAnalysis(id)
    } catch (e: any) {
      setErr(e.message)
    } finally { setBusy(false) }
  }

  async function handleStop() {
    setBusy(true)
    try { await api.stopAnalysis() } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Live Analysis</h1>
          <p className="text-sm text-[var(--muted)]">Upload a crowd video and run real person detection</p>
        </div>
        <PrivacyBadge />
      </div>

      {!detectorOk && (
        <Panel className="border-yellow-500/40">
          <p className="text-sm text-yellow-400">
            Person detector unavailable on the server. Analysis is disabled until a detector
            (YOLO via <code>ultralytics</code>, or OpenCV HOG) is installed.
          </p>
        </Panel>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* video + controls */}
        <div className="lg:col-span-2 space-y-4">
          <Panel title="Crowd Video">
            <div className="aspect-video w-full rounded-md bg-black flex items-center justify-center overflow-hidden">
              {latest?.annotated_frame ? (
                <img src={latest.annotated_frame} alt="analyzed frame with detection boxes"
                  className="w-full h-full object-contain" />
              ) : (
                <span className="text-sm text-[var(--muted)]">
                  {processing ? 'Waiting for first analyzed frame…' : 'No video playing'}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 mt-3">
              <input ref={inputRef} type="file" accept="video/mp4,video/x-msvideo,video/quicktime,.mkv,.webm"
                className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setVideoId(null) }} />
              <button onClick={() => inputRef.current?.click()}
                className="px-3 py-1.5 rounded-md bg-[var(--panel-2)] border border-[var(--border)] text-sm flex items-center gap-1.5">
                <Upload size={14} /> Choose video
              </button>
              <button disabled={!file || busy || processing || !detectorOk} onClick={handleStart}
                className="px-3 py-1.5 rounded-md bg-emerald-600 text-white text-sm flex items-center gap-1.5 disabled:bg-emerald-900">
                <Play size={14} /> {busy ? 'Starting…' : 'Start Analysis'}
              </button>
              <button disabled={!processing || busy} onClick={handleStop}
                className="px-3 py-1.5 rounded-md bg-red-600 text-white text-sm flex items-center gap-1.5">
                <Square size={14} /> Stop
              </button>
              {file && <span className="text-xs text-[var(--muted)]">{file.name}{videoId ? ' · uploaded' : ''}</span>}
              {!file && <span className="text-xs text-[var(--muted)]">Choose a video, then Start Analysis</span>}
            </div>
            {err && <p className="text-sm text-red-400 mt-2">{err}</p>}
            {status && (
              <p className="text-xs text-[var(--muted)] mt-2">
                Status: <span className="text-[var(--text)]">{status.status}</span>
                {status.detector_backend && <> · detector {status.detector_backend}</>}
                {status.frame_count != null && <> · frame {status.frames_processed}/{status.frame_count}</>}
              </p>
            )}
          </Panel>

          <Panel title="Legend">
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-[var(--muted)]">
              <span><span className="inline-block w-3 h-3 rounded-sm border-2 border-emerald-400 align-middle mr-1" />Detection box (per person)</span>
              <span>People count = number of boxes this frame</span>
              <span>Density = people ÷ estimated zone area (m²)</span>
              <span>Risk = weighted density + movement + build-up + compression</span>
            </div>
          </Panel>
        </div>

        {/* right: risk panel */}
        <div className="space-y-4">
          <Panel title="Current Risk" className="flex flex-col items-center">
            {latest ? (
              <>
                <RiskGauge score={latest.score} level={latest.level} label={latest.label} size={180} />
                <dl className="w-full mt-4 text-sm space-y-1.5">
                  <Row k="People detected" v={latest.people_count} />
                  <Row k="Density" v={`${latest.density_ppm2.toFixed(1)} /m²`} />
                  <Row k="Movement" v={latest.mean_motion.toFixed(2)} />
                  <Row k="Turbulence" v={latest.turbulence.toFixed(1)} />
                  <Row k="Risk score" v={<RiskBadge level={latest.level} />} />
                </dl>
              </>
            ) : (
              <EmptyState title="No analysis running" hint="Upload a video and press Start Analysis." />
            )}
          </Panel>

          {zones.length > 0 && (
            <Panel title="Zones">
              <div className="space-y-1.5 text-sm">
                {zones.map((z) => (
                  <div key={z.name} className="flex items-center justify-between">
                    <span className="text-[var(--muted)]">{z.name}</span>
                    <span className="flex items-center gap-2">
                      <span className="tabular-nums">{z.people}p</span>
                      <RiskBadge level={z.level} />
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between">
      <dt className="text-[var(--muted)]">{k}</dt>
      <dd className="tabular-nums">{v}</dd>
    </div>
  )
}
