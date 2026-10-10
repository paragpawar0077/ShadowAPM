"""
LLM-based Root-Cause Analysis Agent (FR-06).

For a given anomalous request_id or experiment_id, this service:
  1. Gathers EVIDENCE — the actual telemetry rows, the matching chaos
     experiment config (if any), and the anomaly score — directly from the
     database. Nothing here is invented.
  2. Builds a structured, evidence-only prompt and sends it to a locally
     hosted Ollama model (free, zero-cost, per Section 9 / Section 12.2
     risk #1 and #5 mitigation).
  3. If Ollama is unreachable or misconfigured, falls back to a
     deterministic, rule-based explanation derived from the same evidence —
     so the pipeline NEVER silently returns a hallucinated or empty result
     (Section 12.2, risk #1's backup plan).

The evidence used to generate the explanation is stored alongside it in
RCAReport.evidence, so every explanation is independently verifiable against
the raw telemetry — this is the "human-verifiable root-cause explanation"
described in the problem statement (Section 8).
"""
import os
import sys
import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, "/app")
from common.db import SessionLocal, TelemetryEvent, ChaosExperiment, AnomalyScore, RCAReport, init_db  # noqa: E402

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

app = FastAPI(title="ShadowAPM RCA Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RCARequest(BaseModel):
    request_id: str


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "rca-agent"}


def gather_evidence(db, request_id: str):
    # Multiple telemetry rows can share a request_id (the proxy logs its own
    # mirror call, and the sandbox logs its own handling of that request).
    # Prefer the one that actually recorded the chaos fault, if any.
    event = (
        db.query(TelemetryEvent)
        .filter(TelemetryEvent.request_id == request_id)
        .order_by(TelemetryEvent.is_chaos.desc())
        .first()
    )
    if not event:
        return None

    anomaly = db.query(AnomalyScore).filter(AnomalyScore.request_id == request_id).first()

    matching_experiment = None
    if event.fault_type or event.is_chaos:
        exp = (
            db.query(ChaosExperiment)
            .filter(ChaosExperiment.fault_type == event.fault_type)
            .order_by(ChaosExperiment.created_at.desc())
            .first()
        )
        if exp:
            matching_experiment = {
                "name": exp.name, "fault_type": exp.fault_type, "params": exp.params,
                "target_path": exp.target_path,
            }

    # Pull a small baseline sample of "normal" sandbox requests on the same path for comparison.
    baseline = (
        db.query(TelemetryEvent)
        .filter(TelemetryEvent.source == "sandbox", TelemetryEvent.path == event.path,
                TelemetryEvent.is_chaos == False)  # noqa: E712
        .order_by(TelemetryEvent.timestamp.desc())
        .limit(10)
        .all()
    )
    baseline_latencies = [b.latency_ms for b in baseline if b.latency_ms is not None]
    baseline_avg = sum(baseline_latencies) / len(baseline_latencies) if baseline_latencies else None

    return {
        "request_id": event.request_id,
        "path": event.path,
        "method": event.method,
        "status_code": event.status_code,
        "latency_ms": event.latency_ms,
        "is_chaos": event.is_chaos,
        "fault_type": event.fault_type,
        "error": event.error,
        "anomaly_score": anomaly.score if anomaly else None,
        "is_anomaly": anomaly.is_anomaly if anomaly else None,
        "matching_experiment": matching_experiment,
        "baseline_avg_latency_ms": baseline_avg,
        "baseline_sample_size": len(baseline_latencies),
    }


def rule_based_explanation(evidence: dict):
    """Deterministic fallback — never hallucinates, only restates evidence (Section 12.2, risk #1)."""
    lines = []
    root_cause = "Unknown — insufficient evidence."
    confidence = "low"

    if evidence["fault_type"] == "latency":
        extra = ""
        if evidence["baseline_avg_latency_ms"]:
            extra = f" (baseline average was {evidence['baseline_avg_latency_ms']:.0f} ms)"
        root_cause = (
            f"Injected latency fault on {evidence['path']}: observed latency of "
            f"{evidence['latency_ms']:.0f} ms{extra}."
        )
        confidence = "high"
    elif evidence["fault_type"] == "error_5xx":
        root_cause = f"Injected 5xx error fault on {evidence['path']}: returned status {evidence['status_code']}."
        confidence = "high"
    elif evidence["fault_type"] == "timeout":
        root_cause = f"Injected timeout fault on {evidence['path']}: request exceeded expected duration."
        confidence = "high"
    elif evidence["fault_type"] == "dependency_failure":
        dep = (evidence.get("matching_experiment") or {}).get("params", {}).get("dependency", "an internal dependency")
        root_cause = f"Injected dependency failure on {evidence['path']}: simulated failure of {dep}."
        confidence = "high"
    elif evidence["is_anomaly"]:
        root_cause = (
            f"Request flagged anomalous by the Isolation Forest model (score={evidence['anomaly_score']:.3f}) "
            f"with no matching configured chaos experiment — recommend manual investigation of {evidence['path']}."
        )
        confidence = "medium"
    elif evidence["error"]:
        root_cause = f"Request raised an unhandled exception: {evidence['error']}"
        confidence = "medium"
    else:
        root_cause = "No fault or anomaly evidence found for this request; it appears to be normal baseline traffic."
        confidence = "low"

    lines.append(root_cause)
    summary = f"RCA for request {evidence['request_id']} on {evidence['method']} {evidence['path']}."
    return summary, root_cause, confidence


def ollama_explanation(evidence: dict):
    """Evidence-linked prompting (Section 12.2, risk #1 mitigation): the model is given ONLY
    the structured evidence dict and asked to explain it — not to invent additional facts."""
    prompt = (
        "You are a site-reliability assistant. You are given ONLY the structured telemetry "
        "evidence below, gathered from a chaos-engineering sandbox. Explain, in 2-4 concise "
        "sentences, the most likely root cause of the observed behaviour. Base your explanation "
        "strictly on the evidence provided — do not invent details that are not present.\n\n"
        f"EVIDENCE (JSON):\n{json.dumps(evidence, indent=2)}\n\n"
        "Respond with plain text only, no markdown."
    )
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if not text:
            raise ValueError("empty response from Ollama")
        return text


@app.post("/rca")
def generate_rca(req: RCARequest):
    db = SessionLocal()
    try:
        evidence = gather_evidence(db, req.request_id)
        if not evidence:
            raise HTTPException(404, "no telemetry found for this request_id")

        generated_by = None
        try:
            root_cause = ollama_explanation(evidence)
            summary = f"RCA for request {evidence['request_id']} on {evidence['method']} {evidence['path']}."
            confidence = "high" if evidence["fault_type"] else "medium"
            generated_by = f"ollama:{OLLAMA_MODEL}"
        except Exception:
            summary, root_cause, confidence = rule_based_explanation(evidence)
            generated_by = "rule-based-fallback"

        report = RCAReport(
            request_id=evidence["request_id"], summary=summary, root_cause=root_cause,
            confidence=confidence, evidence=evidence, generated_by=generated_by,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return {
            "id": report.id, "summary": summary, "root_cause": root_cause,
            "confidence": confidence, "generated_by": generated_by, "evidence": evidence,
        }
    finally:
        db.close()


@app.get("/rca")
def list_rca(limit: int = 50):
    db = SessionLocal()
    try:
        rows = db.query(RCAReport).order_by(RCAReport.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id, "request_id": r.request_id, "summary": r.summary,
                "root_cause": r.root_cause, "confidence": r.confidence,
                "generated_by": r.generated_by, "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        db.close()
