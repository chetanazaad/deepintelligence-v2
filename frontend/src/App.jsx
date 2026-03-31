import { useState } from 'react';
import { searchEvents } from './api';
import SearchBar from './components/SearchBar';
import EventCard from './components/EventCard';
import TimelineView from './components/TimelineView';
import ImpactView from './components/ImpactView';
import SignalView from './components/SignalView';
import MetadataPanel from './components/MetadataPanel';

const TABS = [
  { id: 'timeline', label: 'Timeline', icon: '🕐' },
  { id: 'impact', label: 'Impact', icon: '📊' },
  { id: 'signals', label: 'Signals', icon: '📡' },
];

export default function App() {
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState('timeline');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');

  const handleSearch = async (q) => {
    setLoading(true);
    setError(null);
    setQuery(q);
    try {
      const data = await searchEvents(q);
      setResults(data.results || []);
      setSelected(data.results?.[0] || null);
      if (!data.results?.length) setError('No events found. Try a different search term.');
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to fetch. Is the backend running?');
      setResults([]);
      setSelected(null);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-surface">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-surface/80 backdrop-blur-xl border-b border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent to-cyan flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5.002 5.002 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <div>
                <h1 className="text-lg font-bold text-text-primary tracking-tight">DeepDive Intelligence</h1>
                <p className="text-xs text-text-muted">News Intelligence Engine</p>
              </div>
            </div>

            {results.length > 0 && (
              <span className="text-xs text-text-muted bg-surface-hover px-3 py-1.5 rounded-full">
                {results.length} results for "<span className="text-text-secondary">{query}</span>"
              </span>
            )}
          </div>

          <SearchBar onSearch={handleSearch} loading={loading} />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Empty state */}
        {!loading && results.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-32 text-center">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-accent/20 to-cyan/20 flex items-center justify-center mb-6">
              <svg className="w-10 h-10 text-accent/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-text-primary mb-2">Explore Intelligence</h2>
            <p className="text-sm text-text-muted max-w-md">
              Search for events, entities, or topics to explore timelines, impact analysis, and early-warning signals.
            </p>
            <div className="flex flex-wrap gap-2 mt-6 justify-center">
              {['oil', 'technology', 'sanctions', 'inflation', 'supply'].map((term) => (
                <button
                  key={term}
                  onClick={() => handleSearch(term)}
                  className="px-4 py-2 text-sm bg-surface-card border border-border rounded-full text-text-secondary
                             hover:border-accent/40 hover:text-accent-hover hover:bg-accent/5 transition-all cursor-pointer"
                >
                  {term}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-red-bg border border-red/20 text-red text-sm mb-6">
            <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            {error}
          </div>
        )}

        {/* Results layout */}
        {results.length > 0 && (
          <div className="flex gap-6 flex-col lg:flex-row">
            {/* Left sidebar: event list */}
            <aside className="w-full lg:w-80 shrink-0 space-y-3">
              <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 px-1">Events</h2>
              <div className="space-y-2 max-h-[calc(100vh-200px)] overflow-y-auto pr-1">
                {results.map((result, i) => (
                  <EventCard
                    key={result.event?.node_id || i}
                    event={result.event}
                    isSelected={selected === result}
                    onClick={() => setSelected(result)}
                  />
                ))}
              </div>
            </aside>

            {/* Right: detail panel */}
            {selected && (
              <div className="flex-1 min-w-0 space-y-6">
                {/* Metadata */}
                <MetadataPanel metadata={selected.metadata} />

                {/* Tabs */}
                <div className="flex gap-1 p-1 bg-surface-alt rounded-xl">
                  {TABS.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium transition-all cursor-pointer
                        ${activeTab === tab.id
                          ? 'bg-surface-card text-text-primary shadow-sm border border-border'
                          : 'text-text-muted hover:text-text-secondary'
                        }`}
                    >
                      <span>{tab.icon}</span>
                      {tab.label}
                    </button>
                  ))}
                </div>

                {/* Tab content */}
                <div className="min-h-[400px]">
                  {activeTab === 'timeline' && <TimelineView timeline={selected.timeline} />}
                  {activeTab === 'impact' && <ImpactView impact={selected.impact} />}
                  {activeTab === 'signals' && <SignalView signals={selected.signals} />}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
