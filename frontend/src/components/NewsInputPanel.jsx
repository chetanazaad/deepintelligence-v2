import React, { useState } from 'react';

const PIPELINE_STEPS = [
  { key: 'ingestion', label: 'Ingestion', icon: '📥' },
  { key: 'preprocessing', label: 'Preprocessing', icon: '🧹' },
  { key: 'clustering', label: 'Clustering', icon: '🧩' },
  { key: 'timeline', label: 'Timeline', icon: '📅' },
  { key: 'expansion', label: 'Expansion', icon: '🔄' },
  { key: 'impact', label: 'Impact Analysis', icon: '💥' },
  { key: 'signals', label: 'Signal Detection', icon: '📡' },
  { key: 'assessment', label: 'Assessment', icon: '📊' },
  { key: 'llm', label: 'LLM Analysis', icon: '🤖' },
];

export default function NewsInputPanel({
  onAnalyze,
  isAnalyzing,
  pipelineSteps,
  llmStatus,
  processingTime,
  error,
}) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [useLlm, setUseLlm] = useState(true);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    onAnalyze(title.trim(), content.trim(), useLlm);
  };

  const canSubmit = title.trim().length >= 3 && content.trim().length >= 10 && !isAnalyzing;

  const getStepStatus = (stepKey) => {
    if (!pipelineSteps) return 'pending';
    const step = pipelineSteps[stepKey];
    if (!step) {
      // LLM is handled separately
      if (stepKey === 'llm') {
        if (llmStatus === 'completed') return 'ok';
        if (llmStatus === 'running') return 'running';
        if (llmStatus === 'failed') return 'error';
        if (llmStatus === 'disabled') return 'disabled';
        return 'pending';
      }
      return 'pending';
    }
    return step.status || 'pending';
  };

  return (
    <div className="input-panel">
      {/* Header */}
      <div className="panel-header">
        <div className="panel-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14.5 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7.5L14.5 2z" />
            <polyline points="14,2 14,8 20,8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10,9 9,9 8,9" />
          </svg>
        </div>
        <div>
          <h2 className="panel-title">Submit Intelligence</h2>
          <p className="panel-subtitle">Paste an article for analysis</p>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="input-form">
        <div className="form-group">
          <label htmlFor="news-title" className="form-label">Headline</label>
          <input
            id="news-title"
            type="text"
            placeholder="e.g. Iran invites Modi for official bilateral summit"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="form-input"
            disabled={isAnalyzing}
          />
        </div>

        <div className="form-group">
          <label htmlFor="news-content" className="form-label">Article Content</label>
          <textarea
            id="news-content"
            placeholder="Paste the full article text here..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="form-textarea"
            rows={12}
            disabled={isAnalyzing}
          />
        </div>

        <div className="form-options">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
              disabled={isAnalyzing}
            />
            <span className="toggle-text">
              {useLlm ? '🤖 LLM Augmentation ON' : '⚡ Deterministic Only'}
            </span>
          </label>
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="analyze-button"
        >
          {isAnalyzing ? (
            <>
              <span className="spinner" />
              Analyzing...
            </>
          ) : (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
              ANALYZE
            </>
          )}
        </button>
      </form>

      {/* Pipeline Progress */}
      {isAnalyzing && (
        <div className="pipeline-progress">
          <h3 className="progress-title">Pipeline Progress</h3>
          <div className="progress-steps">
            {PIPELINE_STEPS.map((step) => {
              const status = getStepStatus(step.key);
              return (
                <div key={step.key} className={`progress-step step-${status}`}>
                  <span className="step-indicator">
                    {status === 'ok' && '✓'}
                    {status === 'running' && <span className="spinner-sm" />}
                    {status === 'error' && '✗'}
                    {status === 'disabled' && '—'}
                    {status === 'pending' && '○'}
                  </span>
                  <span className="step-icon">{step.icon}</span>
                  <span className="step-label">{step.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Processing Time */}
      {processingTime != null && !isAnalyzing && (
        <div className="processing-time">
          ⚡ Completed in {processingTime}s
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="input-error">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
