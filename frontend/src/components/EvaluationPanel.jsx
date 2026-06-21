import React, { useState } from 'react';

export default function EvaluationPanel({ statusData }) {
  const [isOpen, setIsOpen] = useState(false);

  // Fallback defaults
  const {
    knowledge_density = 0.85,
    explanation_score = 0.92,
    goal_completion_rate = 0.76,
    loop_risk = 0.05,
    compression_ratio = 1.45,
    status = 'Optimal'
  } = statusData || {};

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-surface-alt border-t border-border shadow-2xl transition-all duration-300">
      {/* Toggle Bar */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between px-6 py-2.5 bg-surface-card hover:bg-surface-hover cursor-pointer border-b border-border/50"
      >
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-bold text-text-primary tracking-wider uppercase">System Health & Metrics</span>
        </div>
        <span className="text-xs text-text-muted">{isOpen ? '▼ COLLAPSE' : '▲ DEVELOPER PANEL'}</span>
      </div>

      {/* Expanded Metrics */}
      {isOpen && (
        <div className="p-6 grid grid-cols-2 md:grid-cols-5 gap-4 max-w-7xl mx-auto">
          <div className="p-4 bg-surface rounded-lg border border-border flex flex-col justify-between">
            <span className="text-[10px] text-text-secondary uppercase tracking-wider font-bold">Knowledge Density</span>
            <span className="text-xl font-bold text-text-primary mt-2">{Math.round(knowledge_density * 100)}%</span>
          </div>

          <div className="p-4 bg-surface rounded-lg border border-border flex flex-col justify-between">
            <span className="text-[10px] text-text-secondary uppercase tracking-wider font-bold">Explanation Score</span>
            <span className="text-xl font-bold text-accent mt-2">{Math.round(explanation_score * 100)}%</span>
          </div>

          <div className="p-4 bg-surface rounded-lg border border-border flex flex-col justify-between">
            <span className="text-[10px] text-text-secondary uppercase tracking-wider font-bold">Goal Completion</span>
            <span className="text-xl font-bold text-emerald-500 mt-2">{Math.round(goal_completion_rate * 100)}%</span>
          </div>

          <div className="p-4 bg-surface rounded-lg border border-border flex flex-col justify-between">
            <span className="text-[10px] text-text-secondary uppercase tracking-wider font-bold">Loop Risk</span>
            <span className="text-xl font-bold text-red mt-2">{Math.round(loop_risk * 100)}%</span>
          </div>

          <div className="p-4 bg-surface rounded-lg border border-border flex flex-col justify-between col-span-2 md:col-span-1">
            <span className="text-[10px] text-text-secondary uppercase tracking-wider font-bold">Compression Ratio</span>
            <span className="text-xl font-bold text-cyan mt-2">{compression_ratio.toFixed(2)}x</span>
          </div>
        </div>
      )}
    </div>
  );
}
