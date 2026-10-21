import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Film, Video, BarChart3, TrendingUp, Bell, AlertOctagon,
  Settings as SettingsIcon, ShieldCheck, CalendarClock,
} from 'lucide-react'
import { useApp } from '../store'
import { Dot } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/videos', label: 'Crowd Videos', icon: Film },
  { to: '/live', label: 'Live Analysis', icon: Video },
  { to: '/analytics', label: 'Crowd Analytics', icon: BarChart3 },
  { to: '/predictive-risk', label: 'Predictive Risk', icon: TrendingUp },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/incidents', label: 'Incidents', icon: AlertOctagon },
  { to: '/events', label: 'Events & Multi-Cam', icon: CalendarClock },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { connected, health, alerts, incidents } = useApp()
  const activeAlerts = alerts.filter((a) => a.status === 'ACTIVE').length
  const activeIncidents = incidents.filter((i) => i.status !== 'RESOLVED').length
  const detector = health?.detector

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-[var(--border)] bg-[var(--panel)] flex flex-col sticky top-0 h-screen">
        <div className="px-4 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <ShieldCheck size={20} className="text-[var(--accent)]" />
            <span className="font-bold tracking-tight">CROWDLENS</span>
          </div>
          <p className="text-[10px] text-[var(--muted)] mt-1">Real-Time Crowd Safety Intelligence</p>
        </div>
        <nav className="flex-1 py-2 overflow-y-auto">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 text-xs font-medium mx-2 rounded-md transition-colors ${
                  isActive ? 'bg-[var(--accent)]/15 text-[var(--accent)] font-semibold' : 'text-[var(--muted)] hover:bg-white/5 hover:text-[var(--text)]'
                }`}>
              <Icon size={16} />
              <span className="flex-1 truncate">{label}</span>
              {to === '/alerts' && activeAlerts > 0 && (
                <span className="text-[10px] font-bold bg-red-500 text-white rounded-full px-1.5 py-0.5">{activeAlerts}</span>
              )}
              {to === '/incidents' && activeIncidents > 0 && (
                <span className="text-[10px] font-bold bg-amber-500 text-black rounded-full px-1.5 py-0.5">{activeIncidents}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-[var(--border)] text-[10px] text-[var(--muted)] leading-relaxed">
          No facial recognition.<br />No personal identification.<br />Anonymous crowd analytics only.
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 border-b border-[var(--border)] bg-[var(--panel)] px-5 flex items-center justify-between gap-4 sticky top-0 z-10">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-semibold">CROWDLENS</span>
            <span className="text-xs text-[var(--muted)] truncate hidden sm:inline">Real-Time Crowd Safety Intelligence</span>
          </div>
          <div className="flex items-center gap-4 shrink-0">
            <Dot ok={!!health} label={health ? 'SYSTEM ONLINE' : 'BACKEND OFFLINE'} />
            <Dot ok={connected} label={connected ? 'LIVE FEED' : 'NO FEED'} />
            <span className="text-[11px] text-[var(--muted)] hidden md:inline">
              {detector
                ? `Detector: ${detector.is_yolo ? 'YOLO' : detector.available ? 'HOG+SVM' : 'unavailable'}`
                : 'Detector: —'}
            </span>
          </div>
        </header>
        <main className="flex-1 p-5 min-w-0 overflow-x-hidden">{children}</main>
      </div>
    </div>
  )
}
