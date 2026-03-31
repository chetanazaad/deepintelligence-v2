export default function TimelineView({ timeline }) {
  if (!timeline || !timeline.entries || timeline.entries.length === 0) {
    return (
      <div className="text-center py-12 text-text-muted">
        <svg className="w-12 h-12 mx-auto mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-sm">No timeline data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-text-primary">Timeline</h2>
        <span className="text-xs text-text-muted bg-surface-hover px-2.5 py-1 rounded-full">
          {timeline.total_events} events
        </span>
      </div>

      <div className="relative pl-6">
        {/* Vertical line */}
        <div className="absolute left-[11px] top-2 bottom-2 w-px bg-gradient-to-b from-accent/60 via-border to-transparent" />

        {timeline.entries.map((entry, idx) => (
          <div key={entry.node_id || idx} className="relative pb-6 last:pb-0 group">
            {/* Dot */}
            <div className={`absolute left-[-17px] top-1.5 w-3 h-3 rounded-full border-2 transition-all
              ${entry.is_anchor
                ? 'bg-accent border-accent shadow-md shadow-accent/40 scale-125'
                : 'bg-surface-card border-border-active group-hover:border-accent group-hover:bg-accent/30'
              }`}
            />

            {/* Card */}
            <div className={`ml-4 p-4 rounded-lg border transition-all duration-200
              ${entry.is_anchor
                ? 'bg-accent/8 border-accent/25'
                : 'bg-surface-card border-border hover:border-border-active'
              }`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-mono text-text-muted">#{entry.position}</span>
                <span className={`px-2 py-0.5 text-xs font-medium rounded-full
                  ${entry.event_type === 'trigger' ? 'bg-amber-bg text-amber' :
                    entry.event_type === 'causal' ? 'bg-red-bg text-red' :
                    entry.event_type === 'reaction' ? 'bg-cyan-bg text-cyan' :
                    'bg-surface-hover text-text-secondary'
                  }`}
                >
                  {entry.event_label || entry.event_type || 'Update'}
                </span>
                {entry.is_anchor && (
                  <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-accent/20 text-accent-hover tracking-wider">ANCHOR</span>
                )}
              </div>

              <p className="text-sm text-text-primary leading-relaxed mb-2">
                {entry.description || 'No description'}
              </p>

              <div className="flex items-center justify-between">
                <span className="text-xs text-text-muted">
                  {entry.timestamp ? new Date(entry.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                </span>

                {/* Causal connections */}
                {entry.causal_connections && entry.causal_connections.length > 0 && (
                  <div className="flex gap-1.5">
                    {entry.causal_connections.map((conn, ci) => (
                      <span key={ci} className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-full bg-surface-hover text-text-secondary border border-border">
                        <span className={
                          conn.relation === 'causes' ? 'text-red' :
                          conn.relation === 'triggers' ? 'text-amber' :
                          conn.relation === 'reacts_to' ? 'text-cyan' : 'text-text-muted'
                        }>→</span>
                        {conn.relation}
                        <span className="font-mono text-text-muted">{((conn.confidence || 0) * 100).toFixed(0)}%</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
