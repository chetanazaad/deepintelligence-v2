import React, { useState } from 'react';

export default function IntelligenceReport({
  assessment,
  stats,
  llmStatus,
  llmError,
}) {
  const [activeScenarioTab, setActiveScenarioTab] = useState(0);

  if (!assessment) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8 bg-surface-card rounded-xl border border-border">
        <div className="w-16 h-16 rounded-full bg-surface/50 flex items-center justify-center mb-4 text-text-muted">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
            <polyline points="3.27,6.96 12,12.01 20.73,6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
        </div>
        <h3 className="text-lg font-bold text-text-primary mb-2">Awaiting Ingestion</h3>
        <p className="text-sm text-text-secondary max-w-sm">
          Submit a news article in the left panel to begin the automated intelligence pipeline.
        </p>
      </div>
    );
  }

  const final = assessment.final || {};
  const isLlmRunning = llmStatus === 'running' || llmStatus === 'pending';
  const isLlmFailed = llmStatus === 'failed';
  const isLlmSuccess = llmStatus === 'completed' || final.source === 'llm';

  // Extract values with sensible defaults
  const confidence = final.confidence || '0% LOW';
  const summary = final.executive_summary || '';
  const detailedAssessment = final.assessment || '';
  const risks = Array.isArray(final.risks) ? final.risks : [];
  const opportunities = Array.isArray(final.opportunities) ? final.opportunities : [];
  const alternatives = Array.isArray(final.alternative_explanations) ? final.alternative_explanations : [];
  const scenarios = Array.isArray(final.future_scenarios) ? final.future_scenarios : [];
  const gaps = Array.isArray(final.knowledge_gaps) ? final.knowledge_gaps : [];
  const entities = Array.isArray(final.key_entities) ? final.key_entities : [];
  const recommendations = Array.isArray(final.recommendations) ? final.recommendations : [];

  return (
    <div className="space-y-6">
      {/* Top Banner / Status */}
      <div className="bg-surface-card border border-border rounded-xl p-6 relative overflow-hidden">
        {/* Glow decoration */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-3xl -mr-16 -mt-16 pointer-events-none" />

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold tracking-wider text-text-muted uppercase">Intelligence Status</span>
              {isLlmRunning && (
                <span className="px-2 py-0.5 text-[10px] font-bold bg-amber-bg text-amber border border-amber/20 rounded-full animate-pulse flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-amber rounded-full animate-ping" />
                  Generating LLM Augmentation...
                </span>
              )}
              {isLlmSuccess && (
                <span className="px-2 py-0.5 text-[10px] font-bold bg-green-bg text-green border border-green/20 rounded-full">
                  🤖 LLM Enhanced
                </span>
              )}
              {!isLlmRunning && !isLlmSuccess && (
                <span className="px-2 py-0.5 text-[10px] font-bold bg-cyan-bg text-cyan border border-cyan/20 rounded-full">
                  ⚡ Deterministic Only
                </span>
              )}
            </div>
            <h2 className="text-xl font-extrabold text-text-primary tracking-tight">Intelligence Report</h2>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <span className="block text-[10px] font-bold text-text-muted uppercase tracking-wider">Confidence Level</span>
              <span className="text-lg font-black text-accent">{confidence}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Report Body */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 columns: Summary, Assessment, Scenarios */}
        <div className="lg:col-span-2 space-y-6">
          {/* Executive Summary */}
          {summary && (
            <div className="bg-surface-card border border-border rounded-xl p-6">
              <h3 className="text-sm font-bold text-text-muted uppercase tracking-wider mb-3">Executive Summary</h3>
              <p className="text-text-primary text-sm leading-relaxed whitespace-pre-wrap">{summary}</p>
            </div>
          )}

          {/* Detailed Assessment */}
          {detailedAssessment && (
            <div className="bg-surface-card border border-border rounded-xl p-6">
              <h3 className="text-sm font-bold text-text-muted uppercase tracking-wider mb-3">Detailed Intelligence Analysis</h3>
              <div className="text-text-primary text-sm leading-relaxed whitespace-pre-wrap prose prose-invert max-w-none">
                {detailedAssessment}
              </div>
            </div>
          )}

          {/* Future Scenarios */}
          {scenarios.length > 0 && (
            <div className="bg-surface-card border border-border rounded-xl p-6">
              <h3 className="text-sm font-bold text-text-muted uppercase tracking-wider mb-4">Future Scenarios</h3>
              
              {/* Tab headers */}
              <div className="flex border-b border-border mb-4">
                {['Likely', 'Possible', 'Unlikely'].map((tabLabel, idx) => (
                  <button
                    key={tabLabel}
                    type="button"
                    onClick={() => setActiveScenarioTab(idx)}
                    className={`px-4 py-2 text-xs font-bold border-b-2 transition-all cursor-pointer ${
                      activeScenarioTab === idx
                        ? 'border-accent text-accent'
                        : 'border-transparent text-text-muted hover:text-text-secondary'
                    }`}
                  >
                    {tabLabel.toUpperCase()}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="text-text-primary text-sm leading-relaxed p-2 bg-surface/30 rounded-lg min-h-[80px]">
                {scenarios[activeScenarioTab] ? (
                  <p className="whitespace-pre-wrap">{scenarios[activeScenarioTab]}</p>
                ) : (
                  <span className="text-text-muted italic">No scenario data available for this category.</span>
                )}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div className="bg-surface-card border border-border rounded-xl p-6">
              <h3 className="text-sm font-bold text-text-muted uppercase tracking-wider mb-3">Recommendations</h3>
              <ul className="space-y-3">
                {recommendations.map((rec, i) => (
                  <li key={i} className="flex gap-3 text-sm text-text-primary">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-accent/15 text-accent text-xs font-bold flex items-center justify-center">
                      {i + 1}
                    </span>
                    <span className="leading-relaxed">{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Right 1 column: Risks/Opportunities, Gaps, Alternative Hypotheses */}
        <div className="space-y-6">
          {/* Risks & Opportunities */}
          {(risks.length > 0 || opportunities.length > 0) && (
            <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
              {risks.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-red uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-red animate-pulse" />
                    Key Risks
                  </h3>
                  <ul className="space-y-1.5">
                    {risks.map((risk, idx) => (
                      <li key={idx} className="text-xs text-text-primary list-disc list-inside leading-relaxed pl-1">
                        {risk}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {opportunities.length > 0 && (
                <div className="pt-2 border-t border-border/50">
                  <h3 className="text-xs font-bold text-green uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-green" />
                    Opportunities
                  </h3>
                  <ul className="space-y-1.5">
                    {opportunities.map((opp, idx) => (
                      <li key={idx} className="text-xs text-text-primary list-disc list-inside leading-relaxed pl-1">
                        {opp}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Key Entities */}
          {entities.length > 0 && (
            <div className="bg-surface-card border border-border rounded-xl p-6">
              <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">Key Entities</h3>
              <div className="flex flex-wrap gap-1.5">
                {entities.map((ent, idx) => (
                  <span key={idx} className="px-2 py-1 bg-surface rounded text-xs text-cyan border border-cyan/15 font-mono">
                    {ent}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Alternative Explanations */}
          {alternatives.length > 0 && (
            <div className="bg-surface-card border border-border rounded-xl p-6">
              <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">Alternative Explanations</h3>
              <div className="space-y-3">
                {alternatives.map((alt, idx) => (
                  <div key={idx} className="p-3 bg-surface/50 rounded-lg border border-border/50 text-xs">
                    <p className="text-text-primary leading-relaxed mb-1">{alt}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Knowledge Gaps */}
          {gaps.length > 0 && (
            <div className="bg-surface-card border border-border rounded-xl p-6">
              <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">Knowledge Gaps</h3>
              <div className="space-y-2">
                {gaps.map((gap, idx) => (
                  <div key={idx} className="p-3 bg-surface/50 rounded-lg border border-border/50 text-xs">
                    <p className="text-text-primary font-medium">{gap}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Stats Footer */}
      {stats && (
        <div className="p-4 bg-surface-alt border border-border rounded-xl flex flex-wrap items-center justify-between gap-4 text-xs text-text-muted">
          <div className="flex flex-wrap gap-4">
            <span>New Nodes: <strong className="text-text-secondary">{stats.nodes_created}</strong></span>
            <span>Reused Knowledge: <strong className="text-text-secondary">{stats.nodes_existing ?? 0}</strong></span>
            <span>New Relationships: <strong className="text-text-secondary">{stats.edges_created}</strong></span>
            <span>Signals Detected: <strong className="text-text-secondary">{stats.signals_detected}</strong></span>
          </div>
          <div>
            <span>Pipeline Executed in <strong className="text-text-secondary">{stats.processing_time}s</strong></span>
          </div>
        </div>
      )}
    </div>
  );
}
