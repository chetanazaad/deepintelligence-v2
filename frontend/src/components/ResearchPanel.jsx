import React from 'react';

export default function ResearchPanel({
  leads = [],
  onExpandNode,
  onResearchNode,
  onViewRelationships
}) {
  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
      <h3 className="text-sm font-bold text-text-primary border-b border-border pb-3">Research Leads</h3>

      <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
        {leads.length === 0 ? (
          <p className="text-xs text-text-muted text-center py-6">No research leads currently queued.</p>
        ) : (
          leads.map((lead) => (
            <div key={lead.id} className="p-3 bg-surface-alt border border-border rounded-lg space-y-2">
              <div className="flex justify-between items-start gap-2">
                <div>
                  <p className="text-xs font-semibold text-text-primary">{lead.entity || `Lead #${lead.id}`}</p>
                  <p className="text-[10px] text-text-muted">Type: {lead.entity_type || 'Unknown'}</p>
                </div>
                <span className="text-[9px] px-2 py-0.5 bg-accent/10 border border-accent/20 text-accent-hover rounded font-bold uppercase">
                  Prio: {lead.priority || 1}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[10px] text-text-secondary border-t border-border pt-2">
                <div>Novelty: <span className="text-text-primary font-medium">{lead.novelty ? `${Math.round(lead.novelty * 100)}%` : 'N/A'}</span></div>
                <div>Contribution: <span className="text-text-primary font-medium">{lead.contribution ? `${Math.round(lead.contribution * 100)}%` : 'N/A'}</span></div>
              </div>

              <div className="flex gap-1.5 justify-end pt-1.5 border-t border-border/50">
                {onExpandNode && (
                  <button
                    onClick={() => onExpandNode(lead.id)}
                    className="text-[9px] font-medium bg-surface px-2 py-0.5 border border-border rounded text-text-secondary hover:text-text-primary"
                  >
                    Expand
                  </button>
                )}
                {onResearchNode && (
                  <button
                    onClick={() => onResearchNode(lead.id)}
                    className="text-[9px] font-medium bg-accent/10 text-accent-hover px-2 py-0.5 border border-accent/20 rounded hover:bg-accent/20"
                  >
                    Research
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
