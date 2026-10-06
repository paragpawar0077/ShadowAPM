"""
Chaos Injection Engine — control plane (FR-03, FR-07).

Provides a REST API to create, list, toggle and delete chaos experiments.
The sandbox-api reads active experiments from the shared database (see
sandbox-api/app/main.py) — this service is purely the management/CRUD
surface used by the dashboard and by CI/CD pipelines (FR-07: CI/CD-integrable
chaos scenarios via exportable experiment configs).
"""
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, "/app")
from common.db import SessionLocal, ChaosExperiment, init_db  # noqa: E402

app = FastAPI(title="ShadowAPM Chaos Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

VALID_FAULTS = {"latency", "error_5xx", "timeout", "dependency_failure"}


class ExperimentIn(BaseModel):
    name: str
    target_path: str = "*"
    fault_type: str
    params: dict = {}
    active: bool = True


class ExperimentPatch(BaseModel):
    active: Optional[bool] = None
    params: Optional[dict] = None


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "chaos-engine"}


@app.get("/experiments")
def list_experiments():
    db = SessionLocal()
    try:
        rows = db.query(ChaosExperiment).order_by(ChaosExperiment.created_at.desc()).all()
        return [
            {
                "id": r.id, "name": r.name, "target_path": r.target_path,
                "fault_type": r.fault_type, "params": r.params, "active": r.active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.post("/experiments")
def create_experiment(exp: ExperimentIn):
    if exp.fault_type not in VALID_FAULTS:
        raise HTTPException(400, f"fault_type must be one of {sorted(VALID_FAULTS)}")
    db = SessionLocal()
    try:
        row = ChaosExperiment(
            name=exp.name, target_path=exp.target_path, fault_type=exp.fault_type,
            params=exp.params, active=exp.active,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "name": row.name, "active": row.active}
    finally:
        db.close()


@app.patch("/experiments/{experiment_id}")
def patch_experiment(experiment_id: str, patch: ExperimentPatch):
    db = SessionLocal()
    try:
        row = db.query(ChaosExperiment).filter(ChaosExperiment.id == experiment_id).first()
        if not row:
            raise HTTPException(404, "experiment not found")
        if patch.active is not None:
            row.active = patch.active
        if patch.params is not None:
            row.params = patch.params
        db.commit()
        return {"id": row.id, "active": row.active}
    finally:
        db.close()


@app.delete("/experiments/{experiment_id}")
def delete_experiment(experiment_id: str):
    db = SessionLocal()
    try:
        row = db.query(ChaosExperiment).filter(ChaosExperiment.id == experiment_id).first()
        if not row:
            raise HTTPException(404, "experiment not found")
        db.delete(row)
        db.commit()
        return {"deleted": experiment_id}
    finally:
        db.close()
