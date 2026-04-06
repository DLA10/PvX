import React, { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

// ─── Priority label ───────────────────────────────────────────────────────────
const PRIORITY_LABEL = { 5: 'CRIT', 4: 'HIGH', 3: 'NORM', 2: 'LOW', 1: 'BKGD' }
const PRIORITY_COLOR  = {
  5: 'text-red-500',
  4: 'text-t-amber',
  3: 'text-t-orange',
  2: 'text-t-or-mid',
  1: 'text-t-or-dim',
}

// ─── Status display ───────────────────────────────────────────────────────────
const STATUS_GLYPH = {
  pending:   { g: '◌', c: 'text-t-or-dim' },
  running:   { g: '◉', c: 'text-t-orange glow-or animate-pulse' },
  done:      { g: '◆', c: 'text-t-or-dim' },
  failed:    { g: '✗', c: 'text-red-500' },
  blocked:   { g: '⊘', c: 'text-t-maroon' },
  timeout:   { g: '⊘', c: 'text-t-maroon' },
  preempted: { g: '⇩', c: 'text-t-amber' },
}

// ─── Task row ─────────────────────────────────────────────────────────────────
const TaskRow = ({ task }) => {
  const { g, c } = STATUS_GLYPH[task.status] || STATUS_GLYPH.pending
  const age = task.created_at
    ? Math.floor((Date.now() - new Date(task.created_at)) / 1000)
    : 0
  const ageStr = age < 60 ? `${age}s` : `${Math.floor(age / 60)}m${age % 60}s`

  return (
    <div className="border-b border-t-border py-1.5 hover:bg-t-deep transition-colors group">
      <div className="flex items-center gap-2 text-xs px-1">
        <span className={`${c} w-3 text-center shrink-0`}>{g}</span>
        <span className="text-t-or-dim shrink-0 w-20 truncate font-bold">
          {task.id.replace('task_', '')}
        </span>
        <span className={`shrink-0 w-8 ${PRIORITY_COLOR[task.priority] || 'text-t-or-dim'}`}>
          {PRIORITY_LABEL[task.priority] || 'NORM'}
        </span>
        <span className="text-t-orange truncate flex-1">
          {task.model ? task.model.replace(/:latest$/, '') : '—'}
        </span>
        <span className="text-t-or-dim shrink-0 w-12 text-right">{ageStr}</span>
      </div>
      <div className="pl-6 text-t-or-dim text-xs truncate mt-0.5 px-1">
        {task.category || '—'}
      </div>
    </div>
  )
}

// ─── Event log entry (from WebSocket) ────────────────────────────────────────
const EventEntry = ({ event }) => {
  const time = new Date(event.timestamp).toLocaleTimeString('en-GB', { hour12: false })
  const typeColor = {
    task_submitted: 'text-t-or-mid',
    task_started:   'text-t-orange glow-dim',
    task_done:      'text-t-or-dim',
    task_failed:    'text-red-400',
    vram_warn:      'text-t-amber',
    model_loaded:   'text-t-bright',
    model_evicted:  'text-t-or-dim',
  }
  const c = typeColor[event.type] || 'text-t-or-dim'

  return (
    <div className="border-b border-t-border py-1 text-xs hover:bg-t-deep transition-colors">
      <div className="flex items-baseline gap-2 px-1">
        <span className="text-t-or-dim shrink-0 w-16">[{time}]</span>
        <span className={`${c} shrink-0 uppercase tracking-wide`}>{event.type}</span>
        {event.task_id && (
          <span className="text-t-or-dim truncate">
            {event.task_id.replace('task_', '#')}
          </span>
        )}
      </div>
      {event.payload && Object.keys(event.payload).length > 0 && (
        <div className="pl-[4.5rem] text-t-or-dim truncate mt-0.5 px-1">
          {JSON.stringify(event.payload).slice(0, 80)}
        </div>
      )}
    </div>
  )
}

// ─── Main Feed ────────────────────────────────────────────────────────────────
const Feed = () => {
  const [tasks,   setTasks]   = useState([])
  const [events,  setEvents]  = useState([])
  const [view,    setView]    = useState('tasks')   // 'tasks' | 'events'
  const [wsState, setWsState] = useState('CONNECTING')
  const wsRef     = useRef(null)
  const eventsRef = useRef(events)
  eventsRef.current = events

  // Poll tasks every 2s
  useEffect(() => {
    const fetch = async () => {
      try {
        const r = await axios.get('/api/tasks/')
        setTasks(r.data)
      } catch { /* backend may be starting */ }
    }
    fetch()
    const id = setInterval(fetch, 2000)
    return () => clearInterval(id)
  }, [])

  // WebSocket for live events
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(`ws://${location.host}/ws/events`)
      wsRef.current = ws

      ws.onopen  = () => setWsState('LIVE')
      ws.onclose = () => {
        setWsState('RECONNECTING')
        setTimeout(connect, 3000)
      }
      ws.onerror = () => setWsState('ERROR')
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data)
          setEvents(prev => [ev, ...prev].slice(0, 120))
        } catch { /* ignore malformed */ }
      }
    }
    connect()
    return () => wsRef.current?.close()
  }, [])

  // Sorted tasks — running first, then pending, then done/failed
  const sorted = [...tasks].sort((a, b) => {
    const order = { running: 0, pending: 1, done: 2, failed: 3 }
    return (order[a.status] ?? 9) - (order[b.status] ?? 9)
  })

  const running = tasks.filter(t => t.status === 'running').length
  const pending = tasks.filter(t => t.status === 'pending').length

  return (
    <div className="flex flex-col h-full font-mono">

      {/* ── Header bar ────────────────────────────────────────────────────── */}
      <div className="panel px-3 py-2 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-xs tracking-widest text-t-or-mid uppercase">
            Orchestration Log
          </span>
          {running > 0 && (
            <span className="text-xs text-t-orange animate-pulse glow-or">
              ● {running} RUNNING
            </span>
          )}
          {pending > 0 && (
            <span className="text-xs text-t-amber">
              ◌ {pending} QUEUED
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Tab buttons */}
          <button
            onClick={() => setView('tasks')}
            className={`text-xs tracking-widest px-2 py-0.5 border transition-colors ${
              view === 'tasks'
                ? 'border-t-orange text-t-orange'
                : 'border-t-border text-t-or-dim hover:border-t-or-mid'
            }`}
          >
            TASKS
          </button>
          <button
            onClick={() => setView('events')}
            className={`text-xs tracking-widest px-2 py-0.5 border transition-colors ${
              view === 'events'
                ? 'border-t-orange text-t-orange'
                : 'border-t-border text-t-or-dim hover:border-t-or-mid'
            }`}
          >
            EVENTS
          </button>
          {/* WS status */}
          <span className={`text-xs tracking-widest ${
            wsState === 'LIVE' ? 'text-t-orange glow-or' : 'text-t-maroon'
          }`}>
            {wsState === 'LIVE' ? '◉' : '○'} {wsState}
          </span>
        </div>
      </div>

      {/* ── Column headers ────────────────────────────────────────────────── */}
      {view === 'tasks' && (
        <div className="px-3 py-1 border-b border-t-border bg-t-panel shrink-0">
          <div className="flex gap-2 text-xs text-t-or-dim tracking-widest pl-1">
            <span className="w-3"> </span>
            <span className="w-20">ID</span>
            <span className="w-8">PRI</span>
            <span className="flex-1">MODEL</span>
            <span className="w-12 text-right">AGE</span>
          </div>
        </div>
      )}
      {view === 'events' && (
        <div className="px-3 py-1 border-b border-t-border bg-t-panel shrink-0">
          <div className="flex gap-2 text-xs text-t-or-dim tracking-widest pl-1">
            <span className="w-16">TIME</span>
            <span>TYPE</span>
          </div>
        </div>
      )}

      {/* ── Content ───────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto panel-bright">
        {view === 'tasks' && (
          sorted.length === 0 ? (
            <div className="flex items-center justify-center h-full text-t-or-dim text-xs tracking-widest">
              NO TASKS<span className="cursor ml-1">█</span>
            </div>
          ) : (
            sorted.map(t => <TaskRow key={t.id} task={t} />)
          )
        )}
        {view === 'events' && (
          events.length === 0 ? (
            <div className="flex items-center justify-center h-full text-t-or-dim text-xs tracking-widest">
              AWAITING EVENTS<span className="cursor ml-1">█</span>
            </div>
          ) : (
            events.map((ev, i) => <EventEntry key={i} event={ev} />)
          )
        )}
      </div>
    </div>
  )
}

export default Feed
