export default function MetadataPanel({ metadata }) {
  if (!metadata) return null;

  const { confidence_summary, data_sources, last_updated } = metadata;

  return (
    <div className="p-4 rounded-xl bg-surface-card border border-border">
      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Intelligence Metadata</h3>

      <div className="grid grid-cols-3 gap-3">
        {/* Data Sources */}
        <div className="text-center p-3 rounded-lg bg-surface-alt">
          <div className="text-2xl font-bold text-accent">{data_sources ?? 0}</div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider mt-1">Sources</div>
        </div>

        {/* Confidence Avg */}
        {confidence_summary && confidence_summary.avg != null ? (
          <div className="text-center p-3 rounded-lg bg-surface-alt">
            <div className={`text-2xl font-bold font-mono ${
              confidence_summary.avg >= 0.7 ? 'text-green' :
              confidence_summary.avg >= 0.4 ? 'text-amber' : 'text-red'
            }`}>
              {(confidence_summary.avg * 100).toFixed(0)}%
            </div>
            <div className="text-[10px] text-text-muted uppercase tracking-wider mt-1">Avg Confidence</div>
          </div>
        ) : (
          <div className="text-center p-3 rounded-lg bg-surface-alt">
            <div className="text-2xl font-bold text-text-muted">—</div>
            <div className="text-[10px] text-text-muted uppercase tracking-wider mt-1">Confidence</div>
          </div>
        )}

        {/* Last Updated */}
        <div className="text-center p-3 rounded-lg bg-surface-alt">
          <div className="text-sm font-semibold text-text-primary mt-1">
            {last_updated ? new Date(last_updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}
          </div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider mt-1">Updated</div>
        </div>
      </div>

      {/* Confidence range bar */}
      {confidence_summary && confidence_summary.min != null && (
        <div className="mt-3 px-1">
          <div className="flex justify-between text-[10px] text-text-muted mb-1">
            <span>Min {(confidence_summary.min * 100).toFixed(0)}%</span>
            <span>{confidence_summary.data_points} data points</span>
            <span>Max {(confidence_summary.max * 100).toFixed(0)}%</span>
          </div>
          <div className="relative h-1.5 bg-surface-alt rounded-full overflow-hidden">
            <div
              className="absolute h-full bg-gradient-to-r from-red via-amber to-green rounded-full"
              style={{
                left: `${confidence_summary.min * 100}%`,
                width: `${(confidence_summary.max - confidence_summary.min) * 100}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
