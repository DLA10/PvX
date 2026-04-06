import React from 'react'

// Read-only retro config viewer — edits require pvx.config.yaml on disk
const Config = () => (
  <div className="font-mono p-4 space-y-4">
    <div className="panel-bright px-3 py-3">
      <div className="text-xs text-t-or-mid tracking-widest border-b border-t-border pb-1 mb-3 uppercase">
        ▸ Configuration
      </div>
      <p className="text-xs text-t-or-dim leading-relaxed">
        Edit <span className="text-t-orange">pvx.config.yaml</span> in your
        working directory, then restart PvX.<br /><br />
        Run <span className="text-t-orange">pvx doctor</span> to validate your
        config before starting.
      </p>
    </div>

    <div className="panel px-3 py-3">
      <div className="text-xs text-t-or-mid tracking-widest border-b border-t-border pb-1 mb-3 uppercase">
        ▸ Quick Reference
      </div>
      <div className="text-xs text-t-or-dim space-y-1.5">
        {[
          ['pvx init',   'Create pvx.config.yaml'],
          ['pvx doctor', 'Validate config + GPU'],
          ['pvx start',  'Start API + MCP servers'],
          ['pvx stop',   'Graceful shutdown'],
        ].map(([cmd, desc]) => (
          <div key={cmd} className="flex gap-3">
            <span className="text-t-orange w-24 shrink-0">{cmd}</span>
            <span>{desc}</span>
          </div>
        ))}
      </div>
    </div>

    <div className="panel px-3 py-2 text-xs text-t-or-dim">
      API docs: <a
        href="http://localhost:8000/docs"
        target="_blank"
        rel="noreferrer"
        className="text-t-orange hover:glow-or transition-colors"
      >localhost:8000/docs</a>
    </div>
  </div>
)

export default Config
