import React, { useState, useEffect } from 'react'
import axios from 'axios'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'DASHBOARD' },
  { id: 'tasks',     label: 'TASKS'     },
  { id: 'models',    label: 'MODELS'    },
  { id: 'config',    label: 'CONFIG'    },
]

const Sidebar = ({ active = 'dashboard', onNav }) => {
  const [health, setHealth] = useState(null)
  const [sessionSecs, setSessionSecs] = useState(0)

  useEffect(() => {
    const fetch = async () => {
      try {
        const r = await axios.get('/api/health')
        setHealth(r.data)
      } catch {
        setHealth(null)
      }
    }
    fetch()
    const id = setInterval(fetch, 5000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const id = setInterval(() => setSessionSecs(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const h = Math.floor(sessionSecs / 3600)
  const m = Math.floor((sessionSecs % 3600) / 60)
  const s = sessionSecs % 60
  const uptimeStr = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
  const pvxReady = health?.pvx_ready ?? false

  return (
    <aside className="w-44 flex flex-col border-r border-t-border bg-t-panel shrink-0 font-mono">

      {/* Logo */}
      <div className="px-3 pt-4 pb-3 border-b border-t-border">
        <div className="text-2xl font-bold glow-or text-t-orange tracking-widest">PvX</div>
        <div className="text-xs text-t-or-dim tracking-widest mt-0.5">ORCHESTRATOR</div>
        <div className="text-xs text-t-border mt-0.5">v0.1.0</div>
      </div>

      {/* System status */}
      <div className="px-3 py-2 border-b border-t-border space-y-1">
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            pvxReady ? 'bg-t-orange animate-pulse' : 'bg-red-900'
          }`} />
          <span className={`text-xs tracking-widest ${pvxReady ? 'text-t-orange' : 'text-red-700'}`}>
            {pvxReady ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
        <div className="text-xs text-t-or-dim">
          UP: <span className="text-t-or-mid">{uptimeStr}</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-2">
        {NAV_ITEMS.map(item => {
          const isActive = active === item.id
          return (
            <button
              key={item.id}
              onClick={() => onNav?.(item.id)}
              className={`w-full text-left px-3 py-2 text-xs tracking-widest flex items-center gap-2 border-l-2 transition-colors ${
                isActive
                  ? 'text-t-orange bg-t-deep border-t-orange'
                  : 'text-t-or-dim hover:text-t-or-mid hover:bg-t-deep border-transparent'
              }`}
            >
              <span>{isActive ? '▸' : ' '}</span>
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-t-border text-xs text-t-or-dim space-y-1">
        <div>
          API:{' '}
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="text-t-or-mid hover:text-t-orange transition-colors"
          >
            :8000
          </a>
        </div>
        <div className="text-t-border">Apache 2.0</div>
      </div>
    </aside>
  )
}

export default Sidebar
