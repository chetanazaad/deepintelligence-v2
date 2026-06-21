import React from 'react';

export default function EvidencePanel({ evidenceSummary }) {
  if (!evidenceSummary) {
    return (
      <div className="bg-surface-card border border-border rounded-xl p-4 text-center">
        <p className="text-text-secondary text-sm">No evidence details available.</p>
      </div>
    );
  }

  const {
    total_claims = 0,
    sources_count = 0,
    categories = [],
    items = [] // Support both summary fields and lists
  } = evidenceSummary;

  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <h3 className="text-sm font-bold text-text-primary tracking-tight">Supporting Evidence</h3>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-1 bg-surface-alt border border-border rounded text-text-secondary">
            Claims: <strong className="text-text-primary">{total_claims}</strong>
          </span>
          <span className="text-xs px-2 py-1 bg-surface-alt border border-border rounded text-text-secondary">
            Sources: <strong className="text-text-primary">{sources_count}</strong>
          </span>
        </div>
      </div>

      {categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {categories.map((cat, i) => (
            <span key={i} className="text-xs bg-accent/10 border border-accent/20 text-accent-hover px-2.5 py-1 rounded-full">
              ✓ {cat}
            </span>
          ))}
        </div>
      )}

      {items && items.length > 0 ? (
        <div className="space-y-2 mt-3">
          {items.map((item, idx) => (
            <div key={idx} className="p-3 bg-surface-alt border border-border rounded-lg flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-text-primary">{item.claim}</p>
                <p className="text-xs text-text-muted">{item.category}</p>
              </div>
              <span className="text-xs text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded">
                {item.confidence}%
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-muted">
          All collected evidence matches active goals across target categories.
        </p>
      )}
    </div>
  );
}
