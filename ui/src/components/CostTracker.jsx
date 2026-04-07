import React, { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

const fmtTokens = (n) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n ?? 0)
const fmtUsd    = (n) => `$${(n ?? 0).toFixed(4)}`

const SectionHeader = ({ children }) => (
  <div className="text-xs tracking-widest text-t-or-mid border-b border-t-border pb-1 mb-2 uppercase">
    {children}
  </div>
)

const Row = ({ label, value, sub, colour = 'text-t-orange' }) => (
  <div className="flex items-baseline justify-between py-0.5">
    <span className="text-t-or-dim text-xs tracking-wide">{label}</span>
    <span className={`text-sm font-bold ${colour}`}>
      {value}
      {sub && <span className="text-t-or-dim text-xs ml-1 font-normal">{sub}</span>}
    </span>
  </div>
)

const CostTracker = () => {
  const [stats,   setStats]   = useState(null)
  const [online,  setOnline]  = useState(false)
  const [updated, setUpdated] = useState(null)

  const fetchStats = useCallback(async () => {
    try {
      const r = await axios.get('/api/stats/session')
      setStats(r.data)
      setOnline(true)
      setUpdated(new Date())
    } catch {
      setOnline(false)
    }
  }, [])

  useEffect(() => {
    fetchStats()
    const id = setInterval(fetchStats, 3000)
    return () => clearInterval(id)
  }, [fetchStats])

  const totalTokens = stats?.total_tokens ?? 0
  const gpt4oUsd    = stats?.gpt4o_equivalent_usd ?? 0
  const savings     = stats?.savings_pct ?? 100
  const compressions = stats?.compressions ?? 0
  const tokensPerModel = stats?.tokens_per_model ?? {}
  const tasksPerModel  = stats?.tasks_per_model ?? {}
  const updStr = updated
    ? updated.toLocaleTimeString('en-GB', { hour12: false })
    : '——:——:——'

  return (
    <div className="flex flex-col gap-3 font-mono p-3">

      {/* Header */}
      <div className="panel px-3 py-2 flex justify-between items-center">
        <span className="text-xs tracking-widest text-t-or-mid">COST TRACKER</span>
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${online ? 'bg-t-orange animate-pulse' : 'bg-red-900'}`} />
          <span className="text-xs text-t-or-dim">{online ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </div>

      {/* Per-model breakdown */}
      <div className="panel-bright px-3 py-3">
        <SectionHeader>▸ PER MODEL — THIS SESSION</SectionHeader>

        {/* Column headers */}
        <div className="flex gap-2 text-xs text-t-or-dim tracking-widest mb-2 border-b border-t-border pb-1">
          <span className="flex-1">MODEL</span>
          <span className="w-14 text-right">TOKENS</span>
          <span className="w-10 text-right">TASKS</span>
          <span className="w-14 text-right">COST</span>
        </div>

        {/* Model rows */}
        {Object.keys(tokensPerModel).length === 0 ? (
          <div className="text-xs text-t-or-dim italic py-2">
            No tasks completed yet<span className="cursor ml-1">█</span>
          </div>
        ) : (
          Object.entries(tokensPerModel).map(([model, toks]) => {
            const modelCost = toks * 0.000005  // GPT-4o blended average
            return (
              <div key={model} className="flex gap-2 text-xs py-1 border-b border-t-border last:border-0">
                <span className="flex-1 text-t-orange truncate">
                  {model.replace(/:latest$/, '')}
                </span>
                <span className="w-14 text-right text-t-or-mid">{fmtTokens(toks)}</span>
                <span className="w-10 text-right text-t-or-dim">
                  {tasksPerModel[model] ?? 0}
                </span>
                <span className="w-14 text-right text-t-or-dim">{fmtUsd(modelCost)}</span>
              </div>
            )
          })
        )}

        {/* Claude row (always show — it's subscription, $0 marginal) */}
        <div className="flex gap-2 text-xs py-1 border-t border-t-border mt-1">
          <span className="flex-1 text-t-or-dim">claude (cli)</span>
          <span className="w-14 text-right text-t-or-dim">—</span>
          <span className="w-10 text-right text-t-or-dim">
            {tasksPerModel['claude'] ?? 0}
          </span>
          <span className="w-14 text-right text-t-or-dim">sub</span>
        </div>
      </div>

      {/* Totals */}
      <div className="panel-bright px-3 py-3">
        <SectionHeader>▸ SESSION TOTALS</SectionHeader>

        <Row
          label="TOTAL TOKENS"
          value={fmtTokens(totalTokens)}
          colour="text-t-orange"
        />
        <Row
          label="ACTUAL COST"
          value="$0.00"
          sub="(local inference)"
          colour="text-t-or-dim"
        />

        <div className="border-t border-t-border my-2" />

        <Row
          label="GPT-4o EQUIV"
          value={fmtUsd(gpt4oUsd)}
          colour="text-t-amber"
        />
        <div className="mt-2">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-t-or-dim tracking-widest">SAVINGS</span>
            <span className="text-t-orange font-bold glow-or">{savings.toFixed(1)}%</span>
          </div>
          {/* Savings bar */}
          <div className="text-sm font-bold leading-none tracking-tight">
            <span className="bar-fill">{'█'.repeat(Math.round(savings / 100 * 18))}</span>
            <span className="bar-empty">{'░'.repeat(18 - Math.round(savings / 100 * 18))}</span>
          </div>
        </div>
      </div>

      {/* Context compressions */}
      <div className="panel px-3 py-3">
        <SectionHeader>▸ CONTEXT MANAGEMENT</SectionHeader>
        <Row
          label="COMPRESSIONS"
          value={compressions}
          colour={compressions > 0 ? 'text-t-amber' : 'text-t-or-dim'}
        />
        <div className="mt-2 text-xs text-t-or-dim leading-relaxed">
          Compression runs when context exceeds 70% of model limit.
          Uses local Qwen-3B — zero API cost.
        </div>
      </div>

      {/* Pricing reference */}
      <div className="panel px-3 py-2">
        <SectionHeader>▸ PRICING REFERENCE</SectionHeader>
        <div className="text-xs text-t-or-dim space-y-0.5">
          <div className="flex justify-between">
            <span>Local (Ollama)</span>
            <span className="text-t-orange">$0.00</span>
          </div>
          <div className="flex justify-between">
            <span>Claude (Pro sub)</span>
            <span className="text-t-or-dim">$0.00 marginal</span>
          </div>
          <div className="flex justify-between">
            <span>GPT-4o equiv</span>
            <span className="text-t-amber">$5/1M in · $15/1M out</span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="panel px-3 py-2 text-xs text-t-or-dim flex justify-between">
        <span>SYNC: {updStr}</span>
        <span>3s POLL</span>
      </div>
    </div>
  )
}

export default CostTracker
