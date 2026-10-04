"""
ShadowAPM Reverse Proxy (FR-01, FR-04, NFR-01, NFR-02).

Sits in front of the real production API. For every incoming request it:
  1. Forwards the request to the production sample-api and returns that
     response to the caller IMMEDIATELY — the caller never waits on anything
     below this line. This guarantees NFR-01 (negligible added latency).
  2. Fires an async background task (does not block the response) that:
       a. Sanitises the request body/headers (PII sanitiser, FR-02)
       b. Mirrors the sanitised copy to the sandbox replica
       c. Records telemetry for both the production and sandbox legs

Because step 2 runs after the response has already been sent, a slow or
failing sandbox can NEVER affect a real user (NFR-02: full production
isolation).
"""
import os
import sys
import time
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

sys.path.insert(0, "/app")
from common.db import SessionLocal, TelemetryEvent, init_db, new_id  # noqa: E402
from common.pii import sanitize, sanitize_headers  # noqa: E402

PRODUCTION_URL = os.environ.get("PRODUCTION_URL", "http://sample-api:8000")
SANDBOX_URL = os.environ.get("SANDBOX_URL", "http://sandbox-api:8000")

app = FastAPI(title="ShadowAPM Traffic Mirroring Proxy")
client = httpx.AsyncClient(timeout=10.0)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "proxy"}


async def mirror_to_sandbox(request_id: str, method: str, path: str, body: dict, headers: dict):
    """Runs in the background, after the real response has already gone out."""
    clean_body = sanitize(body) if body is not None else None
    clean_headers = sanitize_headers(headers)
    clean_headers["x-shadowapm-request-id"] = request_id
    clean_headers.pop("host", None)
    clean_headers.pop("content-length", None)

    start = time.time()
    db = SessionLocal()
    try:
        resp = await client.request(method, f"{SANDBOX_URL}{path}", json=clean_body, headers=clean_headers)
        db.add(TelemetryEvent(
            request_id=request_id, source="sandbox", method=method, path=path,
            status_code=resp.status_code, latency_ms=(time.time() - start) * 1000,
        ))
    except Exception as e:
        db.add(TelemetryEvent(
            request_id=request_id, source="sandbox", method=method, path=path,
            status_code=None, latency_ms=(time.time() - start) * 1000, error=str(e),
        ))
    finally:
        db.commit()
        db.close()


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    request_id = new_id()
    method = request.method
    full_path = f"/{path}"
    body = None
    if method in ("POST", "PUT"):
        try:
            body = await request.json()
        except Exception:
            body = None

    # --- 1. Serve the real user from production, synchronously, first. ---
    start = time.time()
    try:
        prod_resp = await client.request(
            method, f"{PRODUCTION_URL}{full_path}",
            json=body,
            headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")},
        )
        latency = (time.time() - start) * 1000
        db = SessionLocal()
        db.add(TelemetryEvent(
            request_id=request_id, source="production", method=method, path=full_path,
            status_code=prod_resp.status_code, latency_ms=latency,
        ))
        db.commit()
        db.close()

        # --- 2. Fire-and-forget mirror to sandbox. Never awaited by the caller. ---
        import asyncio
        asyncio.create_task(mirror_to_sandbox(request_id, method, full_path, body, dict(request.headers)))

        return Response(
            content=prod_resp.content,
            status_code=prod_resp.status_code,
            headers={"content-type": prod_resp.headers.get("content-type", "application/json"),
                     "x-shadowapm-request-id": request_id},
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "production_unreachable", "detail": str(e)})
