import React, { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

// ─── ASCII progress bar ───────────────────────────────────────────────────────
const BAR_WIDTH = 18
const asciiBar = (pct, width = BAR_WIDTH) => {
  const clamped = Math.max(0, Math.min(100, pct))
  const filled  = Math.round(clamped / 100 * width)
  return (
    <>
      <span className="bar-fill">{'█'.repeat(filled)}</span>
      <span className="bar-empty">{'░'.repeat(width - filled)}</span>
    </>
  )
}

// ─── Colour for VRAM % ────────────────────────────────────────────────────────
const vramColour = (pct) => {
  if (pct >= 90) return 'text-red-500 glow-maroon'
  if (pct >= 70) return 'text-t-amber glow-amber'
  return 'text-t-orange glow-or'
}

// ─── State badge ─────────────────────────────────────────────────────────────
const StateBadge = ({ state }) => {
  const map = {
    idle:  { label: 'IDLE',  cls: 'text-t-or-dim border-t-or-dim' },
    busy:  { label: 'BUSY',  cls: 'text-t-orange border-t-orange glow-or' },
    full:  { label: 'FULL',  cls: 'text-t-amber  border-t-amber  glow-amber' },
    oom:   { label: 'OOM',   cls: 'text-red-500  border-red-500' },
    error: { label: 'ERR',   cls: 'text-red-500  border-red-500' },
  }
  const { label, cls } = map[state] || map.idle
  return (
    <span className={`border px-1.5 py-0.5 text-xs tracking-widest ${cls}`}>
      {label}
    </span>
  )
}

// ─── Single stat row ─────────────────────────────────────────────────────────
const StatRow = ({ label, value, sub, colour = 'text-t-orange' }) => (
  <div className="flex items-baseline justify-between py-0.5">
    <span className="text-t-or-dim text-xs tracking-widest">{label}</span>
    <span className={`text-sm font-bold ${colour}`}>
      {value}
      {sub && <span className="text-t-or-dim text-xs ml-1">{sub}</span>}
    </span>
  </div>
)

// ─── Section header ───────────────────────────────────────────────────────────
const SectionHeader = ({ children }) => (
  <div className="text-xs tracking-widest text-t-or-mid border-b border-t-border pb-1 mb-2 uppercase">
    {children}
  </div>
)

// ─── Main Dashboard ───────────────────────────────────────────────────────────
const Dashboard = () => {
  const [vram,    setVram]    = useState(null)
  const [tasks,   setTasks]   = useState([])
  const [online,  setOnline]  = useState(false)
  const [tick,    setTick]    = useState(0)    // wall-clock second counter
  const [updated, setUpdated] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const [vr, tr] = await Promise.all([
        axios.get('/api/vram/'),
        axios.get('/api/tasks/'),
      ])
      setVram(vr.data)
      setTasks(tr.data)
      setOnline(true)
      setUpdated(new Date())
    } catch {
      setOnline(false)
    }
  }, [])

  // Poll every 2 s
  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 2000)
    return () => clearInterval(id)
  }, [fetchData])

  // Wall clock tick every second
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // ── derived values ──────────────────────────────────────────────────────────
  const vramPct   = vram && vram.total_mb ? (vram.used_mb / vram.total_mb * 100) : 0
  const gpuPct    = vram?.gpu_utilisation_pct ?? 0
  const usedGb    = vram ? (vram.used_mb  / 1024).toFixed(1) : '—'
  const totalGb   = vram ? (vram.total_mb / 1024).toFixed(1) : '—'
  const freeGb    = vram ? (vram.free_mb  / 1024).toFixed(1) : '—'
  const model     = vram?.loaded_model ?? 'NONE'
  const state     = vram?.vram_state ?? 'idle'

  const pending = tasks.filter(t => t.status === 'pending').length
  const running = tasks.filter(t => t.status === 'running').length
  const done    = tasks.filter(t => t.status === 'done').length
  const failed  = tasks.filter(t => t.status === 'failed').length
  const total   = tasks.length

  const nowStr = new Date().toLocaleTimeString('en-GB', { hour12: false })
  const updStr = updated ? updated.toLocaleTimeString('en-GB', { hour12: false }) : '——:——:——'

  return (
    <div className="flex flex-col gap-3 font-mono">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="panel px-3 py-2">
        <div className="flex justify-between items-center">
          <span className="text-xs tracking-widest text-t-or-dim">SYS:MONITOR</span>
          <div className="flex items-center gap-2">
            <span
              className={`w-1.5 h-1.5 rounded-full inline-block ${
                online ? 'bg-t-orange shadow-glow-or animate-pulse' : 'bg-red-900'
              }`}
            />
            <span className="text-xs text-t-or-dim">{online ? 'LIVE' : 'OFFLINE'}</span>
          </div>
        </div>
        <div className="text-base glow-or text-t-orange mt-1 tracking-wider">
          {nowStr}<span className="cursor text-t-or-mid">█</span>
        </div>
      </div>

      {/* ── VRAM Block ──────────────────────────────────────────────────────── */}
      <div className="panel-bright px-3 py-3">
        <SectionHeader>▸ VRAM ALLOCATION</SectionHeader>

        {/* Progress bar */}
        <div className="mb-3">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-t-or-mid tracking-widest">USAGE</span>
            <span className={`font-bold ${vramColour(vramPct)}`}>
              {vramPct.toFixed(1)}%
            </span>
          </div>
          <div className="text-sm font-bold leading-none tracking-tight">
            {asciiBar(vramPct)}
          </div>
        </div>

        {/* GB numbers */}
        <div className="grid grid-cols-3 gap-1 text-center mb-3">
          <div>
            <div className={`text-lg font-bold ${vramColour(vramPct)}`}>{usedGb}</div>
            <div className="text-xs text-t-or-dim">USED GB</div>
          </div>
          <div>
            <div className="text-lg font-bold text-t-or-dim">/</div>
          </div>
          <div>
            <div className="text-lg font-bold text-t-or-mid">{totalGb}</div>
            <div className="text-xs text-t-or-dim">TOTAL GB</div>
          </div>
        </div>

        {/* Loaded model + state */}
        <div className="border-t border-t-border pt-2 flex justify-between items-center">
          <div className="text-xs text-t-or-dim">
            MODEL:&nbsp;
            <span className="text-t-orange">
              {model !== 'NONE' ? model.toUpperCase() : '—'}
            </span>
          </div>
          <StateBadge state={state} />
        </div>

        {/* FREE VRAM */}
        <div className="mt-2 text-xs text-t-or-dim">
          FREE:&nbsp;<span className="text-t-amber">{freeGb} GB</span>
        </div>
      </div>

      {/* ── GPU Utilisation ──────────────────────────────────────────────────── */}
      <div className="panel px-3 py-3">
        <SectionHeader>▸ GPU UTILISATION</SectionHeader>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-t-or-dim">COMPUTE</span>
          <span className={`font-bold ${gpuPct >= 80 ? 'text-t-amber glow-amber' : 'text-t-orange'}`}>
            {gpuPct.toFixed(0)}%
          </span>
        </div>
        <div className="text-sm font-bold leading-none tracking-tight">
          {asciiBar(gpuPct)}
        </div>
      </div>

      {/* ── Task Queue Stats ─────────────────────────────────────────────────── */}
      <div className="panel px-3 py-3">
        <SectionHeader>▸ TASK QUEUE</SectionHeader>

        <div className="space-y-1">
          <StatRow
            label="RUNNING"
            value={running}
            colour={running > 0 ? 'text-t-orange glow-or' : 'text-t-or-dim'}
          />
          <StatRow
            label="PENDING"
            value={pending}
            colour={pending > 0 ? 'text-t-amber' : 'text-t-or-dim'}
          />
          <StatRow
            label="DONE"
            value={done}
            colour="text-t-or-dim"
          />
          <StatRow
            label="FAILED"
            value={failed}
            colour={failed > 0 ? 'text-red-500' : 'text-t-or-dim'}
          />
        </div>

        <div className="border-t border-t-border mt-2 pt-2">
          <StatRow label="TOTAL" value={total} colour="text-t-or-mid" />
        </div>

        {/* Mini queue bars */}
        {total > 0 && (
          <div className="mt-2 text-xs flex items-center gap-1">
            {running > 0 && (
              <span className="bar-fill">{'█'.repeat(Math.min(running, 6))}</span>
            )}
            {pending > 0 && (
              <span className="text-t-amber">{'▒'.repeat(Math.min(pending, 6))}</span>
            )}
            {done > 0 && (
              <span className="text-t-or-dim">{'░'.repeat(Math.min(done, 6))}</span>
            )}
          </div>
        )}
      </div>

      {/* ── Last update ──────────────────────────────────────────────────────── */}
      <div className="panel px-3 py-2 text-xs text-t-or-dim flex justify-between">
        <span>SYNC: {updStr}</span>
        <span>2s POLL</span>
      </div>
    </div>
  )
}

export default Dashboard
