function ImpactGroup({ title, icon, data, colorClass }) {
  if (!data) return null;
  const { direct_winners = [], indirect_winners = [], direct_losers = [], indirect_losers = [] } = data;
  const hasContent = direct_winners.length + indirect_winners.length + direct_losers.length + indirect_losers.length > 0;

  if (!hasContent) return null;

  return (
    <div className="p-4 rounded-xl bg-surface-card border border-border">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">{icon}</span>
        <h3 className="font-semibold text-text-primary text-sm">{title}</h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Winners */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-2 h-2 rounded-full bg-green" />
            <span className="text-xs font-semibold text-green uppercase tracking-wider">Winners</span>
          </div>
          {direct_winners.length > 0 && (
            <div className="mb-2">
              <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">Direct</span>
              <ul className="mt-1 space-y-1">
                {direct_winners.map((item, i) => (
                  <li key={i} className="text-xs text-text-secondary pl-3 border-l-2 border-green/30 py-0.5">{item}</li>
                ))}
              </ul>
            </div>
          )}
          {indirect_winners.length > 0 && (
            <div>
              <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">Indirect</span>
              <ul className="mt-1 space-y-1">
                {indirect_winners.map((item, i) => (
                  <li key={i} className="text-xs text-text-secondary pl-3 border-l-2 border-green/15 py-0.5 italic">{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Losers */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-2 h-2 rounded-full bg-red" />
            <span className="text-xs font-semibold text-red uppercase tracking-wider">Losers</span>
          </div>
          {direct_losers.length > 0 && (
            <div className="mb-2">
              <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">Direct</span>
              <ul className="mt-1 space-y-1">
                {direct_losers.map((item, i) => (
                  <li key={i} className="text-xs text-text-secondary pl-3 border-l-2 border-red/30 py-0.5">{item}</li>
                ))}
              </ul>
            </div>
          )}
          {indirect_losers.length > 0 && (
            <div>
              <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">Indirect</span>
              <ul className="mt-1 space-y-1">
                {indirect_losers.map((item, i) => (
                  <li key={i} className="text-xs text-text-secondary pl-3 border-l-2 border-red/15 py-0.5 italic">{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ImpactView({ impact }) {
  if (!impact || !impact.available) {
    return (
      <div className="text-center py-12 text-text-muted">
        <svg className="w-12 h-12 mx-auto mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
        </svg>
        <p className="text-sm">No impact analysis available</p>
      </div>
    );
  }

  const confidence = impact.confidence_score ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-bold text-text-primary">Impact Analysis</h2>
        <span className={`text-xs font-mono font-semibold px-2.5 py-1 rounded-full
          ${confidence >= 0.7 ? 'bg-green-bg text-green' :
            confidence >= 0.4 ? 'bg-amber-bg text-amber' : 'bg-red-bg text-red'}`}
        >
          {(confidence * 100).toFixed(0)}% confidence
        </span>
      </div>

      <ImpactGroup title="Short-Term Impact" icon="⚡" data={impact.short_term} />
      <ImpactGroup title="Long-Term Impact" icon="📈" data={impact.long_term} />

      {/* Sector impacts */}
      {impact.sector_impacts && impact.sector_impacts.length > 0 && (
        <div className="p-4 rounded-xl bg-surface-card border border-border">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">🏭</span>
            <h3 className="font-semibold text-text-primary text-sm">Sector-Specific</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {impact.sector_impacts.map((s, i) => (
              <span key={i} className="text-xs px-2.5 py-1 rounded-full bg-cyan-bg text-cyan border border-cyan/15">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
