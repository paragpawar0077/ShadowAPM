import React, { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api.js";

export default function Overview() {
  const [modelInfo, setModelInfo] = useState(null);
  const [rca, setRca] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const refresh = async () => {
    try {
      setError(null);
      const [mi, reports, exps] = await Promise.all([
        api.modelInfo(),
        api.listRCA(),
        api.listExperiments(),
      ]);
      setModelInfo(mi);
      setRca(reports);
      setExperiments(exps);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, []);

  const runPipeline = async () => {
    setBusy(true);
    try {
      await api.trainModel(0.1);
      await api.scoreModel(200);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const activeExperiments = experiments.filter((e) => e.active).length;
  const anomalousReports = rca.filter((r) => r.confidence === "high").length;
  const chartData = rca
    .slice()
    .reverse()
    .map((r, i) => ({ idx: i + 1, confidence: r.confidence === "high" ? 2 : r.confidence === "medium" ? 1 : 0 }));

  return (
    <>
      {error && <div className="panel" style={{ borderColor: "#f87171" }}>⚠ {error} — is the backend running?</div>}

      <div className="grid">
        <div className="stat">
          <div className="value">{activeExperiments}</div>
          <div className="label">Active chaos experiments</div>
        </div>
        <div className="stat">
          <div className="value">{modelInfo?.trained_on_rows ?? "—"}</div>
          <div className="label">Telemetry rows used for training</div>
        </div>
        <div className="stat">
          <div className="value">{rca.length}</div>
          <div className="label">RCA reports generated</div>
        </div>
        <div className="stat">
          <div className="value">{anomalousReports}</div>
          <div className="label">High-confidence root causes</div>
        </div>
      </div>

      <div className="panel">
        <h2>Anomaly / RCA model</h2>
        <div className="form-row">
          <span className="muted">
            Model status: {modelInfo?.loaded ? "trained" : "not trained yet"} · version: {modelInfo?.version || "—"}
          </span>
          <button onClick={runPipeline} disabled={busy}>
            {busy ? "Running…" : "Retrain & Score Now"}
          </button>
        </div>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={chartData}>
            <CartesianGrid stroke="#223041" strokeDasharray="3 3" />
            <XAxis dataKey="idx" stroke="#8b98a5" fontSize={11} label={{ value: "recent RCA reports", position: "insideBottom", offset: -2, fill: "#8b98a5", fontSize: 11 }} />
            <YAxis stroke="#8b98a5" fontSize={11} ticks={[0, 1, 2]} tickFormatter={(v) => ["low", "med", "high"][v]} />
            <Tooltip contentStyle={{ background: "#12181f", border: "1px solid #223041" }} />
            <Line type="monotone" dataKey="confidence" stroke="#4fd1c5" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="panel">
        <h2>Recent RCA reports</h2>
        <table>
          <thead>
            <tr><th>Request</th><th>Root cause</th><th>Confidence</th><th>Source</th></tr>
          </thead>
          <tbody>
            {rca.slice(0, 6).map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.request_id?.slice(0, 10)}…</td>
                <td>{r.root_cause}</td>
                <td>
                  <span className={`badge ${r.confidence === "high" ? "danger" : r.confidence === "medium" ? "warn" : "muted"}`}>
                    {r.confidence}
                  </span>
                </td>
                <td className="muted">{r.generated_by}</td>
              </tr>
            ))}
            {rca.length === 0 && (
              <tr><td colSpan={4} className="muted">No RCA reports yet — run a chaos experiment, then generate one from the RCA tab.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
