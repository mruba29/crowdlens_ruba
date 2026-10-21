import React, { useState } from 'react'
import { AlertOctagon, CheckCircle2, Clock, ShieldAlert, Send, Plus, Filter, MessageSquare, ChevronRight } from 'lucide-react'
import { useApp } from '../store'
import { api } from '../lib/api'
import { Panel, RiskBadge, EmptyState, StatCard } from '../components/ui'
import type { Incident, RiskLevel } from '../lib/types'

const STATUS_FILTERS = ['ALL', 'OPEN', 'INVESTIGATING', 'DISPATCHED', 'RESOLVED'] as const

export default function Incidents() {
  const { incidents, refreshIncidents } = useApp()
  const [statusFilter, setStatusFilter] = useState<string>('ALL')
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null)
  const [operatorNotes, setOperatorNotes] = useState('')
  const [updating, setUpdating] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newZone, setNewZone] = useState('Zone B - Main Concourse')
  const [newTitle, setNewTitle] = useState('')
  const [newSeverity, setNewSeverity] = useState<RiskLevel>('RED')
  const [newDesc, setNewDesc] = useState('')

  const filtered = incidents.filter((inc) => {
    if (statusFilter === 'ALL') return true
    return inc.status === statusFilter
  })

  const openCount = incidents.filter((i) => i.status === 'OPEN' || i.status === 'INVESTIGATING' || i.status === 'DISPATCHED').length
  const criticalCount = incidents.filter((i) => (i.severity === 'RED' || i.severity === 'BLACK') && i.status !== 'RESOLVED').length
  const resolvedCount = incidents.filter((i) => i.status === 'RESOLVED').length

  async function handleStatusChange(id: number, nextStatus: string) {
    setUpdating(true)
    try {
      await api.updateIncident(id, {
        status: nextStatus,
        operator_notes: operatorNotes.trim() || undefined,
      })
      await refreshIncidents()
      setOperatorNotes('')
      setSelectedIncident(null)
    } finally {
      setUpdating(false)
    }
  }

  async function handleCreateIncident(e: React.FormEvent) {
    e.preventDefault()
    if (!newTitle.trim()) return
    setUpdating(true)
    try {
      await api.createIncident({
        zone: newZone,
        title: newTitle.trim(),
        severity: newSeverity,
        description: newDesc.trim() || undefined,
        recommended_action: 'Dispatch field stewards to assess physical crowd bottleneck.',
      })
      await refreshIncidents()
      setShowCreateModal(false)
      setNewTitle('')
      setNewDesc('')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <ShieldAlert size={28} className="text-red-400" />
          <div>
            <h1 className="text-xl font-bold leading-tight">Crowd Safety Incidents</h1>
            <p className="text-sm text-[var(--muted)] leading-tight">
              Actionable public safety emergency incidents generated from RED/BLACK crowd alerts
            </p>
          </div>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-white text-xs font-semibold flex items-center gap-1.5 hover:bg-emerald-600 transition-colors"
        >
          <Plus size={14} /> Log Manual Incident
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Total Logged Incidents" value={incidents.length} sub="Lifetime incident log" />
        <StatCard
          label="Active / In Progress"
          value={openCount}
          sub={openCount > 0 ? 'Requires control room attention' : 'All clear'}
          subClass={openCount > 0 ? 'text-amber-400 font-bold' : 'text-emerald-400'}
        />
        <StatCard
          label="Critical Severity"
          value={criticalCount}
          sub={criticalCount > 0 ? 'RED/BLACK risk active' : 'None active'}
          subClass={criticalCount > 0 ? 'text-red-400 font-bold' : 'text-[var(--muted)]'}
        />
        <StatCard label="Resolved Incidents" value={resolvedCount} sub="Successfully closed" />
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
              statusFilter === s
                ? 'bg-[var(--accent)]/15 border-[var(--accent)] text-[var(--text)] font-semibold'
                : 'border-[var(--border)] text-[var(--muted)] hover:border-white/20'
            }`}
          >
            {s} {s === 'OPEN' && openCount > 0 && <span className="ml-1 text-[10px] bg-red-500 text-white rounded-full px-1.5 py-0.2">{openCount}</span>}
          </button>
        ))}
      </div>

      {/* Incident List */}
      {filtered.length === 0 ? (
        <Panel>
          <EmptyState
            title="No incidents found"
            hint={
              statusFilter === 'ALL'
                ? 'High-risk crowd surges (RED/BLACK) automatically open safety incidents here.'
                : `No incidents with status "${statusFilter}".`
            }
          />
        </Panel>
      ) : (
        <div className="space-y-3">
          {filtered.map((inc) => {
            const isResolved = inc.status === 'RESOLVED'
            const isCritical = inc.severity === 'RED' || inc.severity === 'BLACK'
            return (
              <Panel
                key={inc.id}
                className={`transition-all ${
                  isCritical && !isResolved
                    ? 'border-red-500/60 bg-red-500/5'
                    : isResolved
                    ? 'opacity-85 border-[var(--border)]'
                    : 'border-amber-500/40 bg-amber-500/5'
                }`}
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="space-y-1.5 flex-1 min-w-[260px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs text-[var(--muted)] font-bold">
                        #INC-{String(inc.id).padStart(4, '0')}
                      </span>
                      <RiskBadge level={inc.severity} />
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                        inc.status === 'OPEN'
                          ? 'bg-red-500/20 text-red-300 border-red-500/40'
                          : inc.status === 'INVESTIGATING'
                          ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                          : inc.status === 'DISPATCHED'
                          ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                          : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      }`}>
                        {inc.status}
                      </span>
                      <span className="text-xs text-[var(--muted)]">
                        Logged {new Date(inc.created_at * 1000).toLocaleTimeString()}
                      </span>
                    </div>

                    <h3 className="text-sm font-bold text-[var(--text)]">{inc.title}</h3>
                    <p className="text-xs text-[var(--muted)]">
                      Zone: <span className="font-semibold text-[var(--text)]">{inc.zone}</span>
                      {inc.video_id && ` · Video: ${inc.video_id}`}
                    </p>
                    {inc.description && (
                      <p className="text-xs text-[var(--muted)] leading-relaxed bg-[var(--panel-2)]/60 p-2 rounded border border-[var(--border)]">
                        {inc.description}
                      </p>
                    )}
                    {inc.recommended_action && (
                      <p className="text-xs text-amber-300/90 font-medium">
                        Protocol Action: {inc.recommended_action}
                      </p>
                    )}
                    {inc.operator_notes && (
                      <p className="text-xs text-emerald-400 bg-emerald-500/10 p-2 rounded border border-emerald-500/30">
                        Operator Note: {inc.operator_notes}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col sm:flex-row items-center gap-2 shrink-0">
                    {!isResolved ? (
                      <>
                        {inc.status === 'OPEN' && (
                          <button
                            disabled={updating}
                            onClick={() => handleStatusChange(inc.id, 'DISPATCHED')}
                            className="px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold"
                          >
                            Dispatch Stewards
                          </button>
                        )}
                        {inc.status !== 'INVESTIGATING' && inc.status !== 'RESOLVED' && (
                          <button
                            disabled={updating}
                            onClick={() => handleStatusChange(inc.id, 'INVESTIGATING')}
                            className="px-3 py-1.5 rounded-md bg-[var(--panel-2)] border border-[var(--border)] hover:bg-white/5 text-xs font-semibold"
                          >
                            Mark In Progress
                          </button>
                        )}
                        <button
                          disabled={updating}
                          onClick={() => {
                            setSelectedIncident(inc)
                            setOperatorNotes('')
                          }}
                          className="px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold flex items-center gap-1"
                        >
                          <CheckCircle2 size={13} /> Resolve
                        </button>
                      </>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
                        <CheckCircle2 size={14} /> Resolved {inc.resolved_at ? new Date(inc.resolved_at * 1000).toLocaleTimeString() : ''}
                      </div>
                    )}
                  </div>
                </div>
              </Panel>
            )
          })}
        </div>
      )}

      {/* Resolve Modal */}
      {selectedIncident && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--panel)] border border-[var(--border)] rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-[var(--text)]">
              Resolve Incident #INC-{String(selectedIncident.id).padStart(4, '0')}
            </h3>
            <p className="text-xs text-[var(--muted)]">
              {selectedIncident.title} ({selectedIncident.zone})
            </p>
            <div>
              <label className="block text-xs font-medium text-[var(--muted)] mb-1">
                Resolution Notes / Operator Field Confirmation
              </label>
              <textarea
                value={operatorNotes}
                onChange={(e) => setOperatorNotes(e.target.value)}
                rows={3}
                placeholder="E.g. Crowd dispersed safely, secondary gate opened, bottleneck cleared."
                className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md p-2 text-xs text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setSelectedIncident(null)}
                className="px-3 py-1.5 rounded-md border border-[var(--border)] text-xs font-medium"
              >
                Cancel
              </button>
              <button
                disabled={updating}
                onClick={() => handleStatusChange(selectedIncident.id, 'RESOLVED')}
                className="px-4 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
              >
                Confirm Incident Resolution
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual Create Incident Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleCreateIncident}
            className="bg-[var(--panel)] border border-[var(--border)] rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl"
          >
            <h3 className="text-base font-bold text-[var(--text)]">Log Manual Safety Incident</h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-medium text-[var(--muted)] mb-1">Incident Title</label>
                <input
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="E.g. Gate 3 Barricade Obstruction"
                  className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md p-2"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-medium text-[var(--muted)] mb-1">Affected Zone</label>
                  <input
                    value={newZone}
                    onChange={(e) => setNewZone(e.target.value)}
                    className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md p-2"
                  />
                </div>
                <div>
                  <label className="block font-medium text-[var(--muted)] mb-1">Severity</label>
                  <select
                    value={newSeverity}
                    onChange={(e) => setNewSeverity(e.target.value as RiskLevel)}
                    className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md p-2"
                  >
                    <option value="YELLOW">YELLOW (Moderate)</option>
                    <option value="ORANGE">ORANGE (High Risk)</option>
                    <option value="RED">RED (Critical)</option>
                    <option value="BLACK">BLACK (Emergency)</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block font-medium text-[var(--muted)] mb-1">Description / Observations</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  rows={2}
                  placeholder="Details of the hazard..."
                  className="w-full bg-[var(--panel-2)] border border-[var(--border)] rounded-md p-2"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="px-3 py-1.5 rounded-md border border-[var(--border)] text-xs font-medium"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={updating}
                className="px-4 py-1.5 rounded-md bg-[var(--accent)] text-white text-xs font-bold"
              >
                Create Incident Log
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
