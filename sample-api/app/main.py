"""
Sample production API (FR target system).

Simulates a small e-commerce "orders" backend that depends on an internal
"inventory" and "payment" call for each request — representative of the kind
of multi-dependency microservice ShadowAPM is designed to test, per the
problem statement in Section 8 of the Review-II document.

This service represents REAL production traffic. ShadowAPM never injects
faults here — it only mirrors a copy of the traffic elsewhere (see proxy/).
"""
import asyncio
import random
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="ShadowAPM Sample API (Production)")


async def call_inventory_service(sku: str):
    await asyncio.sleep(random.uniform(0.01, 0.05))
    return {"sku": sku, "in_stock": random.choice([True, True, True, False])}


async def call_payment_service(amount: float):
    await asyncio.sleep(random.uniform(0.02, 0.08))
    return {"status": "authorized", "amount": amount}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sample-api"}


@app.post("/orders")
async def create_order(request: Request):
    body = await request.json()
    sku = body.get("sku", "SKU-0000")
    amount = float(body.get("amount", 0))

    inventory = await call_inventory_service(sku)
    if not inventory["in_stock"]:
        return JSONResponse(status_code=409, content={"error": "out_of_stock", "sku": sku})

    payment = await call_payment_service(amount)
    return {"order_id": f"ORD-{random.randint(10000,99999)}", "inventory": inventory, "payment": payment}


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    return {"order_id": order_id, "status": random.choice(["shipped", "processing", "delivered"])}
