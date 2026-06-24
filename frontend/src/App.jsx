import { useState, useEffect, useRef } from 'react';
import { analyzeNews, getAnalysisStatus } from './api';
import NewsInputPanel from './components/NewsInputPanel';
import IntelligenceReport from './components/IntelligenceReport';

export default function App() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState(null);
  const [llmStatus, setLlmStatus] = useState('disabled');
  const [llmError, setLlmError] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [stats, setStats] = useState(null);
  const [processingTime, setProcessingTime] = useState(null);
  const [error, setError] = useState(null);

  const pollIntervalRef = useRef(null);

  // Clear polling interval on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const handleAnalyze = async (title, content, useLlm) => {
    setIsAnalyzing(true);
    setError(null);
    setLlmError(null);
    setPipelineSteps(null);
    setProcessingTime(null);

    // Provide immediate mock/loading progress sequence for deterministic pipeline steps
    // while the server executes the synchronous call.
    const steps = {
      ingestion: { status: 'running' },
      preprocessing: { status: 'pending' },
      clustering: { status: 'pending' },
      timeline: { status: 'pending' },
      expansion: { status: 'pending' },
      impact: { status: 'pending' },
      signals: { status: 'pending' },
      assessment: { status: 'pending' },
    };
    setPipelineSteps(steps);

    try {
      const response = await analyzeNews(title, content, useLlm);

      // Handle structured pipeline failure
      if (response.status === 'failed') {
        setPipelineSteps(response.pipeline || steps);
        const errMsg = response.failed_step
          ? `Pipeline failed at step "${response.failed_step}": ${response.error}`
          : response.error || 'Pipeline failed without a specific error.';
        setError(errMsg);
        setIsAnalyzing(false);
        return;
      }

      // Update pipeline steps from response
      const updatedSteps = { ...steps };
      Object.keys(response.pipeline || {}).forEach((key) => {
        if (updatedSteps[key]) {
          updatedSteps[key] = response.pipeline[key];
        }
      });
      // Mark all deterministic steps as OK
      Object.keys(updatedSteps).forEach((key) => {
        if (updatedSteps[key].status === 'running' || updatedSteps[key].status === 'pending') {
          updatedSteps[key].status = 'ok';
        }
      });
      setPipelineSteps(updatedSteps);

      // Set initial results
      setAssessment(response.assessment);
      setStats(response.stats);
      setProcessingTime(response.stats?.processing_time);

      const llmPipelineStatus = response.pipeline?.llm?.status;
      const llmEffectivelyRunning = useLlm && llmPipelineStatus !== 'disabled';
      setLlmStatus(llmEffectivelyRunning ? 'running' : 'disabled');
      setIsAnalyzing(false);

      if (llmEffectivelyRunning && response.analysis_id) {
        startPolling(response.analysis_id);
      }
    } catch (err) {
      console.error(err);
      setError(err?.response?.data?.detail || 'Failed to complete deterministic intelligence pipeline.');
      setIsAnalyzing(false);
    }
  };

  const startPolling = (analysisId) => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = setInterval(async () => {
      try {
        const statusData = await getAnalysisStatus(analysisId);
        
        // Update live assessment objects as they refine
        if (statusData.assessment) {
          setAssessment(statusData.assessment);
        }
        
        setLlmStatus(statusData.llm_status);

        if (statusData.llm_status === 'completed') {
          clearInterval(pollIntervalRef.current);
        } else if (statusData.llm_status === 'failed') {
          setLlmError(statusData.llm_error || 'LLM generation failed.');
          clearInterval(pollIntervalRef.current);
        }
      } catch (err) {
        console.error('Polling failed:', err);
        setLlmStatus('failed');
        setLlmError('Connection error polling intelligence status.');
        clearInterval(pollIntervalRef.current);
      }
    }, 1500);
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-surface/80 backdrop-blur-xl border-b border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent to-cyan flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5.002 5.002 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary tracking-tight">DeepDive Intelligence</h1>
              <p className="text-xs text-text-muted">Analyst Workspace</p>
            </div>
          </div>
          <div className="text-xs text-text-secondary bg-surface-alt px-3 py-1.5 rounded-lg border border-border">
            🟢 Workspace Online
          </div>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column - Input Panel */}
          <div className="lg:col-span-4 bg-surface-card border border-border rounded-xl p-5">
            <NewsInputPanel
              onAnalyze={handleAnalyze}
              isAnalyzing={isAnalyzing}
              pipelineSteps={pipelineSteps}
              llmStatus={llmStatus}
              processingTime={processingTime}
              error={error}
            />
          </div>

          {/* Right Column - Intelligence Report */}
          <div className="lg:col-span-8">
            <IntelligenceReport
              assessment={assessment}
              stats={stats}
              llmStatus={llmStatus}
              llmError={llmError}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
