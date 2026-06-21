import React, { useState, useEffect } from 'react';
import axios from 'axios';

export default function ValidationDashboard() {
  const [readiness, setReadiness] = useState(null);
  const [failures, setFailures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [benchmarking, setBenchmarking] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // Human Review Form State
  const [reviewForm, setReviewForm] = useState({
    assessmentId: '',
    analystName: '',
    usefulness: 5,
    correctness: 5,
    confidence: 5,
    explanation: 5,
    notes: ''
  });
  const [reviewMsg, setReviewMsg] = useState('');

  const loadValidationData = async () => {
    setLoading(true);
    try {
      const readRes = await axios.get('/api/validation/readiness');
      setReadiness(readRes.data);

      const failRes = await axios.get('/api/validation/failures');
      setFailures(failRes.data);
    } catch (err) {
      console.error('Failed to load validation dashboard data:', err);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadValidationData();
  }, []);

  const handleBenchmark = async (numItems) => {
    setBenchmarking(true);
    setTestResult(null);
    try {
      const res = await axios.post(`/api/validation/benchmark?num_items=${numItems}`);
      setTestResult(res.data);
      // Reload readiness/failures
      loadValidationData();
    } catch (err) {
      console.error('Benchmark failed:', err);
    }
    setBenchmarking(false);
  };

  const handleReviewSubmit = async (e) => {
    e.preventDefault();
    setReviewMsg('');
    try {
      await axios.post('/api/validation/review', {
        assessment_id: parseInt(reviewForm.assessmentId),
        analyst_name: reviewForm.analystName,
        usefulness_score: reviewForm.usefulness,
        correctness_score: reviewForm.correctness,
        confidence_score: reviewForm.confidence,
        explanation_score: reviewForm.explanation,
        analyst_notes: reviewForm.notes
      });
      setReviewMsg('✓ Feedback submitted successfully.');
      setReviewForm({
        assessmentId: '',
        analystName: '',
        usefulness: 5,
        correctness: 5,
        confidence: 5,
        explanation: 5,
        notes: ''
      });
    } catch (err) {
      setReviewMsg('⚠️ Failed to submit feedback. Check assessment ID.');
    }
  };

  const getReadinessBg = (classification) => {
    switch (classification) {
      case 'PRODUCTION_READY': return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
      case 'STABLE': return 'text-cyan bg-cyan/10 border-cyan/20';
      case 'LEARNING': return 'text-amber-500 bg-amber-500/10 border-amber-500/20';
      default: return 'text-red-500 bg-red-500/10 border-red-500/20';
    }
  };

  return (
    <div className="bg-surface border border-border rounded-xl p-6 space-y-6 max-w-7xl mx-auto">
      {/* Title */}
      <div className="flex justify-between items-center border-b border-border pb-4">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Intelligence Quality & Validation</h2>
          <p className="text-xs text-text-muted">Real-time heuristics audit & system readiness scorecard</p>
        </div>
        <button
          onClick={loadValidationData}
          disabled={loading}
          className="text-xs bg-surface-card border border-border px-3 py-1.5 rounded hover:border-accent transition-all text-text-secondary cursor-pointer"
        >
          {loading ? 'Refreshing...' : '🔄 REFRESH'}
        </button>
      </div>

      {/* Main Readiness Display */}
      {readiness && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="md:col-span-1 p-6 bg-surface-card border border-border rounded-xl flex flex-col justify-between items-center text-center space-y-4">
            <span className="text-xs font-bold text-text-secondary uppercase tracking-wider">System Readiness</span>
            <div className="relative flex items-center justify-center">
              <span className="text-3xl font-extrabold text-text-primary">{readiness.latest.overall_score}%</span>
            </div>
            <span className={`text-[10px] font-extrabold px-3 py-1 border rounded-full uppercase ${getReadinessBg(readiness.latest.classification)}`}>
              {readiness.latest.classification.replace('_', ' ')}
            </span>
          </div>

          <div className="md:col-span-3 grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { label: 'Entity Quality', val: readiness.latest.entity_quality, color: 'text-emerald-500' },
              { label: 'Assessment Quality', val: readiness.latest.assessment_quality, color: 'text-accent-hover' },
              { label: 'Explanation Quality', val: readiness.latest.explanation_quality, color: 'text-cyan' },
              { label: 'Scenario Quality', val: readiness.latest.scenario_quality, color: 'text-amber-500' },
              { label: 'Goal Quality', val: readiness.latest.goal_quality, color: 'text-red-500' }
            ].map((metric, idx) => (
              <div key={idx} className="p-4 bg-surface-card border border-border rounded-xl flex flex-col justify-between">
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider">{metric.label}</span>
                <span className={`text-xl font-bold ${metric.color} mt-2`}>{Math.round(metric.val)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Side: Failure Log */}
        <div className="lg:col-span-2 space-y-4 bg-surface-card border border-border rounded-xl p-6">
          <h3 className="text-sm font-bold text-text-primary border-b border-border pb-2">Diagnostic Failure Log</h3>
          <div className="space-y-3 overflow-y-auto max-h-[350px] pr-2">
            {failures.length === 0 ? (
              <p className="text-xs text-text-muted text-center py-8">No system failures detected in recent assessments.</p>
            ) : (
              failures.map((report) => (
                <div key={report.id} className="p-3 bg-surface border border-border rounded-lg space-y-2 flex justify-between items-start">
                  <div>
                    <span className="text-[9px] text-text-muted">Assessment #{report.assessment_id}</span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {report.failures.map((f, i) => (
                        <span key={i} className="text-[9px] font-mono font-bold bg-red-bg border border-red/20 text-red px-1.5 py-0.5 rounded">
                          {f}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className={`text-[9px] font-bold px-2 py-0.5 border rounded uppercase ${report.severity === 'HIGH' ? 'text-red border-red/20 bg-red/5' : 'text-amber-500 border-amber-500/20 bg-amber-500/5'}`}>
                    {report.severity}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Side: Human Review Form & Benchmark Suite */}
        <div className="space-y-6">
          {/* Human Review */}
          <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
            <h3 className="text-sm font-bold text-text-primary border-b border-border pb-2">Analyst Review Submission</h3>
            <form onSubmit={handleReviewSubmit} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="number"
                  placeholder="Ass ID"
                  required
                  value={reviewForm.assessmentId}
                  onChange={(e) => setReviewForm({ ...reviewForm, assessmentId: e.target.value })}
                  className="bg-surface border border-border text-text-primary text-xs p-2 rounded w-full"
                />
                <input
                  type="text"
                  placeholder="Analyst Name"
                  required
                  value={reviewForm.analystName}
                  onChange={(e) => setReviewForm({ ...reviewForm, analystName: e.target.value })}
                  className="bg-surface border border-border text-text-primary text-xs p-2 rounded w-full"
                />
              </div>

              <div className="grid grid-cols-2 gap-2 text-[10px] text-text-secondary">
                {['usefulness', 'correctness', 'confidence', 'explanation'].map((field) => (
                  <div key={field} className="flex justify-between items-center">
                    <span className="capitalize">{field}</span>
                    <input
                      type="number"
                      min="1"
                      max="5"
                      required
                      value={reviewForm[field]}
                      onChange={(e) => setReviewForm({ ...reviewForm, [field]: parseInt(e.target.value) })}
                      className="bg-surface border border-border text-text-primary w-10 text-center rounded py-0.5"
                    />
                  </div>
                ))}
              </div>

              <textarea
                placeholder="Review notes..."
                value={reviewForm.notes}
                onChange={(e) => setReviewForm({ ...reviewForm, notes: e.target.value })}
                className="bg-surface border border-border text-text-primary text-xs p-2 rounded w-full h-16"
              />

              <button
                type="submit"
                className="w-full bg-accent hover:bg-accent-hover text-white text-xs font-bold py-2 rounded transition-all cursor-pointer"
              >
                SUBMIT REVIEW
              </button>

              {reviewMsg && <p className="text-[10px] text-center text-text-secondary font-medium">{reviewMsg}</p>}
            </form>
          </div>

          {/* Benchmark Harness */}
          <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
            <h3 className="text-sm font-bold text-text-primary border-b border-border pb-2">Benchmark Validation Harness</h3>
            <div className="grid grid-cols-3 gap-2">
              {[20, 50, 100].map((num) => (
                <button
                  key={num}
                  onClick={() => handleBenchmark(num)}
                  disabled={benchmarking}
                  className="bg-surface hover:border-accent text-text-secondary border border-border py-2 text-xs rounded transition-all cursor-pointer font-semibold"
                >
                  {benchmarking ? '...' : `Run ${num}`}
                </button>
              ))}
            </div>
            {testResult && (
              <div className="p-3 bg-surface border border-border rounded text-[10px] text-text-secondary space-y-1">
                <div>Readiness Score: <strong className="text-text-primary">{testResult.overall_readiness_score}%</strong></div>
                <div>Classification: <strong className="text-text-primary">{testResult.readiness_classification}</strong></div>
                <div>Processed: <strong className="text-text-primary">{testResult.num_items_processed} items</strong></div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
