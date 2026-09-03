import React from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Video, BarChart3, Bell, Settings as SettingsIcon, ShieldCheck } from 'lucide-react'
import { useApp } from '../store'
import { Dot } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/live', label: 'Live Analysis', icon: Video },
  { to: '/analytics', label: 'Crowd Analytics', icon: BarChart3 },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { connected, health, alerts } = useApp()
  const active = alerts.filter((a) => a.status === 'ACTIVE').length
  const detector = health?.detector

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-[var(--border)] bg-[var(--panel)] flex flex-col sticky top-0 h-screen">
        <div className="px-4 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <ShieldCheck size={20} className="text-[var(--accent)]" />
            <span className="font-bold tracking-tight">CROWDLENS</span>
          </div>
          <p className="text-[10px] text-[var(--muted)] mt-1">Real-Time Crowd Safety</p>
        </div>
        <nav className="flex-1 py-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2 text-sm mx-2 rounded-md transition-colors ${
                  isActive ? 'bg-[var(--accent)]/15 text-[var(--text)]' : 'text-[var(--muted)] hover:bg-white/5 hover:text-[var(--text)]'
                }`}>
              <Icon size={16} />
              <span className="flex-1">{label}</span>
              {to === '/alerts' && active > 0 && (
                <span className="text-[10px] font-bold bg-red-500 text-white rounded-full px-1.5 py-0.5">{active}</span>
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
            <span className="text-xs text-[var(--muted)] truncate hidden sm:inline">Real-Time Crowd Safety</span>
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
