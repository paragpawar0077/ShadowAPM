import React, { useState } from "react";
import Overview from "./components/Overview.jsx";
import Experiments from "./components/Experiments.jsx";
import RCAReports from "./components/RCAReports.jsx";

const TABS = [
  { id: "overview", label: "Reliability Overview" },
  { id: "experiments", label: "Chaos Experiments" },
  { id: "rca", label: "RCA Reports" },
];

export default function App() {
  const [tab, setTab] = useState("overview");

  return (
    <div className="app">
      <div className="header">
        <h1>🛡️ ShadowAPM</h1>
        <span className="tag">AI-Driven Chaos Engineering &amp; Reliability Platform</span>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <div
            key={t.id}
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </div>
        ))}
      </div>

      {tab === "overview" && <Overview />}
      {tab === "experiments" && <Experiments />}
      {tab === "rca" && <RCAReports />}
    </div>
  );
}
