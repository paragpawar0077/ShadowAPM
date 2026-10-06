"""
Sandbox replica API (FR-03: isolated fault injection).

Identical business logic to sample-api, but every request first passes
through the chaos hook, which checks for an active ChaosExperiment matching
the request path and, if found, injects the configured fault (latency,
5xx error, timeout, or a failing internal dependency) BEFORE the real logic
runs.

This is the ONLY service where faults are ever injected. It never receives
real user traffic directly — it only receives mirrored copies forwarded by
the proxy (see NFR-02: full production isolation).
"""
import asyncio
import random
import sys
import time
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, "/app")
from common.db import SessionLocal, ChaosExperiment, TelemetryEvent, init_db, new_id  # noqa: E402

app = FastAPI(title="ShadowAPM Sandbox Replica")

_cache = {"experiments": [], "fetched_at": 0}
CACHE_TTL_SECONDS = 5


def get_active_experiments():
    now = time.time()
    if now - _cache["fetched_at"] > CACHE_TTL_SECONDS:
        db = SessionLocal()
        try:
            _cache["experiments"] = db.query(ChaosExperiment).filter(ChaosExperiment.active == True).all()  # noqa: E712
            _cache["fetched_at"] = now
        finally:
            db.close()
    return _cache["experiments"]


def match_experiment(path: str):
    for exp in get_active_experiments():
        if exp.target_path == "*" or path.startswith(exp.target_path):
            return exp
    return None


async def apply_chaos(path: str):
    """Returns (fault_type, forced_response) — forced_response is None if the request should proceed normally."""
    exp = match_experiment(path)
    if not exp:
        return None, None

    params = exp.params or {}
    if exp.fault_type == "latency":
        await asyncio.sleep(params.get("delay_ms", 500) / 1000)
        return "latency", None

    if exp.fault_type == "error_5xx":
        return "error_5xx", JSONResponse(
            status_code=params.get("status", 503),
            content={"error": "sandbox_chaos_injected", "fault": "error_5xx"},
        )

    if exp.fault_type == "timeout":
        await asyncio.sleep(params.get("delay_ms", 5000) / 1000)
        return "timeout", JSONResponse(status_code=504, content={"error": "sandbox_chaos_timeout"})

    if exp.fault_type == "dependency_failure":
        # Simulate the internal payment/inventory dependency itself failing.
        return "dependency_failure", JSONResponse(
            status_code=502, content={"error": "sandbox_dependency_failure", "dependency": params.get("dependency", "payment-service")}
        )

    return None, None


async def call_inventory_service(sku: str):
    await asyncio.sleep(random.uniform(0.01, 0.05))
    return {"sku": sku, "in_stock": random.choice([True, True, True, False])}


async def call_payment_service(amount: float):
    await asyncio.sleep(random.uniform(0.02, 0.08))
    return {"status": "authorized", "amount": amount}


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sandbox-api"}


@app.post("/orders")
async def create_order(request: Request):
    start = time.time()
    request_id = request.headers.get("x-shadowapm-request-id", new_id())
    fault_type, forced = await apply_chaos("/orders")

    db = SessionLocal()
    try:
        if forced is not None:
            db.add(TelemetryEvent(
                request_id=request_id, source="sandbox", method="POST", path="/orders",
                status_code=forced.status_code, latency_ms=(time.time() - start) * 1000,
                is_chaos=True, fault_type=fault_type,
            ))
            db.commit()
            return forced

        body = await request.json()
        sku = body.get("sku", "SKU-0000")
        amount = float(body.get("amount", 0))

        inventory = await call_inventory_service(sku)
        if not inventory["in_stock"]:
            resp = JSONResponse(status_code=409, content={"error": "out_of_stock", "sku": sku})
            db.add(TelemetryEvent(
                request_id=request_id, source="sandbox", method="POST", path="/orders",
                status_code=409, latency_ms=(time.time() - start) * 1000,
                is_chaos=fault_type is not None, fault_type=fault_type,
            ))
            db.commit()
            return resp

        payment = await call_payment_service(amount)
        result = {"order_id": f"ORD-{random.randint(10000,99999)}", "inventory": inventory, "payment": payment}
        db.add(TelemetryEvent(
            request_id=request_id, source="sandbox", method="POST", path="/orders",
            status_code=200, latency_ms=(time.time() - start) * 1000,
            is_chaos=fault_type is not None, fault_type=fault_type,
        ))
        db.commit()
        return result
    except Exception as e:
        db.add(TelemetryEvent(
            request_id=request_id, source="sandbox", method="POST", path="/orders",
            status_code=500, latency_ms=(time.time() - start) * 1000,
            is_chaos=fault_type is not None, fault_type=fault_type, error=str(e),
        ))
        db.commit()
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(e)})
    finally:
        db.close()
