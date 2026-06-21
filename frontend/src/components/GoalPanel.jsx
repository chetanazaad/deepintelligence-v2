import React from 'react';

export default function GoalPanel({
  goals,
  selectedGoalId,
  onSelectGoal,
  onPauseGoal,
  onResumeGoal,
  onAbandonGoal,
  onCreateGoal
}) {
  const getStatusBadge = (status) => {
    switch (status?.toLowerCase()) {
      case 'completed':
        return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
      case 'paused':
        return 'text-amber-500 bg-amber-500/10 border-amber-500/20';
      case 'abandoned':
        return 'text-red-500 bg-red-500/10 border-red-500/20';
      default:
        return 'text-cyan bg-cyan/10 border-cyan/20';
    }
  };

  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4 flex flex-col h-full">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <h3 className="text-sm font-bold text-text-primary">Investigation Goals</h3>
        {onCreateGoal && (
          <button
            onClick={onCreateGoal}
            className="text-[10px] font-bold bg-accent hover:bg-accent-hover text-white px-2 py-1 rounded transition-all cursor-pointer"
          >
            + NEW GOAL
          </button>
        )}
      </div>

      <div className="space-y-3 overflow-y-auto flex-1 max-h-[350px] pr-1">
        {goals.length === 0 ? (
          <p className="text-xs text-text-muted text-center py-6">No goals configured yet.</p>
        ) : (
          goals.map((goal) => {
            const isSelected = selectedGoalId === goal.id;
            const progress = goal.completion_score || 0;
            return (
              <div
                key={goal.id}
                onClick={() => onSelectGoal(goal.id)}
                className={`p-3.5 rounded-lg border transition-all cursor-pointer space-y-2
                  ${isSelected
                    ? 'bg-surface-alt border-accent shadow-sm'
                    : 'bg-surface border-border hover:border-border-active'
                  }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold text-text-primary leading-snug">{goal.goal_question}</p>
                  <span className={`text-[9px] font-bold px-2 py-0.5 border rounded uppercase ${getStatusBadge(goal.status)}`}>
                    {goal.status}
                  </span>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] text-text-secondary">
                    <span>Progress</span>
                    <span>{Math.round(progress)}%</span>
                  </div>
                  <div className="w-full bg-border rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-accent h-1.5 rounded-full transition-all duration-500"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>

                {isSelected && (
                  <div className="flex gap-2 pt-2 border-t border-border mt-2 justify-end">
                    {goal.status === 'active' && onPauseGoal && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onPauseGoal(goal.id); }}
                        className="text-[9px] px-2 py-1 bg-amber-500/10 text-amber-500 rounded border border-amber-500/20 hover:bg-amber-500/20"
                      >
                        PAUSE
                      </button>
                    )}
                    {goal.status === 'paused' && onResumeGoal && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onResumeGoal(goal.id); }}
                        className="text-[9px] px-2 py-1 bg-emerald-500/10 text-emerald-500 rounded border border-emerald-500/20 hover:bg-emerald-500/20"
                      >
                        RESUME
                      </button>
                    )}
                    {goal.status !== 'abandoned' && goal.status !== 'completed' && onAbandonGoal && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onAbandonGoal(goal.id); }}
                        className="text-[9px] px-2 py-1 bg-red-500/10 text-red-500 rounded border border-red-500/20 hover:bg-red-500/20"
                      >
                        ABANDON
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
