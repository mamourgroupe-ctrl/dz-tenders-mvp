import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar, Topbar, useDarkMode } from './shared'

export function AppShell(): JSX.Element {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [darkMode, toggleDarkMode] = useDarkMode()
  return <div className="min-h-screen bg-canvas text-ink transition-colors dark:bg-slate-950 dark:text-white">
    <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
    <div className="min-h-screen lg:mr-[264px]">
      <Topbar onMenu={() => setSidebarOpen(true)} darkMode={darkMode} onToggleDark={toggleDarkMode} />
      <main className="mx-auto max-w-[1600px] px-5 py-7 lg:px-9 lg:py-8"><Outlet /></main>
    </div>
  </div>
}
