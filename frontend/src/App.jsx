import { useState, useEffect } from 'react';
import {
  searchEvents,
  listGoals,
  getGoalDetails,
  getLatestAssessment,
  getLeadQueue,
  getEvaluationStatus
} from './api';

import SearchBar from './components/SearchBar';
import EventCard from './components/EventCard';
import IntelligenceAssessmentCard from './components/IntelligenceAssessmentCard';
import EvidencePanel from './components/EvidencePanel';
import GapPanel from './components/GapPanel';
import ScenarioPanel from './components/ScenarioPanel';
import GoalPanel from './components/GoalPanel';
import ResearchPanel from './components/ResearchPanel';
import AlternativeExplanations from './components/AlternativeExplanations';
import EvaluationPanel from './components/EvaluationPanel';
import GraphPanel from './components/GraphPanel';
import ValidationDashboard from './components/ValidationDashboard';

export default function App() {
  // Navigation & Workspace Toggles
  const [currentView, setCurrentView] = useState('intelligence'); // 'intelligence' | 'validation'
  
  // Navigation & Search
  const [results, setResults] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');

  // Intelligence Core State
  const [goals, setGoals] = useState([]);
  const [selectedGoalId, setSelectedGoalId] = useState(null);
  const [goalDetails, setGoalDetails] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [leads, setLeads] = useState([]);
  const [systemHealth, setSystemHealth] = useState(null);

  // Initial loading of goals, leads, and system health
  useEffect(() => {
    async function loadInitialData() {
      try {
        const goalsData = await listGoals();
        setGoals(goalsData.goals || []);
        if (goalsData.goals?.length > 0) {
          setSelectedGoalId(goalsData.goals[0].id);
        }

        const leadsData = await getLeadQueue();
        setLeads(leadsData.queue || []);

        const healthData = await getEvaluationStatus();
        setSystemHealth(healthData);
      } catch (err) {
        console.error('Failed to load initial workspace data:', err);
      }
    }
    loadInitialData();
  }, []);

  // Fetch goal details & latest assessment whenever selectedGoalId changes
  useEffect(() => {
    if (!selectedGoalId) return;

    async function loadGoalData() {
      try {
        const details = await getGoalDetails(selectedGoalId);
        setGoalDetails(details);

        // Fetch latest assessment for this goal
        try {
          const ass = await getLatestAssessment(selectedGoalId);
          setAssessment(ass);
        } catch {
          // If no assessment exists yet, reset state
          setAssessment(null);
        }
      } catch (err) {
        console.error(`Failed to load data for goal ${selectedGoalId}:`, err);
      }
    }
    loadGoalData();
  }, [selectedGoalId]);

  const handleSearch = async (q) => {
    setLoading(true);
    setError(null);
    setQuery(q);
    try {
      const data = await searchEvents(q);
      setResults(data.results || []);
      if (data.results?.length > 0) {
        setSelectedEvent(data.results[0].event || null);
      } else {
        setError('No events found. Try a different search term.');
      }
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to fetch. Is the backend running?');
      setResults([]);
      setSelectedEvent(null);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col pb-16">
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
              <p className="text-xs text-text-muted">Intelligence Analysis Platform</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <nav className="flex gap-1 p-1 bg-surface-alt rounded-lg border border-border">
              <button
                onClick={() => setCurrentView('intelligence')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-all cursor-pointer ${currentView === 'intelligence' ? 'bg-surface-card text-accent' : 'text-text-muted hover:text-text-secondary'}`}
              >
                💼 WORKSPACE
              </button>
              <button
                onClick={() => setCurrentView('validation')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-all cursor-pointer ${currentView === 'validation' ? 'bg-surface-card text-accent' : 'text-text-muted hover:text-text-secondary'}`}
              >
                🛡️ VALIDATION
              </button>
            </nav>
            <div className="w-80">
              <SearchBar onSearch={handleSearch} loading={loading} />
            </div>
          </div>
        </div>
      </header>

      {/* Workspace */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Error notification */}
        {error && (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-red-bg border border-red/20 text-red text-sm">
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {currentView === 'validation' ? (
          <ValidationDashboard />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* LEFT COLUMN: Events & Goals */}
          <div className="lg:col-span-1 space-y-6">
            {results.length > 0 && (
              <div className="bg-surface-card border border-border rounded-xl p-4 space-y-3">
                <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider">Related Events</h3>
                <div className="space-y-2 max-h-[250px] overflow-y-auto">
                  {results.map((res, i) => (
                    <EventCard
                      key={res.event?.node_id || i}
                      event={res.event}
                      isSelected={selectedEvent?.node_id === res.event?.node_id}
                      onClick={() => setSelectedEvent(res.event)}
                    />
                  ))}
                </div>
              </div>
            )}

            <GoalPanel
              goals={goals}
              selectedGoalId={selectedGoalId}
              onSelectGoal={setSelectedGoalId}
            />
          </div>

          {/* CENTER COLUMN: Intelligence Assessment & Evidence */}
          <div className="lg:col-span-2 space-y-6">
            <IntelligenceAssessmentCard
              assessment={assessment}
              goalQuestion={goalDetails?.goal_question || 'No Active Goal Selected'}
            />

            <EvidencePanel evidenceSummary={assessment?.evidence_summary} />

            <GraphPanel
              centerNode={selectedEvent || (goalDetails ? { entity: goalDetails.keywords?.[0] || 'Investigation Target', entity_type: 'Concept' } : null)}
              evidence={assessment?.evidence_summary}
              goals={goals}
              scenarios={assessment?.future_scenarios}
            />
          </div>

          {/* RIGHT COLUMN: Gaps, Scenarios & Alternative Hypotheses */}
          <div className="lg:col-span-1 space-y-6">
            <GapPanel gaps={assessment?.knowledge_gaps || goalDetails?.gap_analysis} />

            <AlternativeExplanations explanations={assessment?.alternative_explanations} />

            <ScenarioPanel scenarios={assessment?.future_scenarios} />

            <ResearchPanel leads={leads} />
          </div>
        </div>
      )}
    </main>

      {/* Developer Health Panel */}
      <EvaluationPanel statusData={systemHealth} />
    </div>
  );
}
