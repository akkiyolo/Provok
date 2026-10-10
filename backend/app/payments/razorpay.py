"""Razorpay: orders, checkout signature verification, webhook verification, idempotent crediting."""
from __future__ import annotations

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, ServiceUnavailable
from backend.app.core.logging import get_logger
from backend.app.core.security import constant_time_equals, hmac_sha256_hex, utcnow
from backend.app.models import AnalyticsEvent, Payment, User
from backend.app.payments.credits import apply_credit

log = get_logger("provok.razorpay")
API = "https://api.razorpay.com/v1"


def get_pack(pack_id: str) -> dict:
    for p in get_settings().credit_packs:
        if p["id"] == pack_id:
            return p
    raise AppError("Unknown credit pack.", code="unknown_pack", status_code=422)


async def create_order(db: AsyncSession, user: User, pack_id: str) -> tuple[Payment, dict]:
    s = get_settings()
    if not s.razorpay_enabled:
        raise ServiceUnavailable("Payments aren't available right now.", code="payments_disabled")
    pack = get_pack(pack_id)
    payment = Payment(id=uuid.uuid4(), user_id=user.id, pack_id=pack["id"], amount_inr=int(pack["amount_inr"]),
                      credits=int(pack["credits"]), status="created", razorpay_order_id="pending")
    body = {"amount": payment.amount_inr * 100, "currency": "INR", "receipt": str(payment.id),
            "notes": {"user_id": str(user.id), "pack_id": pack["id"], "credits": str(pack["credits"])}}
    try:
        async with httpx.AsyncClient(timeout=15, auth=(s.razorpay_key_id, s.razorpay_key_secret)) as client:
            resp = await client.post(f"{API}/orders", json=body)
            resp.raise_for_status()
            order = resp.json()
    except httpx.HTTPError as exc:
        log.error("razorpay_order_failed", error=str(exc)[:200])
        raise ServiceUnavailable("We couldn't start the payment. Please try again.", code="payment_provider") from exc
    payment.razorpay_order_id = order["id"]
    db.add(payment)
    await db.flush()
    return payment, order


def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    secret = get_settings().razorpay_key_secret
    if not secret or not signature:
        return False  # an HMAC under an empty key is forgeable by anyone
    expected = hmac_sha256_hex(secret, f"{order_id}|{payment_id}".encode())
    return constant_time_equals(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = get_settings().razorpay_webhook_secret
    if not secret or not signature:
        return False
    return constant_time_equals(hmac_sha256_hex(secret, raw_body), signature)


async def mark_paid(db: AsyncSession, order_id: str, payment_id: str, *, amount_paise: int | None = None,
                    source: str) -> Payment | None:
    """Idempotent: crediting is keyed on the Razorpay payment id."""
    payment = await db.scalar(select(Payment).where(Payment.razorpay_order_id == order_id).with_for_update(key_share=True))
    if payment is None:
        log.warning("razorpay_unknown_order", order_id=order_id, source=source)
        return None
    if amount_paise is not None and amount_paise != payment.amount_inr * 100:
        log.error("razorpay_amount_mismatch", order_id=order_id, expected=payment.amount_inr * 100, got=amount_paise)
        payment.status = "failed"
        payment.failure_reason = "amount mismatch"
        return payment
    if payment.status == "paid":
        return payment
    payment.status = "paid"
    payment.razorpay_payment_id = payment_id
    payment.paid_at = utcnow()
    await apply_credit(db, payment.user_id, payment.credits, "purchase", ref_id=payment_id,
                       idempotency_key=f"purchase:{order_id}")
    db.add(AnalyticsEvent(name="purchase", user_id=payment.user_id,
                          props={"pack_id": payment.pack_id, "amount_inr": payment.amount_inr, "source": source}))
    log.info("payment_captured", order_id=order_id, credits=payment.credits, source=source)
    return payment


async def mark_failed(db: AsyncSession, order_id: str, reason: str) -> None:
    payment = await db.scalar(select(Payment).where(Payment.razorpay_order_id == order_id).with_for_update(key_share=True))
    if payment is not None and payment.status == "created":
        payment.status = "failed"
        payment.failure_reason = reason[:300]


async def handle_webhook(db: AsyncSession, event: dict) -> str:
    kind = event.get("event", "")
    payload = event.get("payload", {})
    pay = (payload.get("payment") or {}).get("entity") or {}
    order = (payload.get("order") or {}).get("entity") or {}
    if kind in ("payment.captured", "order.paid"):
        order_id = pay.get("order_id") or order.get("id")
        payment_id = pay.get("id")
        if order_id and payment_id and (pay.get("currency", "INR") == "INR"):
            await mark_paid(db, order_id, payment_id, amount_paise=pay.get("amount"), source="webhook")
        return "processed"
    if kind == "payment.failed":
        if pay.get("order_id"):
            await mark_failed(db, pay["order_id"], str(pay.get("error_description") or "failed"))
        return "processed"
    return "ignored"
