"""Checkout API — BandAid demo target with chaos injection."""

from __future__ import annotations

import random
import threading
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from sqlalchemy import text

from app.chaos import FaultType, chaos
from app.database import Order, PoolExhaustedError, Product, init_db, session_scope
from app.log_buffer import append_log, get_logs
from app.logging_config import setup_logging

setup_logging()

app = FastAPI(title="checkout-api", version="0.1.0")

_lock = threading.Lock()
_request_count = 0
_error_count = 0
_checkout_latency_ms: list[float] = []


@app.on_event("startup")
def startup() -> None:
    init_db()
    append_log("INFO", "checkout-api started")


def _record_request(ok: bool, latency_ms: float) -> None:
    with _lock:
        global _request_count, _error_count
        _request_count += 1
        if not ok:
            _error_count += 1
        _checkout_latency_ms.append(latency_ms)
        if len(_checkout_latency_ms) > 1000:
            _checkout_latency_ms.pop(0)


@app.get("/health")
def health() -> dict[str, Any]:
    if chaos.active_fault == FaultType.POOL_EXHAUSTION:
        try:
            with session_scope() as db:
                db.execute(text("SELECT 1"))
            chaos.clear()
            append_log("INFO", "Pool recovered — auto-cleared pool_exhaustion fault")
        except Exception as exc:
            append_log("ERROR", "Health check failed: connection pool exhausted")
            return {
                "status": "unhealthy",
                "severity": "critical",
                "pool_exhausted": True,
                "held_connections": len(chaos.held_connections),
                "reason": f"database pool exhausted: {exc}",
            }
    if chaos.active_fault == FaultType.BAD_CONFIG and random.random() < chaos.error_rate:
        append_log("ERROR", "Health check degraded: bad config deploy")
        return {
            "status": "unhealthy",
            "severity": "high",
            "active_fault": chaos.active_fault.value,
            "reason": "elevated error rate after config deploy",
        }
    if chaos.active_fault == FaultType.PII_LEAK:
        return {
            "status": "unhealthy",
            "severity": "high",
            "active_fault": chaos.active_fault.value,
            "reason": "error storm with potential PII exposure",
        }
    return {"status": "healthy", "severity": "none", "active_fault": None}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    with _lock:
        req_count = _request_count
        err_count = _error_count
        latencies = list(_checkout_latency_ms)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    pool_in_use = len(chaos.held_connections)
    lines = [
        "# HELP checkout_requests_total Total checkout requests",
        "# TYPE checkout_requests_total counter",
        f"checkout_requests_total {req_count}",
        "# HELP checkout_errors_total Total checkout errors",
        "# TYPE checkout_errors_total counter",
        f"checkout_errors_total {err_count}",
        "# HELP checkout_latency_ms_avg Average checkout latency",
        "# TYPE checkout_latency_ms_avg gauge",
        f"checkout_latency_ms_avg {avg_latency:.2f}",
        "# HELP db_pool_connections_in_use DB pool connections held",
        "# TYPE db_pool_connections_in_use gauge",
        f"db_pool_connections_in_use {pool_in_use}",
        "# HELP chaos_error_rate Injected error rate",
        "# TYPE chaos_error_rate gauge",
        f"chaos_error_rate {chaos.error_rate}",
    ]
    return "\n".join(lines) + "\n"


@app.get("/logs")
def logs(limit: int = 100, level: str | None = None) -> dict[str, Any]:
    entries = get_logs(limit=limit, level=level)
    return {"logs": entries, "count": len(entries)}


@app.get("/products")
def list_products() -> list[dict[str, Any]]:
    try:
        with session_scope() as db:
            products = db.query(Product).all()
            return [{"id": p.id, "name": p.name, "price": p.price, "stock": p.stock} for p in products]
    except PoolExhaustedError:
        raise HTTPException(status_code=503, detail="database pool exhausted")


@app.post("/checkout")
def checkout(product_id: int, customer_email: str, quantity: int = 1) -> dict[str, Any]:
    start = time.perf_counter()
    ok = True
    try:
        if chaos.active_fault == FaultType.BAD_CONFIG and random.random() < chaos.error_rate:
            raise HTTPException(status_code=500, detail="checkout_failed_bad_config")

        if chaos.active_fault == FaultType.POOL_EXHAUSTION:
            raise HTTPException(status_code=503, detail="database pool exhausted")

        if chaos.active_fault == FaultType.PII_LEAK:
            chaos.leak_count += 1
            leaked = {
                "customer_email": customer_email,
                "phone": "+1-555-0199",
                "ssn_last4": "4242",
                "error": "payment_processor_timeout",
            }
            append_log(
                "ERROR",
                f"Checkout failed — leaked customer data: {leaked}",
                pii_exposed=True,
                customer=customer_email,
            )
            raise HTTPException(status_code=500, detail=f"processor error: {leaked}")

        with session_scope() as db:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail="product not found")
            if product.stock < quantity:
                raise HTTPException(status_code=409, detail="insufficient stock")
            product.stock -= quantity
            order = Order(
                customer_email=customer_email,
                product_id=product_id,
                quantity=quantity,
                status="confirmed",
            )
            db.add(order)
            db.flush()
            append_log("INFO", "Checkout completed", order_id=order.id, product_id=product_id)
            return {"order_id": order.id, "status": "confirmed", "total": product.price * quantity}
    except PoolExhaustedError:
        ok = False
        raise HTTPException(status_code=503, detail="database pool exhausted")
    except HTTPException:
        ok = False
        raise
    finally:
        latency = (time.perf_counter() - start) * 1000
        _record_request(ok, latency)


@app.get("/chaos/status")
def chaos_status() -> dict[str, Any]:
    return chaos.to_dict()


@app.post("/chaos/clear")
def clear_fault() -> dict[str, Any]:
    previous = chaos.active_fault.value if chaos.active_fault else None
    chaos.clear()
    append_log("INFO", "Chaos faults cleared", previous_fault=previous)
    return {"cleared": True, "previous_fault": previous}


@app.post("/chaos/{fault}")
def inject_fault(fault: str) -> dict[str, Any]:
    try:
        fault_type = FaultType(fault)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown fault: {fault}") from exc
    chaos.activate(fault_type)
    append_log("WARN", f"Chaos fault activated: {fault}", fault=fault)
    return {"activated": fault, "state": chaos.to_dict()}


@app.post("/chaos/simulate-traffic")
def simulate_traffic(requests: int = 20) -> dict[str, Any]:
    """Generate checkout traffic to trigger active faults."""
    results = {"success": 0, "errors": 0}
    for i in range(requests):
        try:
            checkout(product_id=1, customer_email=f"user{i}@example.com")
            results["success"] += 1
        except HTTPException:
            results["errors"] += 1
    return results
