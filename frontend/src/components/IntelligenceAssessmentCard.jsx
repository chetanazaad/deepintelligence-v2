import React from 'react';

export default function IntelligenceAssessmentCard({ assessment, goalQuestion }) {
  if (!assessment) {
    return (
      <div className="bg-surface-card border border-border rounded-xl p-6 text-center">
        <p className="text-text-secondary text-sm">No intelligence assessment available for this goal.</p>
      </div>
    );
  }

  const {
    confidence_score = 0,
    confidence_level = 'LOW',
    executive_summary = '',
    assessment_text = '',
    generated_at = '',
    version = 1,
    status = 'draft'
  } = assessment;

  // Confidence color styling
  let confColor = 'text-red-500 bg-red-500/10 border-red-500/20';
  if (confidence_score >= 70) {
    confColor = 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
  } else if (confidence_score >= 40) {
    confColor = 'text-amber-500 bg-amber-500/10 border-amber-500/20';
  }

  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="text-[10px] font-bold text-accent tracking-widest uppercase">
            Intelligence Assessment v{version} ({status})
          </span>
          <h2 className="text-xl font-bold text-text-primary mt-1">{goalQuestion}</h2>
        </div>
        <div className={`flex flex-col items-center px-4 py-2 border rounded-lg ${confColor}`}>
          <span className="text-xs font-semibold tracking-wider">{confidence_level}</span>
          <span className="text-lg font-bold">{Math.round(confidence_score)}%</span>
        </div>
      </div>

      {executive_summary && (
        <div className="p-4 bg-surface-alt rounded-lg border border-border">
          <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-2">Executive Summary</h3>
          <p className="text-sm text-text-secondary leading-relaxed">{executive_summary}</p>
        </div>
      )}

      <div className="space-y-3">
        <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider">Detailed Analysis</h3>
        <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">{assessment_text}</p>
      </div>

      {generated_at && (
        <div className="text-[10px] text-text-muted pt-2 border-t border-border flex justify-between">
          <span>Generated At: {new Date(generated_at).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}
