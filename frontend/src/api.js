import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

export async function searchEvents(query, limit = 10) {
  const res = await api.get('/event', { params: { query, limit } });
  return res.data;
}

export async function getTimeline(nodeId) {
  const res = await api.get(`/timeline/${nodeId}`);
  return res.data;
}

export async function getImpact(nodeId) {
  const res = await api.get(`/impact/${nodeId}`);
  return res.data;
}

export async function getSignals(nodeId) {
  const res = await api.get(`/signals/${nodeId}`);
  return res.data;
}

export async function getValidation() {
  const res = await api.get('/pipeline/validate');
  return res.data;
}

export async function getPipelineStatus() {
  const res = await api.get('/pipeline/status');
  return res.data;
}

// --- Recursive Expansion API ---

export async function expandNode(nodeId, config = {}) {
  const res = await api.post(`/expand/${nodeId}`, config, { timeout: 60000 });
  return res.data;
}

export async function getExpansionStatus(nodeId) {
  const res = await api.get(`/expand/${nodeId}/status`);
  return res.data;
}

export async function getExpansionGraph(nodeId, depth = 3) {
  const res = await api.get(`/graph/${nodeId}`, { params: { depth } });
  return res.data;
}

export async function getNodeChildren(nodeId) {
  const res = await api.get(`/node/${nodeId}/children`);
  return res.data;
}

export async function getResearchHistory(nodeId) {
  const res = await api.get(`/node/${nodeId}/research`);
  return res.data;
}

export async function triggerNodeResearch(nodeId) {
  const res = await api.post(`/research/${nodeId}`, {}, { timeout: 30000 });
  return res.data;
}

export async function triggerExpansionCycle() {
  const res = await api.post(`/expansion/cycle`, {}, { timeout: 60000 });
  return res.data;
}

export async function getLeadQueue(status = null) {
  const url = status ? `/expansion/queue?status=${status}` : `/expansion/queue`;
  const res = await api.get(url);
  return res.data;
}
