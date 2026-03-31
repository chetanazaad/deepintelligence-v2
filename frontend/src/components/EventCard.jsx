export default function EventCard({ event, isSelected, onClick }) {
  if (!event) return null;

  const confidence = event.confidence_score ?? 0;
  const confidenceColor =
    confidence >= 0.7 ? 'text-green' :
    confidence >= 0.4 ? 'text-amber' : 'text-red';

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-5 rounded-xl border transition-all duration-200 cursor-pointer group
        ${isSelected
          ? 'bg-accent/10 border-accent/40 shadow-lg shadow-accent/5'
          : 'bg-surface-card border-border hover:border-border-active hover:bg-surface-hover'
        }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-text-primary truncate text-base">
            {event.entity || 'Unknown Entity'}
          </h3>
          <span className="inline-block mt-1 px-2.5 py-0.5 text-xs font-medium rounded-full bg-accent/15 text-accent-hover">
            {event.event_type_label || event.event_type || 'Update'}
          </span>
        </div>
        {event.is_anchor && (
          <span className="shrink-0 px-2 py-0.5 text-xs font-bold rounded bg-cyan-bg text-cyan border border-cyan/20">
            ANCHOR
          </span>
        )}
      </div>

      {/* Description */}
      <p className="text-sm text-text-secondary leading-relaxed line-clamp-2 mb-3">
        {event.description || 'No description available.'}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>{event.timestamp ? new Date(event.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</span>
        <span className={`font-mono font-semibold ${confidenceColor}`}>
          {(confidence * 100).toFixed(0)}% confidence
        </span>
      </div>
    </button>
  );
}
