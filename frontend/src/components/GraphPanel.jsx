import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';

export default function GraphPanel({ centerNode, evidence = [], goals = [], scenarios = [] }) {
  const nodes = useMemo(() => {
    if (!centerNode) return [];

    const list = [];
    // 1. Center Node
    list.push({
      id: 'center',
      type: 'input',
      data: { label: `${centerNode.entity}\n(${centerNode.entity_type})` },
      position: { x: 250, y: 150 },
      style: {
        background: '#6366f1',
        color: '#fff',
        border: '1px solid #818cf8',
        borderRadius: '8px',
        padding: '10px',
        fontWeight: 'bold',
        fontSize: '12px',
        width: 160
      }
    });

    // 2. Evidence Nodes (Left side)
    const evidenceItems = evidence.items || [];
    evidenceItems.slice(0, 3).forEach((item, idx) => {
      list.push({
        id: `ev-${idx}`,
        data: { label: `✓ ${item.claim || 'Evidence'}` },
        position: { x: 50, y: 50 + idx * 100 },
        style: {
          background: '#151820',
          color: '#10b981',
          border: '1px solid #10b98130',
          borderRadius: '6px',
          padding: '8px',
          fontSize: '10px',
          width: 140
        }
      });
    });

    // 3. Goal Nodes (Top)
    goals.slice(0, 2).forEach((goal, idx) => {
      list.push({
        id: `goal-${idx}`,
        data: { label: `Goal: ${goal.goal_question.substring(0, 30)}...` },
        position: { x: 180 + idx * 180, y: 10 },
        style: {
          background: '#151820',
          color: '#06b6d4',
          border: '1px solid #06b6d430',
          borderRadius: '6px',
          padding: '8px',
          fontSize: '10px',
          width: 150
        }
      });
    });

    // 4. Scenario Nodes (Right side)
    const scenarioList = typeof scenarios === 'object' ? Object.keys(scenarios) : ['likely', 'possible'];
    scenarioList.slice(0, 2).forEach((scen, idx) => {
      list.push({
        id: `scen-${idx}`,
        type: 'output',
        data: { label: `Scenario: ${scen.toUpperCase()}` },
        position: { x: 480, y: 100 + idx * 120 },
        style: {
          background: '#151820',
          color: '#f59e0b',
          border: '1px solid #f59e0b30',
          borderRadius: '6px',
          padding: '8px',
          fontSize: '10px',
          width: 130
        }
      });
    });

    return list;
  }, [centerNode, evidence, goals, scenarios]);

  const edges = useMemo(() => {
    if (!centerNode) return [];
    const list = [];

    // Connect Evidence -> Center
    const evidenceItems = evidence.items || [];
    evidenceItems.slice(0, 3).forEach((_, idx) => {
      list.push({
        id: `e-ev-${idx}`,
        source: `ev-${idx}`,
        target: 'center',
        animated: true,
        style: { stroke: '#10b981' }
      });
    });

    // Connect Center -> Goals
    goals.slice(0, 2).forEach((_, idx) => {
      list.push({
        id: `e-goal-${idx}`,
        source: 'center',
        target: `goal-${idx}`,
        style: { stroke: '#06b6d4' }
      });
    });

    // Connect Center -> Scenarios
    const scenarioList = typeof scenarios === 'object' ? Object.keys(scenarios) : ['likely', 'possible'];
    scenarioList.slice(0, 2).forEach((_, idx) => {
      list.push({
        id: `e-scen-${idx}`,
        source: 'center',
        target: `scen-${idx}`,
        style: { stroke: '#f59e0b' }
      });
    });

    return list;
  }, [centerNode, evidence, goals, scenarios]);

  if (!centerNode) {
    return (
      <div className="bg-surface-card border border-border rounded-xl p-6 text-center h-[350px] flex items-center justify-center">
        <p className="text-text-secondary text-sm">Select an event node to visualize its investigation network.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface-card border border-border rounded-xl p-6 space-y-4">
      <h3 className="text-sm font-bold text-text-primary border-b border-border pb-3">Investigation Graph</h3>
      <div className="h-[350px] bg-surface rounded-lg overflow-hidden border border-border">
        <ReactFlow nodes={nodes} edges={edges} fitView>
          <Background color="#2a2f3e" gap={16} />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
