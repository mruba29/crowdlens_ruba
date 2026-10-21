import React, { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search, Upload, Loader2, Pencil, Check, X, Play, Trash2, Filter,
  CheckSquare, Square, Video, Eye, ArrowUpDown, Film, AlertCircle, Clock,
} from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, EmptyState, PrivacyBadge, RiskBadge, VideoThumb, formatDuration, formatDate } from '../components/ui'
import { VIDEO_CATEGORIES, LEVEL_RISK_LABEL } from '../lib/types'
import type { VideoRecord, RiskLevel } from '../lib/types'

const CATEGORY_FILTERS = ['All', ...VIDEO_CATEGORIES]

type SortOption = 'recently_uploaded' | 'recently_analyzed' | 'highest_risk' | 'not_analyzed'

interface UploadItem {
  id: string
  file: File
  status: 'pending' | 'uploading' | 'completed' | 'error'
  progress: number
  error?: string
}

export default function CrowdVideos() {
  const { videos, refreshVideos, status: liveStatus } = useApp()
  const navigate = useNavigate()

  // Filters & Sorting
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [sortBy, setSortBy] = useState<SortOption>('recently_uploaded')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')

  // Multi-select & Batch
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [batchStarting, setBatchStarting] = useState(false)

  // Edit filename/category
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editCategory, setEditCategory] = useState('')
  const [saving, setSaving] = useState(false)

  // Multi-upload Modal & Queue
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadCategory, setUploadCategory] = useState<string>(VIDEO_CATEGORIES[0])
  const [uploadQueue, setUploadQueue] = useState<UploadItem[]>([])
  const [uploadingAll, setUploadingAll] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Filter & Sort computation
  const filteredVideos = useMemo(() => {
    const q = search.trim().toLowerCase()
    const result = videos.filter((v) => {
      if (category !== 'All' && v.category !== category) return false
      if (!q) return true
      const level = v.last_level ? `${v.last_level} ${LEVEL_RISK_LABEL[v.last_level]}` : ''
      return (
        v.filename.toLowerCase().includes(q) ||
        v.category.toLowerCase().includes(q) ||
        v.id.toLowerCase().includes(q) ||
        level.toLowerCase().includes(q)
      )
    })

    // Sorting
    result.sort((a, b) => {
      if (sortBy === 'recently_uploaded') {
        return b.uploaded_at - a.uploaded_at
      }
      if (sortBy === 'recently_analyzed') {
        return (b.last_analyzed_at ?? 0) - (a.last_analyzed_at ?? 0)
      }
      if (sortBy === 'highest_risk') {
        return (b.last_score ?? 0) - (a.last_score ?? 0)
      }
      if (sortBy === 'not_analyzed') {
        const aAnalyzed = a.last_analyzed_at != null ? 1 : 0
        const bAnalyzed = b.last_analyzed_at != null ? 1 : 0
        return aAnalyzed - bAnalyzed
      }
      return 0
    })

    return result
  }, [videos, search, category, sortBy])

  // Select helpers
  function toggleSelect(id: string, e?: React.MouseEvent) {
    e?.stopPropagation()
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectAll() {
    if (selectedIds.size === filteredVideos.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredVideos.map((v) => v.id)))
    }
  }

  // Batch actions
  async function handleBatchStart() {
    if (selectedIds.size === 0) return
    setBatchStarting(true)
    try {
      await api.batchStartAnalysis(Array.from(selectedIds))
      await refreshVideos()
      setSelectedIds(new Set())
    } catch (e: any) {
      alert(`Batch start failed: ${e.message}`)
    } finally {
      setBatchStarting(false)
    }
  }

  async function handleBatchDelete() {
    if (selectedIds.size === 0) return
    if (!confirm(`Are you sure you want to delete ${selectedIds.size} videos from library?`)) return
    try {
      for (const id of Array.from(selectedIds)) {
        await api.deleteVideo(id).catch(() => {})
      }
      await refreshVideos()
      setSelectedIds(new Set())
    } catch (e: any) {
      alert(`Delete failed: ${e.message}`)
    }
  }

  // Edit file metadata
  function startEdit(v: VideoRecord, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingId(v.id)
    setEditName(v.filename)
    setEditCategory(v.category)
  }

  async function saveEdit(id: string) {
    if (!editName.trim()) return
    setSaving(true)
    try {
      await api.updateVideo(id, { filename: editName.trim(), category: editCategory })
      await refreshVideos()
      setEditingId(null)
    } finally {
      setSaving(false)
    }
  }

  // Multi-upload handling
  function handleFilesSelected(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploadError(null)

    const validExts = ['.mp4', '.mov', '.webm', '.avi', '.mkv']
    const newItems: UploadItem[] = []

    for (const f of Array.from(files)) {
      const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
      if (!validExts.includes(ext)) {
        setUploadError(`Unsupported format "${ext}" on "${f.name}". Supported: MP4, MOV, WebM, AVI, MKV.`)
        continue
      }
      if (f.size > 500 * 1024 * 1024) {
        setUploadError(`File "${f.name}" exceeds 500MB limit.`)
        continue
      }

      newItems.push({
        id: Math.random().toString(36).substring(2),
        file: f,
        status: 'pending',
        progress: 0,
      })
    }

    setUploadQueue((prev) => [...prev, ...newItems])
    if (inputRef.current) inputRef.current.value = ''
  }

  async function executeQueueUpload() {
    if (uploadQueue.length === 0) return
    setUploadingAll(true)
    setUploadError(null)

    for (let i = 0; i < uploadQueue.length; i++) {
      const item = uploadQueue[i]
      if (item.status === 'completed') continue

      setUploadQueue((prev) =>
        prev.map((it, idx) => (idx === i ? { ...it, status: 'uploading', progress: 40 } : it))
      )

      try {
        await api.uploadVideo(item.file, uploadCategory)
        setUploadQueue((prev) =>
          prev.map((it, idx) => (idx === i ? { ...it, status: 'completed', progress: 100 } : it))
        )
      } catch (err: any) {
        setUploadQueue((prev) =>
          prev.map((it, idx) =>
            idx === i ? { ...it, status: 'error', error: err.message || 'Upload failed' } : it
          )
        )
      }
    }

    await refreshVideos()
    setUploadingAll(false)
  }

  function removeQueueItem(id: string) {
    setUploadQueue((prev) => prev.filter((it) => it.id !== id))
  }

  return (
    <div className="space-y-5">
      {/* Top Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[var(--text)]">Crowd Video Library</h1>
          <p className="text-xs text-[var(--muted)]">
            YouTube-style video repository for multi-feed crowd safety surveillance & analytics
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowUploadModal(true)}
            className="px-3.5 py-2 rounded-lg bg-[var(--accent)] hover:bg-emerald-600 text-white text-xs font-bold transition-all flex items-center gap-2 shadow-sm"
          >
            <Upload size={14} /> Upload Videos
          </button>
          <PrivacyBadge />
        </div>
      </div>

      {/* Top Bar: Search, Category Chips, Sort Controls */}
      <Panel className="p-3.5 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search Field */}
          <div className="relative flex-1 min-w-[240px]">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by title, category, camera ID, or risk level..."
              className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-lg pl-9 pr-8 py-2 text-xs text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-white"
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Sort Dropdown */}
          <div className="flex items-center gap-1.5 shrink-0 text-xs">
            <ArrowUpDown size={14} className="text-[var(--muted)]" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="bg-[var(--panel-2)] border border-[var(--border)] rounded-lg px-2.5 py-2 text-xs text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="recently_uploaded">Recently Uploaded</option>
              <option value="recently_analyzed">Recently Analyzed</option>
              <option value="highest_risk">Highest Risk</option>
              <option value="not_analyzed">Not Yet Analyzed</option>
            </select>
          </div>
        </div>

        {/* YouTube-style Category Filter Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
          {CATEGORY_FILTERS.map((c) => {
            const isSelected = category === c
            return (
              <button
                key={c}
                onClick={() => setCategory(c)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors border ${
                  isSelected
                    ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                    : 'bg-[var(--panel-2)] border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)] hover:border-white/20'
                }`}
              >
                {c}
              </button>
            )
          })}
        </div>
      </Panel>

      {/* Batch Selection Action Bar */}
      {selectedIds.size > 0 && (
        <div className="bg-[var(--panel)] border border-[var(--accent)]/50 rounded-xl p-3 px-4 flex items-center justify-between flex-wrap gap-3 shadow-lg animate-in fade-in duration-200">
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-[var(--accent)]">
              {selectedIds.size} video{selectedIds.size > 1 ? 's' : ''} selected
            </span>
            <button onClick={selectAll} className="text-xs text-[var(--muted)] hover:text-white underline">
              {selectedIds.size === filteredVideos.length ? 'Deselect All' : 'Select All'}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={batchStarting}
              onClick={handleBatchStart}
              className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 transition-colors"
            >
              {batchStarting ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
              Start Batch Analysis
            </button>
            <button
              onClick={handleBatchDelete}
              className="px-3 py-1.5 rounded-lg bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-500/30 text-xs font-semibold flex items-center gap-1 transition-colors"
            >
              <Trash2 size={13} /> Delete Selected
            </button>
          </div>
        </div>
      )}

      {/* Video Cards Grid (YouTube Style) */}
      {videos.length === 0 ? (
        <Panel>
          <EmptyState
            title="Your video library is empty"
            hint="Upload multiple crowd videos to analyze density, bottlenecks, and real-time safety risks."
          />
          <div className="flex justify-center mt-3">
            <button
              onClick={() => setShowUploadModal(true)}
              className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-bold flex items-center gap-2 shadow"
            >
              <Upload size={14} /> Upload First Video
            </button>
          </div>
        </Panel>
      ) : filteredVideos.length === 0 ? (
        <Panel>
          <EmptyState title="No videos match your filters" hint="Try adjusting your keyword or category filter." />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredVideos.map((v, i) => {
            const isEditing = editingId === v.id
            const isSelected = selectedIds.has(v.id)
            const isProcessing = liveStatus?.video_id === v.id && liveStatus?.status === 'processing'
            const isQueued = v.status === 'queued'

            return (
              <div
                key={v.id}
                onClick={() => !isEditing && navigate(`/videos/${v.id}`)}
                className={`group rounded-xl border bg-[var(--panel)] overflow-hidden transition-all duration-200 cursor-pointer ${
                  isSelected
                    ? 'border-[var(--accent)] ring-1 ring-[var(--accent)] shadow-md'
                    : 'border-[var(--border)] hover:border-[var(--accent)]/50 hover:shadow-md'
                }`}
              >
                {/* 16:9 Thumbnail Card */}
                <div className="aspect-video bg-black relative overflow-hidden">
                  <VideoThumb src={v.thumbnail} className="group-hover:scale-105 transition-transform duration-300" />

                  {/* Multi-Select Checkbox (Top Left Overlay) */}
                  <div
                    onClick={(e) => toggleSelect(v.id, e)}
                    className="absolute top-2 left-2 z-10 p-1 rounded-md bg-black/60 hover:bg-black/90 transition-colors"
                  >
                    {isSelected ? (
                      <CheckSquare size={16} className="text-[var(--accent)]" />
                    ) : (
                      <Square size={16} className="text-white/70 hover:text-white" />
                    )}
                  </div>

                  {/* Status Badge (Top Right) */}
                  <div className="absolute top-2 right-2 flex items-center gap-1.5">
                    {v.last_level && <RiskBadge level={v.last_level} />}
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded shadow ${
                        isProcessing
                          ? 'bg-red-600 text-white animate-pulse'
                          : isQueued
                          ? 'bg-amber-500 text-black font-extrabold'
                          : v.status === 'completed'
                          ? 'bg-emerald-600/90 text-white'
                          : 'bg-black/70 text-[var(--muted)]'
                      }`}
                    >
                      {isProcessing ? '● PROCESSING' : isQueued ? 'QUEUED' : v.status.toUpperCase()}
                    </span>
                  </div>

                  {/* Duration Badge (Bottom Right) */}
                  <span className="absolute bottom-2 right-2 text-[10px] font-bold px-1.5 py-0.5 rounded bg-black/80 text-white font-mono shadow">
                    {formatDuration(v.duration_sec)}
                  </span>
                </div>

                {/* Metadata Area (YouTube Style) */}
                <div className="p-3.5 space-y-2">
                  {isEditing ? (
                    <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEdit(v.id)
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2 py-1 text-xs"
                      />
                      <select
                        value={editCategory}
                        onChange={(e) => setEditCategory(e.target.value)}
                        className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2 py-1 text-xs"
                      >
                        {VIDEO_CATEGORIES.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                      <div className="flex items-center gap-2">
                        <button
                          disabled={saving}
                          onClick={() => saveEdit(v.id)}
                          className="flex-1 px-2 py-1 rounded bg-[var(--accent)] text-white text-xs font-bold"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="px-2 py-1 rounded border border-[var(--border)] text-xs"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-start justify-between gap-1.5">
                        <h3 className="text-xs font-bold text-[var(--text)] line-clamp-1 group-hover:text-[var(--accent)] transition-colors">
                          {v.filename}
                        </h3>
                        <button
                          onClick={(e) => startEdit(v, e)}
                          title="Rename or change category"
                          className="p-1 rounded text-[var(--muted)] hover:text-white hover:bg-white/10 shrink-0"
                        >
                          <Pencil size={11} />
                        </button>
                      </div>

                      <div className="flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
                        <span className="px-1.5 py-0.2 rounded bg-[var(--panel-2)] border border-[var(--border)] text-[10px] font-semibold text-[var(--text)]">
                          {v.category}
                        </span>
                        <span>·</span>
                        <span>{formatDate(v.uploaded_at)}</span>
                      </div>

                      {/* Metrics Chip */}
                      <div className="flex items-center justify-between text-xs text-[var(--muted)] pt-2 border-t border-[var(--border)]">
                        <span>
                          {v.last_people != null ? (
                            <span className="font-semibold text-[var(--text)]">{v.last_people} people</span>
                          ) : (
                            'Not analyzed'
                          )}
                        </span>
                        <span>
                          {v.last_density != null && (
                            <span className="font-semibold text-[var(--text)]">{v.last_density.toFixed(1)}/m²</span>
                          )}
                        </span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Multi-Video Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--panel)] border border-[var(--border)] rounded-2xl max-w-xl w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Upload size={18} className="text-[var(--accent)]" />
                <h3 className="text-sm font-bold text-[var(--text)]">Batch Crowd Video Uploader</h3>
              </div>
              <button
                disabled={uploadingAll}
                onClick={() => {
                  setShowUploadModal(false)
                  setUploadQueue([])
                }}
                className="text-[var(--muted)] hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            {/* Drop / Select Area */}
            <div
              onClick={() => inputRef.current?.click()}
              className="border-2 border-dashed border-[var(--border)] hover:border-[var(--accent)]/60 rounded-xl p-6 text-center cursor-pointer transition-colors bg-[var(--panel-2)]/40"
            >
              <input
                ref={inputRef}
                type="file"
                multiple
                hidden
                accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,.mkv"
                onChange={(e) => handleFilesSelected(e.target.files)}
              />
              <Film size={32} className="mx-auto text-[var(--muted)] mb-2" />
              <p className="text-xs font-bold text-[var(--text)]">
                Click to browse or drag and drop multiple crowd footage videos
              </p>
              <p className="text-[11px] text-[var(--muted)] mt-1">
                Supported formats: MP4, MOV, WebM, AVI, MKV (Up to 500MB per file)
              </p>
            </div>

            {/* Category selection for batch */}
            <div className="flex items-center justify-between text-xs">
              <span className="text-[var(--muted)] font-medium">Default Event Category:</span>
              <select
                value={uploadCategory}
                onChange={(e) => setUploadCategory(e.target.value)}
                className="bg-[var(--panel-2)] border border-[var(--border)] rounded-lg px-2.5 py-1 text-xs text-[var(--text)]"
              >
                {VIDEO_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            {uploadError && (
              <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400 flex items-center gap-2">
                <AlertCircle size={14} className="shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            {/* Queue List */}
            {uploadQueue.length > 0 && (
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {uploadQueue.map((it) => (
                  <div
                    key={it.id}
                    className="p-2 rounded-lg bg-[var(--panel-2)] border border-[var(--border)] flex items-center justify-between text-xs gap-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-[var(--text)]">{it.file.name}</p>
                      <p className="text-[10px] text-[var(--muted)]">
                        {(it.file.size / (1024 * 1024)).toFixed(1)} MB · {it.status.toUpperCase()}
                      </p>
                      {it.status === 'uploading' && (
                        <div className="h-1 bg-black/40 rounded-full mt-1.5 overflow-hidden">
                          <div className="h-full bg-[var(--accent)] animate-pulse w-3/4 rounded-full" />
                        </div>
                      )}
                    </div>
                    {it.status === 'completed' ? (
                      <span className="text-emerald-400 font-bold flex items-center gap-1 text-[11px]">
                        <Check size={14} /> Ready
                      </span>
                    ) : it.status === 'error' ? (
                      <span className="text-red-400 text-[10px]">{it.error}</span>
                    ) : (
                      <button
                        disabled={uploadingAll}
                        onClick={() => removeQueueItem(it.id)}
                        className="text-[var(--muted)] hover:text-red-400 p-1"
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
              <span className="text-xs text-[var(--muted)]">
                {uploadQueue.length} file{uploadQueue.length !== 1 ? 's' : ''} in queue
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={uploadingAll}
                  onClick={() => {
                    setShowUploadModal(false)
                    setUploadQueue([])
                  }}
                  className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs font-semibold"
                >
                  Close
                </button>
                <button
                  type="button"
                  disabled={uploadingAll || uploadQueue.length === 0}
                  onClick={executeQueueUpload}
                  className="px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-emerald-600 text-white text-xs font-bold flex items-center gap-1.5"
                >
                  {uploadingAll ? (
                    <>
                      <Loader2 size={13} className="animate-spin" /> Uploading Queue…
                    </>
                  ) : (
                    <>Upload {uploadQueue.length > 0 ? `(${uploadQueue.length})` : ''}</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
