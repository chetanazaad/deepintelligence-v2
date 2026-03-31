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
