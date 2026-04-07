import React, { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const MSG_COLOURS = {
  user:      'text-t-orange',
  assistant: 'text-t-or-mid',
  system:    'text-t-or-dim',
}

const Message = ({ role, content, streaming }) => (
  <div className="py-2 border-b border-t-border">
    <div className={`text-xs tracking-widest mb-1 ${MSG_COLOURS[role] || 'text-t-or-dim'}`}>
      {role.toUpperCase()}
    </div>
    <div className="text-xs text-t-or-mid leading-relaxed whitespace-pre-wrap font-mono">
      {content}
      {streaming && <span className="cursor text-t-orange ml-0.5">█</span>}
    </div>
  </div>
)

const DirectChat = () => {
  const [models,      setModels]      = useState([])
  const [selected,    setSelected]    = useState('')
  const [messages,    setMessages]    = useState([])
  const [input,       setInput]       = useState('')
  const [generating,  setGenerating]  = useState(false)
  const [streamText,  setStreamText]  = useState('')
  const bottomRef   = useRef(null)
  const inputRef    = useRef(null)
  const abortRef    = useRef(null)   // AbortController for fetch

  // Fetch available models
  useEffect(() => {
    axios.get('/api/chat/models').then(r => {
      setModels(r.data)
      if (r.data.length > 0) setSelected(r.data[0])
    }).catch(() => {})
  }, [])

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamText])

  const sendMessage = useCallback(async () => {
    if (!input.trim() || !selected || generating) return

    const prompt = input.trim()
    setInput('')
    setGenerating(true)
    setStreamText('')

    // Add user message
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(prev => [...prev, { role: 'user', content: prompt }])

    // SSE stream
    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const resp = await fetch(`/api/chat/${encodeURIComponent(selected)}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, history }),
        signal: ctrl.signal,
      })

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }

      const reader  = resp.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.done) {
              // Finalise
              setMessages(prev => [
                ...prev,
                { role: 'assistant', content: accumulated },
              ])
              setStreamText('')
              setGenerating(false)
              return
            }
            if (data.token) {
              accumulated += data.token
              setStreamText(accumulated)
            }
            if (data.error) {
              setMessages(prev => [
                ...prev,
                { role: 'system', content: `ERROR: ${data.error}` },
              ])
              setGenerating(false)
              setStreamText('')
              return
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages(prev => [
          ...prev,
          { role: 'system', content: `Connection error: ${err.message}` },
        ])
      }
      setGenerating(false)
      setStreamText('')
    }
  }, [input, selected, messages, generating])

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearChat = () => {
    if (generating) abortRef.current?.abort()
    setMessages([])
    setStreamText('')
    setGenerating(false)
  }

  const sendToQueue = async () => {
    // Take last user message and submit it as an orchestrated task
    const lastUser = [...messages].reverse().find(m => m.role === 'user')
    if (!lastUser) return
    try {
      const r = await axios.post('/api/tasks/', {
        prompt: lastUser.content,
        model: selected,
        priority: 3,
      })
      setMessages(prev => [
        ...prev,
        { role: 'system', content: `→ Queued as ${r.data.task_id} (${r.data.model})` },
      ])
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { role: 'system', content: `Queue error: ${e.response?.data?.detail || e.message}` },
      ])
    }
  }

  return (
    <div className="flex flex-col h-full font-mono">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="panel px-3 py-2 shrink-0 flex justify-between items-center">
        <span className="text-xs tracking-widest text-t-or-mid">DIRECT CHAT</span>
        <div className="flex items-center gap-3">
          {generating && (
            <span className="text-xs text-t-orange animate-pulse glow-or">
              ◉ GENERATING
            </span>
          )}
          <button
            onClick={clearChat}
            className="text-xs text-t-or-dim hover:text-t-orange border border-t-border px-2 py-0.5 transition-colors"
          >
            CLEAR
          </button>
        </div>
      </div>

      {/* ── Model selector ─────────────────────────────────────────────────── */}
      <div className="panel px-3 py-2 shrink-0 flex items-center gap-3 border-t border-t-border">
        <span className="text-xs text-t-or-dim tracking-widest shrink-0">MODEL:</span>
        {models.length === 0 ? (
          <span className="text-xs text-t-or-dim italic">No Ollama models found</span>
        ) : (
          <div className="flex gap-2 flex-wrap">
            {models.map(m => (
              <button
                key={m}
                onClick={() => setSelected(m)}
                className={`text-xs px-2 py-0.5 border transition-colors tracking-wide ${
                  selected === m
                    ? 'border-t-orange text-t-orange'
                    : 'border-t-border text-t-or-dim hover:border-t-or-mid hover:text-t-or-mid'
                }`}
              >
                {m.replace(/:latest$/, '')}
              </button>
            ))}
          </div>
        )}
        {messages.length > 0 && (
          <button
            onClick={sendToQueue}
            className="ml-auto text-xs text-t-or-dim hover:text-t-amber border border-t-border px-2 py-0.5 transition-colors shrink-0"
            title="Submit last prompt to orchestration queue"
          >
            → QUEUE
          </button>
        )}
      </div>

      {/* ── Message area ───────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto panel-bright px-3 pb-2">
        {messages.length === 0 && !generating ? (
          <div className="flex items-center justify-center h-full text-t-or-dim text-xs tracking-widest">
            TYPE A PROMPT BELOW<span className="cursor ml-1">█</span>
          </div>
        ) : (
          <>
            {messages.map((m, i) => (
              <Message key={i} role={m.role} content={m.content} />
            ))}
            {generating && streamText && (
              <Message role="assistant" content={streamText} streaming />
            )}
            {generating && !streamText && (
              <div className="py-2 text-xs text-t-or-dim animate-pulse">
                ◌ waiting for first token...
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ──────────────────────────────────────────────────────────── */}
      <div
        className="shrink-0 panel border-t border-t-border px-3 py-2 flex items-end gap-2"
        onClick={() => inputRef.current?.focus()}
      >
        <span className="text-t-orange text-xs shrink-0 glow-or pb-0.5">▸</span>
        <textarea
          ref={inputRef}
          className="term-input text-xs flex-1 resize-none leading-relaxed"
          rows={2}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Enter prompt… (Enter to send, Shift+Enter for newline)"
          disabled={generating || !selected}
        />
        <button
          onClick={sendMessage}
          disabled={generating || !input.trim() || !selected}
          className="shrink-0 text-xs border border-t-orange text-t-orange px-3 py-1 hover:bg-t-deep transition-colors disabled:border-t-border disabled:text-t-or-dim disabled:cursor-not-allowed"
        >
          SEND
        </button>
      </div>
    </div>
  )
}

export default DirectChat
