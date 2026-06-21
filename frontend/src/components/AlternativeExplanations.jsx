import React, { useState } from 'react';

export default function AlternativeExplanations({ explanations }) {
  const [expandedIndex, setExpandedIndex] = useState(null);

  if (!explanations) {
    return (
      <div className="bg-surface-card border border-border rounded-xl p-4 text-center">
        <p className="text-text-secondary text-sm">No alternative explanations defined.</p>
      </div>
    );
  }

  // Handle both string format and list of objects format
  const explanationsList = Array.isArray(explanations)
    ? explanations
    : typeof explanations === 'string'
      ? [{ hypothesis: explanations, confidence: 50, details: 'Standard fallback explanation.' }]
      : Object.entries(explanations).map(([k, v]) => ({
          hypothesis: k,
          confidence: typeof v === 'number' ? v : 50,
          details: typeof v === 'string' ? v : 'No additional details.'
        }));

  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
      <h3 className="text-sm font-bold text-text-primary border-b border-border pb-3">Alternative Hypotheses</h3>

      <div className="space-y-2">
        {explanationsList.map((exp, idx) => {
          const isExpanded = expandedIndex === idx;
          const conf = exp.confidence || 50;
          return (
            <div key={idx} className="border border-border rounded-lg overflow-hidden">
              <div
                onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                className="flex items-center justify-between p-3 bg-surface-alt hover:bg-surface-hover transition-all cursor-pointer"
              >
                <span className="text-xs font-semibold text-text-primary">{exp.hypothesis}</span>
                <span className="text-xs font-bold text-accent">{conf}%</span>
              </div>
              {isExpanded && (
                <div className="p-3 bg-surface text-xs text-text-secondary border-t border-border leading-relaxed">
                  {exp.details || 'No expanded details provided for this scenario path.'}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
