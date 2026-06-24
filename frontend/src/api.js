import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Primary: Intelligence Analysis ──────────────────────────────

/**
 * Submit an article for full intelligence analysis.
 * Returns deterministic results immediately; LLM runs in background.
 */
export async function analyzeNews(title, content, useLlm = true) {
  const res = await api.post(
    '/analyze',
    { title, content, source: 'user', use_llm: useLlm },
    { timeout: 120000 }
  );
  return res.data;
}

/**
 * Poll for LLM analysis completion.
 */
export async function getAnalysisStatus(analysisId) {
  const res = await api.get(`/analyze/${analysisId}/status`);
  return res.data;
}

// ── Legacy: Retained for backward compatibility ─────────────────

export async function searchEvents(query, limit = 10) {
  const res = await api.get('/event', { params: { query, limit } });
  return res.data;
}

export async function getValidation() {
  const res = await api.get('/pipeline/validate');
  return res.data;
}

export async function listGoals(status = null) {
  const res = await api.get('/goals', { params: { status } });
  return res.data;
}

export async function getGoalDetails(goalId) {
  const res = await api.get(`/goals/${goalId}`);
  return res.data;
}

export async function getLatestAssessment(goalId) {
  const res = await api.get(`/goals/${goalId}/assessments/latest`);
  return res.data;
}

export async function getLeadQueue(status = null) {
  const url = status ? `/expansion/queue?status=${status}` : `/expansion/queue`;
  const res = await api.get(url);
  return res.data;
}

export async function getEvaluationStatus() {
  const res = await api.get('/pipeline/validate');
  return res.data;
}

export async function getLlmAssessment(goalId) {
  const res = await api.get(`/goals/${goalId}/assessments/llm`);
  return res.data;
}
