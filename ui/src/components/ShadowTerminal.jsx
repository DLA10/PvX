import React, { useState, useRef, useEffect } from 'react'
import axios from 'axios'

const ShadowTerminal = () => {
  const [lines,   setLines]   = useState([
    { type: 'sys', text: 'PvX SHADOW TERMINAL v0.1.0' },
    { type: 'sys', text: 'Type "help" for commands.' },
    { type: 'sys', text: '─────────────────────────────' },
  ])
  const [input,   setInput]   = useState('')
  const [history, setHistory] = useState([])
  const [histIdx, setHistIdx] = useState(-1)
  const [open,    setOpen]    = useState(true)
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, open])

  const addLine = (type, text) => setLines(prev => [...prev, { type, text }])

  const COMMANDS = {
    help: () => {
      addLine('out', 'Available commands:')
      addLine('out', '  submit <prompt>   — submit a task (priority 3)')
      addLine('out', '  tasks             — list all tasks')
      addLine('out', '  vram              — VRAM status')
      addLine('out', '  clear             — clear terminal')
      addLine('out', '  help              — this message')
    },
    clear: () => setLines([{ type: 'sys', text: 'Cleared.' }]),
    vram: async () => {
      try {
        const r = await axios.get('/api/vram/')
        const d = r.data
        const pct = d.total_mb ? ((d.used_mb / d.total_mb) * 100).toFixed(1) : '0.0'
        addLine('out', `VRAM: ${(d.used_mb/1024).toFixed(1)} / ${(d.total_mb/1024).toFixed(1)} GB  (${pct}%)`)
        addLine('out', `STATE: ${d.vram_state}  MODEL: ${d.loaded_model || 'none'}`)
        addLine('out', `GPU: ${d.gpu_utilisation_pct?.toFixed(0) ?? '?'}%  FREE: ${(d.free_mb/1024).toFixed(1)} GB`)
      } catch (e) {
        addLine('err', `Error: ${e.message}`)
      }
    },
    tasks: async () => {
      try {
        const r = await axios.get('/api/tasks/')
        if (r.data.length === 0) { addLine('out', 'No tasks.'); return }
        r.data.slice(0, 10).forEach(t => {
          addLine('out', `  ${t.id.replace('task_','')}  ${t.status.padEnd(8)}  p${t.priority}  ${t.model}`)
        })
        if (r.data.length > 10) addLine('out', `  ... and ${r.data.length - 10} more`)
      } catch (e) {
        addLine('err', `Error: ${e.message}`)
      }
    },
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const raw = input.trim()
    if (!raw) return

    addLine('in', `> ${raw}`)
    setHistory(h => [raw, ...h].slice(0, 50))
    setHistIdx(-1)
    setInput('')

    const parts = raw.split(' ')
    const cmd   = parts[0].toLowerCase()
    const rest  = parts.slice(1).join(' ')

    if (COMMANDS[cmd]) {
      await COMMANDS[cmd](rest)
    } else if (cmd === 'submit' && rest) {
      try {
        const r = await axios.post('/api/tasks/', { prompt: rest, priority: 3 })
        addLine('out', `Submitted: ${r.data.task_id}`)
        addLine('out', `  model: ${r.data.model}  category: ${r.data.category}`)
      } catch (e) {
        addLine('err', `Submit failed: ${e.response?.data?.detail || e.message}`)
      }
    } else {
      addLine('err', `Unknown command: ${cmd}. Type "help".`)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      const idx = Math.min(histIdx + 1, history.length - 1)
      setHistIdx(idx)
      setInput(history[idx] ?? '')
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const idx = Math.max(histIdx - 1, -1)
      setHistIdx(idx)
      setInput(idx === -1 ? '' : history[idx])
    }
  }

  const LINE_STYLE = {
    sys: 'text-t-or-dim',
    in:  'text-t-orange glow-dim',
    out: 'text-t-or-mid',
    err: 'text-red-500',
  }

  if (!open) {
    return (
      <div
        className="fixed bottom-0 right-0 left-44 border-t border-t-border bg-t-panel px-3 py-2 flex justify-between items-center cursor-pointer"
        onClick={() => setOpen(true)}
      >
        <span className="text-xs text-t-or-dim tracking-widest">▸ SHADOW TERMINAL</span>
        <span className="text-xs text-t-or-dim">[ EXPAND ]</span>
      </div>
    )
  }

  return (
    <div className="fixed bottom-0 right-0 left-44 h-40 flex flex-col border-t border-t-border bg-t-panel font-mono">
      {/* Header */}
      <div className="px-3 py-1.5 border-b border-t-border flex justify-between items-center shrink-0">
        <span className="text-xs text-t-or-mid tracking-widest">▸ SHADOW TERMINAL</span>
        <button
          onClick={() => setOpen(false)}
          className="text-xs text-t-or-dim hover:text-t-orange transition-colors"
        >
          [ COLLAPSE ]
        </button>
      </div>

      {/* Output area */}
      <div className="flex-1 overflow-y-auto px-3 py-1.5 space-y-0.5">
        {lines.map((l, i) => (
          <div key={i} className={`text-xs ${LINE_STYLE[l.type] || 'text-t-or-dim'}`}>
            {l.text}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {/* Input row */}
      <form
        onSubmit={handleSubmit}
        className="shrink-0 border-t border-t-border px-3 py-1.5 flex items-center gap-2"
        onClick={() => inputRef.current?.focus()}
      >
        <span className="text-t-orange text-xs shrink-0 glow-or">▸</span>
        <input
          ref={inputRef}
          className="term-input text-xs flex-1"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          autoComplete="off"
          spellCheck={false}
          placeholder="submit <prompt>  |  vram  |  tasks  |  help"
        />
        <span className="cursor text-t-orange text-xs">█</span>
      </form>
    </div>
  )
}

export default ShadowTerminal
