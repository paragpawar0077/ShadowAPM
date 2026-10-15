const CHAOS_URL = import.meta.env.VITE_CHAOS_ENGINE_URL || "http://localhost:8003";
const ANOMALY_URL = import.meta.env.VITE_ANOMALY_DETECTOR_URL || "http://localhost:8004";
const RCA_URL = import.meta.env.VITE_RCA_AGENT_URL || "http://localhost:8005";

async function j(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

export const api = {
  listExperiments: () => j(`${CHAOS_URL}/experiments`),
  createExperiment: (body) =>
    j(`${CHAOS_URL}/experiments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  toggleExperiment: (id, active) =>
    j(`${CHAOS_URL}/experiments/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    }),
  deleteExperiment: (id) => j(`${CHAOS_URL}/experiments/${id}`, { method: "DELETE" }),

  trainModel: (contamination = 0.1) =>
    j(`${ANOMALY_URL}/train?contamination=${contamination}`, { method: "POST" }),
  scoreModel: (limit = 200) => j(`${ANOMALY_URL}/score?limit=${limit}`, { method: "POST" }),
  modelInfo: () => j(`${ANOMALY_URL}/model`),

  listRCA: () => j(`${RCA_URL}/rca`),
  generateRCA: (request_id) =>
    j(`${RCA_URL}/rca`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id }),
    }),
};
