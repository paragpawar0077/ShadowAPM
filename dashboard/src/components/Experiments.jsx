import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const FAULT_TYPES = [
  { id: "latency", label: "Latency spike", defaultParams: { delay_ms: 700 } },
  { id: "error_5xx", label: "5xx error", defaultParams: { status: 503 } },
  { id: "timeout", label: "Timeout", defaultParams: { delay_ms: 5000 } },
  { id: "dependency_failure", label: "Dependency failure", defaultParams: { dependency: "payment-service" } },
];

export default function Experiments() {
  const [experiments, setExperiments] = useState([]);
  const [name, setName] = useState("");
  const [targetPath, setTargetPath] = useState("/orders");
  const [faultType, setFaultType] = useState("latency");
  const [error, setError] = useState(null);

  const refresh = async () => {
    try {
      setError(null);
      setExperiments(await api.listExperiments());
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 6000);
    return () => clearInterval(id);
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    const params = FAULT_TYPES.find((f) => f.id === faultType).defaultParams;
    try {
      await api.createExperiment({ name, target_path: targetPath, fault_type: faultType, params, active: true });
      setName("");
      refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const toggle = async (exp) => {
    await api.toggleExperiment(exp.id, !exp.active);
    refresh();
  };

  const remove = async (exp) => {
    await api.deleteExperiment(exp.id);
    refresh();
  };

  return (
    <>
      {error && <div className="panel" style={{ borderColor: "#f87171" }}>⚠ {error} — is chaos-engine running?</div>}

      <div className="panel">
        <h2>New chaos experiment</h2>
        <div className="form-row">
          <input placeholder="Experiment name" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="Target path (e.g. /orders or *)" value={targetPath} onChange={(e) => setTargetPath(e.target.value)} />
          <select value={faultType} onChange={(e) => setFaultType(e.target.value)}>
            {FAULT_TYPES.map((f) => (
              <option key={f.id} value={f.id}>{f.label}</option>
            ))}
          </select>
          <button onClick={create}>Create &amp; Activate</button>
        </div>
        <p className="muted" style={{ fontSize: 12 }}>
          Experiments only ever run against the sandbox replica — production traffic is never touched.
        </p>
      </div>

      <div className="panel">
        <h2>Configured experiments</h2>
        <table>
          <thead>
            <tr><th>Name</th><th>Target</th><th>Fault</th><th>Params</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {experiments.map((exp) => (
              <tr key={exp.id}>
                <td>{exp.name}</td>
                <td className="mono">{exp.target_path}</td>
                <td>{exp.fault_type}</td>
                <td className="mono">{JSON.stringify(exp.params)}</td>
                <td><span className={`badge ${exp.active ? "ok" : "muted"}`}>{exp.active ? "active" : "paused"}</span></td>
                <td>
                  <button className="secondary" onClick={() => toggle(exp)} style={{ marginRight: 6 }}>
                    {exp.active ? "Pause" : "Resume"}
                  </button>
                  <button className="secondary" onClick={() => remove(exp)}>Delete</button>
                </td>
              </tr>
            ))}
            {experiments.length === 0 && (
              <tr><td colSpan={6} className="muted">No experiments yet — create one above.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
