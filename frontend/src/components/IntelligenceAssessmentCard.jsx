import React, { useState } from 'react';

export default function IntelligenceAssessmentCard({ assessment, llmAssessment, goalQuestion }) {
  const [activeView, setActiveView] = useState('deterministic'); // 'deterministic' | 'llm'

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
      {/* Header */}
      <div className="flex items-start justify-between gap-4 border-b border-border pb-4">
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

      {/* View Selector Toggle */}
      <div className="flex gap-2 p-1 bg-surface-alt rounded-lg border border-border">
        <button
          onClick={() => setActiveView('deterministic')}
          className={`flex-1 text-center py-1.5 text-xs font-bold rounded transition-all cursor-pointer
            ${activeView === 'deterministic'
              ? 'bg-surface-card text-accent'
              : 'text-text-muted hover:text-text-secondary'
            }`}
        >
          💼 DETERMINISTIC WORKSPACE
        </button>
        <button
          onClick={() => setActiveView('llm')}
          className={`flex-1 text-center py-1.5 text-xs font-bold rounded transition-all cursor-pointer
            ${activeView === 'llm'
              ? 'bg-surface-card text-accent'
              : 'text-text-muted hover:text-text-secondary'
            }`}
        >
          🤖 LLM AUGMENTATION LAYER
        </button>
      </div>

      {/* Render selected view */}
      {activeView === 'deterministic' ? (
        <div className="space-y-6">
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
        </div>
      ) : (
        <div className="space-y-6">
          {llmAssessment ? (
            <div className="space-y-4">
              {/* LLM Metadata stats */}
              <div className="grid grid-cols-3 gap-2 p-3 bg-surface-alt rounded-lg border border-border text-[10px] text-text-secondary">
                <div>Model: <strong className="text-text-primary">{llmAssessment.model}</strong></div>
                <div>Latency: <strong className="text-text-primary">{llmAssessment.latency}s</strong></div>
                <div>Tokens (I/O): <strong className="text-text-primary">{llmAssessment.input_tokens}/{llmAssessment.output_tokens}</strong></div>
              </div>

              <div className="space-y-3">
                <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider">Augmented Detailed Analysis</h3>
                <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">{llmAssessment.response}</p>
              </div>
            </div>
          ) : (
            <div className="p-6 bg-surface-alt rounded-lg border border-border text-center">
              <p className="text-xs text-text-secondary">No LLM augmented assessment generated for this version.</p>
            </div>
          )}
        </div>
      )}

      {generated_at && (
        <div className="text-[10px] text-text-muted pt-2 border-t border-border flex justify-between">
          <span>Generated At: {new Date(generated_at).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}
