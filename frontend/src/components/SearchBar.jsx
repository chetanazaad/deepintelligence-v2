import { useState } from 'react';

const GLOW = 'focus:outline-none focus:ring-2 focus:ring-accent/40';

export default function SearchBar({ onSearch, loading }) {
  const [value, setValue] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (value.trim().length >= 2) onSearch(value.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto">
      <div className="relative group">
        {/* Glow ring */}
        <div className="absolute -inset-0.5 bg-gradient-to-r from-accent/30 to-cyan/30 rounded-2xl blur-sm opacity-0 group-focus-within:opacity-100 transition-opacity duration-300" />

        <div className="relative flex items-center bg-surface-card border border-border rounded-2xl overflow-hidden">
          {/* Search icon */}
          <div className="pl-5 text-text-muted">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>

          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Search events, entities, topics…"
            className={`flex-1 bg-transparent text-text-primary placeholder:text-text-muted px-4 py-4 text-base ${GLOW} outline-none border-none`}
          />

          <button
            type="submit"
            disabled={loading || value.trim().length < 2}
            className="mr-2 px-6 py-2.5 bg-accent hover:bg-accent-hover text-white font-medium rounded-xl
                       disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 text-sm cursor-pointer"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Searching
              </span>
            ) : 'Search'}
          </button>
        </div>
      </div>
    </form>
  );
}
