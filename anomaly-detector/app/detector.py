"""
ML-based Anomaly Detector (FR-05).

Uses scikit-learn's IsolationForest — a lightweight classical algorithm
(Section 9: "not a deep learning model", no GPU required) trained on
sandbox telemetry to separate normal request behaviour from chaos-injected
or otherwise abnormal behaviour.

Endpoints:
  POST /train  — (re)train the model on all sandbox telemetry collected so far
  POST /score  — score the most recent N sandbox telemetry rows and persist
                 an AnomalyScore for each one
  GET  /model  — current model metadata
"""
import sys
import time
import joblib
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sklearn.ensemble import IsolationForest

sys.path.insert(0, "/app")
from common.db import SessionLocal, TelemetryEvent, AnomalyScore, init_db  # noqa: E402

MODEL_PATH = "/data/isolation_forest.joblib"
app = FastAPI(title="ShadowAPM Anomaly Detector")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_model_state = {"model": None, "version": None, "trained_on": 0}


def featurize(events):
    """Turn telemetry rows into a numeric feature matrix.

    Features: latency_ms, status_code bucket (0 ok / 1 4xx / 2 5xx-or-null), error flag.
    Kept deliberately simple and explainable for RCA grounding (see rca-agent).
    """
    rows = []
    for e in events:
        status = e.status_code or 0
        bucket = 0 if 200 <= status < 400 else (1 if 400 <= status < 500 else 2)
        rows.append([e.latency_ms or 0.0, bucket, 1.0 if e.error else 0.0])
    return np.array(rows, dtype=float)


@app.on_event("startup")
def startup():
    init_db()
    try:
        _model_state["model"] = joblib.load(MODEL_PATH)
        _model_state["version"] = "loaded-from-disk"
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok", "service": "anomaly-detector"}


@app.get("/model")
def model_info():
    return {"loaded": _model_state["model"] is not None, "version": _model_state["version"],
            "trained_on_rows": _model_state["trained_on"]}


@app.post("/train")
def train(contamination: float = 0.1):
    db = SessionLocal()
    try:
        events = db.query(TelemetryEvent).filter(TelemetryEvent.source == "sandbox").all()
        if len(events) < 20:
            return {"status": "not_enough_data", "rows": len(events), "minimum_required": 20}

        X = featurize(events)
        model = IsolationForest(
            n_estimators=150, contamination=contamination, random_state=42
        )
        model.fit(X)
        joblib.dump(model, MODEL_PATH)

        version = f"v{int(time.time())}"
        _model_state.update(model=model, version=version, trained_on=len(events))
        return {"status": "trained", "rows": len(events), "version": version}
    finally:
        db.close()


@app.post("/score")
def score(limit: int = 200):
    if _model_state["model"] is None:
        return {"status": "no_model", "detail": "call /train first"}

    db = SessionLocal()
    try:
        events = (
            db.query(TelemetryEvent)
            .filter(TelemetryEvent.source == "sandbox")
            .order_by(TelemetryEvent.timestamp.desc())
            .limit(limit)
            .all()
        )
        if not events:
            return {"status": "no_data"}

        X = featurize(events)
        raw_scores = _model_state["model"].decision_function(X)   # higher = more normal
        predictions = _model_state["model"].predict(X)             # -1 = anomaly, 1 = normal

        written = 0
        for event, raw_score, pred in zip(events, raw_scores, predictions):
            existing = db.query(AnomalyScore).filter(AnomalyScore.request_id == event.request_id).first()
            if existing:
                continue
            db.add(AnomalyScore(
                request_id=event.request_id,
                score=float(raw_score),
                is_anomaly=bool(pred == -1),
                model_version=_model_state["version"],
            ))
            written += 1
        db.commit()
        anomalies = sum(1 for p in predictions if p == -1)
        return {"status": "scored", "rows_scored": len(events), "new_scores_written": written, "anomalies_found": int(anomalies)}
    finally:
        db.close()
