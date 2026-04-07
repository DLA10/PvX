import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import Feed from './components/Feed'
import Dashboard from './components/Dashboard'
import Config from './components/Config'
import CostTracker from './components/CostTracker'
import DirectChat from './components/DirectChat'
import ShadowTerminal from './components/ShadowTerminal'

const App = () => {
  const [activeNav, setActiveNav] = useState('dashboard')

  const now = new Date().toLocaleDateString('en-GB', {
    weekday: 'short', day: '2-digit', month: 'short', year: 'numeric'
  })

  return (
    <div className="flex h-screen bg-t-black text-t-orange font-mono overflow-hidden boot-flicker">
      <Sidebar active={activeNav} onNav={setActiveNav} />

      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ── Top header bar ─────────────────────────────────────────────── */}
        <header className="shrink-0 border-b border-t-border bg-t-panel px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className="text-xs text-t-or-dim tracking-widest">
              ┌─ PvX ORCHESTRATION TERMINAL
            </span>
          </div>
          <div className="flex items-center gap-6 text-xs text-t-or-dim tracking-widest">
            <span>{now}</span>
            <span className="text-t-border">│</span>
            <span className="text-t-or-mid">REST: localhost:8000</span>
            <span className="text-t-border">│</span>
            <span className="text-t-or-mid">MCP: pvx-mcp</span>
          </div>
        </header>

        {/* ── Main content ───────────────────────────────────────────────── */}
        <main className="flex-1 overflow-hidden flex gap-0 pb-40">

          {activeNav === 'config' ? (
            <div className="flex-1 overflow-y-auto"><Config /></div>
          ) : activeNav === 'cost' ? (
            <div className="flex-1 overflow-y-auto"><CostTracker /></div>
          ) : activeNav === 'chat' ? (
            <div className="flex-1 overflow-hidden flex flex-col"><DirectChat /></div>
          ) : (
            <>
              {/* Feed — takes 2/3 */}
              <div className="flex-1 border-r border-t-border overflow-hidden flex flex-col">
                <Feed />
              </div>
              {/* Dashboard sidebar */}
              <div className="w-72 shrink-0 overflow-y-auto p-3">
                <Dashboard />
              </div>
            </>
          )}
        </main>
      </div>

      <ShadowTerminal />
    </div>
  )
}

export default App
