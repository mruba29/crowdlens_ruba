import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search, Upload, Loader2, Pencil, Check, X, Play, Trash2, Filter,
  CheckSquare, Square, Video, Eye, ArrowUpDown, Film, AlertCircle, Clock,
  ExternalLink, Download, BookOpen, Sparkles, ShieldCheck, Layers, ChevronRight,
  Info, CheckCircle2,
} from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, EmptyState, PrivacyBadge, RiskBadge, VideoThumb, formatDuration, formatDate } from '../components/ui'
import { VIDEO_CATEGORIES, LEVEL_RISK_LABEL } from '../lib/types'
import type { VideoRecord, RiskLevel, SampleVideo } from '../lib/types'

const CATEGORY_FILTERS = ['All', ...VIDEO_CATEGORIES]

const SCENARIO_FILTERS = [
  'All Scenarios',
  'Normal Crowd',
  'High Density',
  'Bottleneck / Accumulation',
  'Reverse Flow',
  'Possible Compression',
  'Turbulent Motion',
]

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

  // Tabs: 'uploaded' | 'samples'
  const [activeTab, setActiveTab] = useState<'uploaded' | 'samples'>('uploaded')

  // Uploaded Videos Filters & Sorting
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [sortBy, setSortBy] = useState<SortOption>('recently_uploaded')

  // Multi-select & Batch Actions
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

  // Sample Videos Library State
  const [samples, setSamples] = useState<SampleVideo[]>([])
  const [loadingSamples, setLoadingSamples] = useState(false)
  const [sampleCategory, setSampleCategory] = useState('All')
  const [sampleScenario, setSampleScenario] = useState('All Scenarios')
  const [sampleSearch, setSampleSearch] = useState('')
  const [importingId, setImportingId] = useState<string | null>(null)
  const [importNotice, setImportNotice] = useState<string | null>(null)

  // Fetch sample videos catalogue
  useEffect(() => {
    let alive = true
    setLoadingSamples(true)
    api.listSamples()
      .then((s) => alive && setSamples(s))
      .catch(() => {})
      .finally(() => alive && setLoadingSamples(false))
    return () => { alive = false }
  }, [videos])

  // Filter & Sort computation for Uploaded Videos
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

  // Filter computation for Sample Video Library
  const filteredSamples = useMemo(() => {
    const q = sampleSearch.trim().toLowerCase()
    return samples.filter((s) => {
      if (sampleCategory !== 'All' && s.category !== sampleCategory) return false
      if (sampleScenario !== 'All Scenarios' && !s.scenario_type.toLowerCase().includes(sampleScenario.toLowerCase())) return false
      if (!q) return true
      return (
        s.title.toLowerCase().includes(q) ||
        s.category.toLowerCase().includes(q) ||
        s.scenario_type.toLowerCase().includes(q) ||
        s.source_name.toLowerCase().includes(q) ||
        s.license.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
      )
    })
  }, [samples, sampleCategory, sampleScenario, sampleSearch])

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

  // Import Sample Video
  async function handleImportSample(s: SampleVideo) {
    setImportingId(s.id)
    setImportNotice(null)
    try {
      const res = await api.importSample(s.id)
      await refreshVideos()
      setImportNotice(res.message || `Sample "${s.title}" ready in library!`)
      const updated = await api.listSamples().catch(() => null)
      if (updated) setSamples(updated)
    } catch (err: any) {
      alert(`Import notice: ${err.message || 'Could not import sample.'}`)
    } finally {
      setImportingId(null)
    }
  }

  return (
    <div className="space-y-5">
      {/* Top Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[var(--text)]">Crowd Video Hub</h1>
          <p className="text-xs text-[var(--muted)]">
            Multi-feed crowd safety repository, research dataset benchmarks, and AI video analytics
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

      {/* Navigation Tabs: Uploaded Videos vs Sample Video Library */}
      <div className="flex items-center gap-2 border-b border-[var(--border)] pb-2">
        <button
          onClick={() => setActiveTab('uploaded')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-colors ${
            activeTab === 'uploaded'
              ? 'bg-[var(--accent)] text-white shadow-sm'
              : 'text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--panel-2)]'
          }`}
        >
          <Film size={14} />
          <span>Uploaded Videos</span>
          <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-semibold ${
            activeTab === 'uploaded' ? 'bg-black/30 text-white' : 'bg-[var(--panel-2)] text-[var(--muted)]'
          }`}>
            {videos.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('samples')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-colors ${
            activeTab === 'samples'
              ? 'bg-[var(--accent)] text-white shadow-sm'
              : 'text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--panel-2)]'
          }`}
        >
          <BookOpen size={14} />
          <span>Sample Video Library</span>
          <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-semibold ${
            activeTab === 'samples' ? 'bg-black/30 text-white' : 'bg-emerald-500/20 text-emerald-300'
          }`}>
            7 Categories
          </span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: UPLOADED VIDEOS VIEW                                               */}
      {/* ========================================================================= */}
      {activeTab === 'uploaded' && (
        <div className="space-y-4">
          {/* Top Bar: Search, Category Chips, Sort Controls */}
          <Panel className="p-3.5 space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {/* Search Field */}
              <div className="relative flex-1 min-w-[240px]">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by title, category, video ID, or risk level..."
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

            {/* Category Filter Chips */}
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
                  className="px-3.5 py-1.5 rounded-lg bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-500/30 text-xs font-semibold flex items-center gap-1 transition-colors"
                >
                  <Trash2 size={13} /> Delete Selected
                </button>
              </div>
            </div>
          )}

          {/* Video Cards Grid */}
          {videos.length === 0 ? (
            <Panel className="p-8 text-center space-y-4">
              <EmptyState
                title="Your video library is empty"
                hint="Upload crowd videos or choose from the built-in Sample Video Library to test real-time AI crowd analytics."
              />
              <div className="flex justify-center items-center gap-3 pt-2">
                <button
                  onClick={() => setShowUploadModal(true)}
                  className="px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-emerald-600 text-white text-xs font-bold flex items-center gap-2 shadow"
                >
                  <Upload size={14} /> Upload First Video
                </button>
                <button
                  onClick={() => setActiveTab('samples')}
                  className="px-4 py-2 rounded-lg bg-[var(--panel-2)] border border-[var(--border)] hover:border-emerald-500/50 text-[var(--text)] text-xs font-semibold flex items-center gap-2"
                >
                  <BookOpen size={14} /> Browse Sample Videos
                </button>
              </div>
            </Panel>
          ) : filteredVideos.length === 0 ? (
            <Panel className="p-8 text-center">
              <EmptyState title="No videos match your filters" hint="Try adjusting your keyword or category filter." />
            </Panel>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredVideos.map((v) => {
                const isEditing = editingId === v.id
                const isSelected = selectedIds.has(v.id)
                const isProcessing = liveStatus?.video_id === v.id && liveStatus?.status === 'processing'
                const isQueued = v.status === 'queued'

                return (
                  <div
                    key={v.id}
                    onClick={() => navigate(`/videos/${v.id}`)}
                    className={`group relative bg-[var(--panel)] border rounded-xl overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-xl hover:-translate-y-0.5 flex flex-col ${
                      isSelected
                        ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]'
                        : 'border-[var(--border)] hover:border-white/20'
                    }`}
                  >
                    {/* Thumbnail Area */}
                    <div className="relative aspect-video w-full bg-black/60 overflow-hidden">
                      <VideoThumb src={v.thumbnail} className="w-full h-full object-cover" />

                      {/* Top Bar inside Thumbnail: Checkbox & Category */}
                      <div className="absolute top-2 left-2 right-2 flex items-center justify-between pointer-events-none">
                        <button
                          onClick={(e) => toggleSelect(v.id, e)}
                          className={`pointer-events-auto p-1 rounded-md transition-colors ${
                            isSelected
                              ? 'bg-[var(--accent)] text-white'
                              : 'bg-black/60 text-white/70 hover:text-white backdrop-blur-xs'
                          }`}
                        >
                          {isSelected ? <CheckSquare size={14} /> : <Square size={14} />}
                        </button>

                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-black/70 text-emerald-400 backdrop-blur-xs border border-white/10 uppercase tracking-wider">
                          {v.category}
                        </span>
                      </div>

                      {/* Status Badges inside Thumbnail */}
                      <div className="absolute bottom-2 left-2 flex items-center gap-1.5 pointer-events-none">
                        {isProcessing && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500 text-white flex items-center gap-1 shadow-md animate-pulse">
                            <Loader2 size={11} className="animate-spin" /> Processing
                          </span>
                        )}
                        {isQueued && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500 text-black flex items-center gap-1 shadow-md">
                            <Clock size={11} /> Queued
                          </span>
                        )}
                        {v.status === 'completed' && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/80 text-white backdrop-blur-xs">
                            Completed
                          </span>
                        )}
                        {v.status === 'failed' && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500 text-white">
                            Failed
                          </span>
                        )}
                      </div>

                      {/* Duration inside Thumbnail */}
                      {v.duration_sec != null && (
                        <div className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-black/80 text-white/90 backdrop-blur-xs">
                          {formatDuration(v.duration_sec)}
                        </div>
                      )}
                    </div>

                    {/* Metadata Section */}
                    <div className="p-3.5 flex-1 flex flex-col justify-between space-y-3">
                      <div>
                        {isEditing ? (
                          <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
                            <input
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded px-2 py-1 text-xs text-[var(--text)]"
                            />
                            <select
                              value={editCategory}
                              onChange={(e) => setEditCategory(e.target.value)}
                              className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded px-2 py-1 text-xs text-[var(--text)]"
                            >
                              {VIDEO_CATEGORIES.map((c) => (
                                <option key={c} value={c}>{c}</option>
                              ))}
                            </select>
                            <div className="flex justify-end gap-1.5 pt-1">
                              <button
                                disabled={saving}
                                onClick={() => setEditingId(null)}
                                className="px-2 py-1 rounded bg-[var(--panel-2)] text-[10px] font-bold text-[var(--muted)]"
                              >
                                Cancel
                              </button>
                              <button
                                disabled={saving}
                                onClick={() => saveEdit(v.id)}
                                className="px-2.5 py-1 rounded bg-[var(--accent)] text-[10px] font-bold text-white flex items-center gap-1"
                              >
                                {saving ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />} Save
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-start justify-between gap-2">
                            <h3
                              title={v.filename}
                              className="font-semibold text-xs leading-snug line-clamp-2 text-[var(--text)] group-hover:text-[var(--accent)] transition-colors"
                            >
                              {v.filename}
                            </h3>
                            <button
                              onClick={(e) => startEdit(v, e)}
                              className="opacity-0 group-hover:opacity-100 p-1 text-[var(--muted)] hover:text-white transition-opacity"
                              title="Edit metadata"
                            >
                              <Pencil size={12} />
                            </button>
                          </div>
                        )}
                        <p className="text-[10px] text-[var(--muted)] mt-1">
                          Uploaded {formatDate(v.uploaded_at)}
                        </p>
                      </div>

                      {/* Analytics Metrics Preview */}
                      <div className="pt-2.5 border-t border-[var(--border)]/60 flex items-center justify-between text-[11px]">
                        <div>
                          <div className="text-[10px] text-[var(--muted)] uppercase tracking-wider font-semibold">
                            Peak People
                          </div>
                          <div className="font-mono font-bold text-sm text-[var(--text)]">
                            {v.last_people ?? '—'}
                          </div>
                        </div>

                        <div className="text-right">
                          <div className="text-[10px] text-[var(--muted)] uppercase tracking-wider font-semibold mb-0.5">
                            Risk Level
                          </div>
                          {v.last_level ? (
                            <RiskBadge level={v.last_level} />
                          ) : (
                            <span className="text-[10px] text-[var(--muted)]">Not Analyzed</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: SAMPLE VIDEO LIBRARY (7 CATEGORIES)                                */}
      {/* ========================================================================= */}
      {activeTab === 'samples' && (
        <div className="space-y-4">
          {/* Research & Attribution Notice */}
          <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-3 text-xs text-emerald-200/90 leading-relaxed">
            <Info size={16} className="text-emerald-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-bold text-white">
                Curated Crowd-Safety Test Library Across 7 Event Categories
              </p>
              <p className="text-[11px] text-emerald-300/80">
                Derived from verified open datasets: <strong>Wikimedia Commons</strong> (CC-BY/CC-BY-SA), <strong>OpenCV UCF Benchmarks</strong> (BSD), 
                <strong> Zenodo PPS-D</strong> (CC-BY 4.0 record 15124010), and <strong>HuggingFace WalkIndia-50</strong>. 
                Click <strong>"Import to CrowdLens"</strong> to load any video into your active workspace and run the computer-vision pipeline.
              </p>
            </div>
          </div>

          {importNotice && (
            <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/30 text-xs text-blue-300 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <CheckCircle2 size={15} className="text-blue-400" />
                {importNotice}
              </span>
              <button onClick={() => setImportNotice(null)} className="text-blue-400 hover:text-white">
                <X size={14} />
              </button>
            </div>
          )}

          {/* Sample Filters Panel */}
          <Panel className="p-3.5 space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {/* Search */}
              <div className="relative flex-1 min-w-[240px]">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" />
                <input
                  value={sampleSearch}
                  onChange={(e) => setSampleSearch(e.target.value)}
                  placeholder="Search samples by title, category, scenario, source, or license..."
                  className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-lg pl-9 pr-8 py-2 text-xs text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
                />
                {sampleSearch && (
                  <button
                    onClick={() => setSampleSearch('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-white"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>

              {/* Scenario Filter */}
              <div className="flex items-center gap-1.5 shrink-0 text-xs">
                <Filter size={14} className="text-[var(--muted)]" />
                <select
                  value={sampleScenario}
                  onChange={(e) => setSampleScenario(e.target.value)}
                  className="bg-[var(--panel-2)] border border-[var(--border)] rounded-lg px-2.5 py-2 text-xs text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
                >
                  {SCENARIO_FILTERS.map((sc) => (
                    <option key={sc} value={sc}>{sc}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* 7 Category Filter Chips */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
              {CATEGORY_FILTERS.map((c) => {
                const isSelected = sampleCategory === c
                return (
                  <button
                    key={c}
                    onClick={() => setSampleCategory(c)}
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

          {/* Sample Cards Grid */}
          {loadingSamples ? (
            <Panel className="p-8 text-center text-xs text-[var(--muted)] flex items-center justify-center gap-2">
              <Loader2 size={16} className="animate-spin text-[var(--accent)]" />
              Loading verified sample library…
            </Panel>
          ) : filteredSamples.length === 0 ? (
            <Panel className="p-8 text-center">
              <EmptyState title="No sample videos found" hint="Try adjusting your keyword, scenario, or category filter." />
            </Panel>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredSamples.map((sample) => {
                const isImporting = importingId === sample.id
                return (
                  <Panel
                    key={sample.id}
                    className="p-4 flex flex-col justify-between space-y-3.5 border border-[var(--border)] hover:border-emerald-500/40 transition-all shadow-sm"
                  >
                    {/* Top Badges */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          {sample.category}
                        </span>

                        {sample.is_synthetic ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/20">
                            Synthetic (PPS-D Simulation)
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                            Real Recorded Footage
                          </span>
                        )}
                      </div>

                      {/* Title & Scenario */}
                      <div>
                        <h3 className="font-bold text-sm text-[var(--text)] leading-snug">
                          {sample.title}
                        </h3>
                        <div className="inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-[var(--panel-2)] text-[var(--muted)] border border-[var(--border)]">
                          Scenario: {sample.scenario_type}
                        </div>
                      </div>

                      {/* Description */}
                      <p className="text-xs text-[var(--muted)] leading-relaxed line-clamp-3">
                        {sample.description}
                      </p>

                      {/* Expected Indicators */}
                      <div className="p-2.5 rounded-lg bg-[var(--panel-2)] border border-[var(--border)]/60 text-[11px] text-[var(--muted)] space-y-1">
                        <span className="font-semibold text-emerald-400 block text-[10px] uppercase tracking-wider">
                          Observable Safety Cues:
                        </span>
                        <p className="line-clamp-2">{sample.expected_indicators}</p>
                      </div>
                    </div>

                    {/* Meta info & Action Buttons */}
                    <div className="space-y-3 pt-2 border-t border-[var(--border)]/60">
                      <div className="flex items-center justify-between text-[10px] text-[var(--muted)] font-mono flex-wrap gap-1">
                        <span>{sample.resolution || '1080p'} · {sample.duration_sec ? `${sample.duration_sec}s` : 'Multi-minute'}</span>
                        <span className="px-1.5 py-0.2 rounded bg-[var(--panel-2)] text-[var(--text)]">{sample.license}</span>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Open Source Button */}
                        <a
                          href={sample.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex-1 py-1.5 px-2 rounded-lg bg-[var(--panel-2)] hover:bg-white/10 text-[var(--text)] text-xs font-semibold flex items-center justify-center gap-1.5 border border-[var(--border)] transition-colors"
                        >
                          <ExternalLink size={12} /> Source Page
                        </a>

                        {/* Import / Open Button */}
                        {sample.is_imported && sample.video_id ? (
                          <button
                            onClick={() => navigate(`/videos/${sample.video_id}`)}
                            className="flex-1 py-1.5 px-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow transition-colors"
                          >
                            <Play size={12} /> Analyze / View
                          </button>
                        ) : (
                          <button
                            disabled={isImporting}
                            onClick={() => handleImportSample(sample)}
                            className="flex-1 py-1.5 px-2 rounded-lg bg-[var(--accent)] hover:bg-emerald-600 disabled:opacity-50 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow transition-colors"
                          >
                            {isImporting ? (
                              <>
                                <Loader2 size={12} className="animate-spin" /> Importing…
                              </>
                            ) : (
                              <>
                                <Download size={12} /> Import to Hub
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  </Panel>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* MULTI-VIDEO UPLOAD MODAL                                                  */}
      {/* ========================================================================= */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-[var(--panel)] border border-[var(--border)] rounded-2xl w-full max-w-lg p-5 space-y-4 shadow-2xl animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-2 border-b border-[var(--border)]">
              <div>
                <h2 className="text-base font-bold text-[var(--text)]">Upload Crowd Videos</h2>
                <p className="text-[11px] text-[var(--muted)]">
                  Select one or more files (MP4, MOV, WebM, AVI, MKV up to 500MB each)
                </p>
              </div>
              <button
                disabled={uploadingAll}
                onClick={() => {
                  setShowUploadModal(false)
                  setUploadQueue([])
                }}
                className="text-[var(--muted)] hover:text-white p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {/* Drop Zone / File Picker */}
            <div
              onClick={() => inputRef.current?.click()}
              className="border-2 border-dashed border-[var(--border)] hover:border-[var(--accent)] rounded-xl p-6 text-center cursor-pointer transition-colors bg-[var(--panel-2)]"
            >
              <Upload size={28} className="mx-auto text-[var(--muted)] mb-2" />
              <p className="text-xs font-semibold text-[var(--text)]">
                Click to browse files or drag & drop video files here
              </p>
              <p className="text-[10px] text-[var(--muted)] mt-1">
                Multiple files supported in a single operation
              </p>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept=".mp4,.mov,.webm,.avi,.mkv,video/mp4,video/webm,video/quicktime,video/x-msvideo"
                onChange={(e) => handleFilesSelected(e.target.files)}
                className="hidden"
              />
            </div>

            {/* Category selection for current upload batch */}
            <div>
              <label className="text-[11px] font-semibold text-[var(--muted)] block mb-1">
                Assign Category for this batch:
              </label>
              <select
                value={uploadCategory}
                onChange={(e) => setUploadCategory(e.target.value)}
                className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
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
                  className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs font-semibold hover:bg-white/5"
                >
                  Close
                </button>
                <button
                  type="button"
                  disabled={uploadingAll || uploadQueue.length === 0}
                  onClick={executeQueueUpload}
                  className="px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-emerald-600 text-white text-xs font-bold flex items-center gap-1.5 shadow"
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
