import React, { useState } from 'react';

export default function ScenarioPanel({ scenarios }) {
  const [activeTab, setActiveTab] = useState('likely');

  if (!scenarios) {
    return (
      <div className="bg-surface-card border border-border rounded-xl p-4 text-center">
        <p className="text-text-secondary text-sm">No predictive scenarios available.</p>
      </div>
    );
  }

  // Handle both dict layout and string layout
  const scenariosData = typeof scenarios === 'string'
    ? { likely: scenarios, possible: 'No additional possible scenarios documented.', unlikely: 'No outlier scenarios documented.' }
    : scenarios;

  const tabs = [
    { id: 'likely', label: 'Likely', color: 'border-emerald-500 text-emerald-500' },
    { id: 'possible', label: 'Possible', color: 'border-amber-500 text-amber-500' },
    { id: 'unlikely', label: 'Unlikely', color: 'border-red-500 text-red-500' }
  ];

  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
      <h3 className="text-sm font-bold text-text-primary border-b border-border pb-3">Future Scenarios</h3>

      <div className="flex border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 pb-2 text-xs font-semibold uppercase tracking-wider text-center border-b-2 transition-all cursor-pointer
              ${activeTab === tab.id
                ? `${tab.color}`
                : 'border-transparent text-text-muted hover:text-text-secondary'
              }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="p-4 bg-surface-alt rounded-lg border border-border min-h-[100px]">
        <p className="text-sm text-text-secondary leading-relaxed">
          {scenariosData[activeTab] || 'No details specified for this classification.'}
        </p>
      </div>
    </div>
  );
}
