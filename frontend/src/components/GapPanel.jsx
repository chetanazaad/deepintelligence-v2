import React from 'react';

export default function GapPanel({ gaps }) {
  if (!gaps) {
    return (
      <div className="bg-surface-card border border-border rounded-xl p-4 text-center">
        <p className="text-text-secondary text-sm">No knowledge gaps identified.</p>
      </div>
    );
  }

  // If gaps is an array of strings (e.g. ['EVENT', 'CONCEPT'])
  const isArray = Array.isArray(gaps);
  const criticalGaps = isArray ? gaps.filter(g => g === 'EVENT' || g === 'ORGANIZATION') : gaps.critical || [];
  const moderateGaps = isArray ? gaps.filter(g => g === 'CONCEPT' || g === 'LOCATION') : gaps.moderate || [];
  const minorGaps = isArray ? gaps.filter(g => !['EVENT', 'ORGANIZATION', 'CONCEPT', 'LOCATION'].includes(g)) : gaps.minor || [];

  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
      <h3 className="text-sm font-bold text-text-primary border-b border-border pb-3">Knowledge Gaps</h3>
      
      <div className="space-y-3">
        {/* Critical Gaps */}
        {criticalGaps.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-[10px] font-bold text-red tracking-wider uppercase">🔴 Critical</span>
            <div className="space-y-1">
              {criticalGaps.map((gap, i) => (
                <div key={i} className="p-2.5 bg-red/5 border border-red/20 rounded text-xs text-red">
                  {typeof gap === 'string' ? gap : `${gap?.category || 'Unknown'}: ${gap?.reason || JSON.stringify(gap)}`} details missing or uncorroborated.
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Moderate Gaps */}
        {moderateGaps.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-[10px] font-bold text-amber tracking-wider uppercase">🟠 Moderate</span>
            <div className="space-y-1">
              {moderateGaps.map((gap, i) => (
                <div key={i} className="p-2.5 bg-amber/5 border border-amber/20 rounded text-xs text-amber">
                  {typeof gap === 'string' ? gap : `${gap?.category || 'Unknown'}: ${gap?.reason || JSON.stringify(gap)}`} relations unverified.
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Minor Gaps */}
        {minorGaps.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-[10px] font-bold text-green tracking-wider uppercase">🟢 Minor</span>
            <div className="space-y-1">
              {minorGaps.map((gap, i) => (
                <div key={i} className="p-2.5 bg-green/5 border border-green/20 rounded text-xs text-green">
                  {typeof gap === 'string' ? gap : `${gap?.category || 'Unknown'}: ${gap?.reason || JSON.stringify(gap)}`} context covered.
                </div>
              ))}
            </div>
          </div>
        )}

        {!isArray && criticalGaps.length === 0 && moderateGaps.length === 0 && minorGaps.length === 0 && (
          <p className="text-xs text-text-muted">No unresolved knowledge gaps found.</p>
        )}
      </div>
    </div>
  );
}
