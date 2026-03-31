const STRENGTH_STYLES = {
  STRONG: { bg: 'bg-red-bg', text: 'text-red', border: 'border-red/20', label: 'Strong' },
  MEDIUM: { bg: 'bg-amber-bg', text: 'text-amber', border: 'border-amber/20', label: 'Medium' },
  WEAK:   { bg: 'bg-surface-hover', text: 'text-text-secondary', border: 'border-border', label: 'Weak' },
};

const TYPE_ICONS = {
  risk: '⚠️',
  opportunity: '💡',
  transition: '🔄',
};

export default function SignalView({ signals }) {
  if (!signals || !signals.items || signals.items.length === 0) {
    return (
      <div className="text-center py-12 text-text-muted">
        <svg className="w-12 h-12 mx-auto mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.808-3.808-9.98 0-13.789m13.788 0c3.808 3.808 3.808 9.981 0 13.79M12 12h.008v.007H12V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
        </svg>
        <p className="text-sm">No signals detected</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-bold text-text-primary">Early-Warning Signals</h2>
        <span className="text-xs text-text-muted bg-surface-hover px-2.5 py-1 rounded-full">
          {signals.count} signals
        </span>
      </div>

      {signals.items.map((signal, i) => {
        const style = STRENGTH_STYLES[signal.strength] || STRENGTH_STYLES.WEAK;
        const icon = TYPE_ICONS[signal.signal_type] || '📡';
        const confidence = signal.confidence_score ?? 0;

        return (
          <div key={i} className={`p-4 rounded-xl border ${style.border} ${style.bg} transition-all hover:shadow-md`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="text-lg">{icon}</span>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-semibold ${style.text}`}>{signal.keyword || '—'}</span>
                    <span className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full ${style.bg} ${style.text} border ${style.border}`}>
                      {style.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-text-muted">
                    <span className="capitalize">{signal.signal_type || 'unknown'}</span>
                    {signal.entity && <span>• {signal.entity}</span>}
                    {signal.source_count != null && <span>• {signal.source_count} sources</span>}
                  </div>
                </div>
              </div>

              <div className="text-right shrink-0">
                <div className={`text-sm font-mono font-semibold ${
                  confidence >= 0.6 ? 'text-red' :
                  confidence >= 0.35 ? 'text-amber' : 'text-text-muted'
                }`}>
                  {(confidence * 100).toFixed(0)}%
                </div>
                {signal.time_span && signal.time_span !== 'unknown' && (
                  <div className="text-[10px] text-text-muted mt-0.5">{signal.time_span}</div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
