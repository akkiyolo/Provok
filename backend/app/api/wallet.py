"""Wallet + payments routes."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from backend.app.api.deps import DB, CurrentUser, VerifiedUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Forbidden
from backend.app.core.logging import get_logger
from backend.app.core.ratelimit import enforce
from backend.app.models import CreditLedger, Payment
from backend.app.payments import razorpay as rzp
from backend.app.services import flags

router = APIRouter()
log = get_logger("provok.api.wallet")


@router.get("/me/wallet")
async def wallet(user: CurrentUser, db: DB) -> dict:
    s = get_settings()
    ledger = (await db.scalars(select(CreditLedger).where(CreditLedger.user_id == user.id)
                               .order_by(desc(CreditLedger.created_at)).limit(50))).all()
    payments = (await db.scalars(select(Payment).where(Payment.user_id == user.id)
                                 .order_by(desc(Payment.created_at)).limit(20))).all()
    return {
        "credits": user.credits,
        "free_ai_debates_total": s.free_ai_debates,
        "free_ai_debates_left": max(0, s.free_ai_debates - user.free_ai_debates_used),
        "costs": {"standard": s.standard_credit_cost, "flagship": s.flagship_credit_cost,
                  "free_covers_flagship": s.free_debates_cover_flagship},
        "packs": s.credit_packs,
        "payments_enabled": s.razorpay_enabled and await flags.is_enabled(flags.PAYMENTS),
        "razorpay_key_id": s.razorpay_key_id or None,
        "history": [{"delta": e.delta, "reason": e.reason, "balance_after": e.balance_after, "ref_id": e.ref_id,
                     "created_at": e.created_at} for e in ledger],
        "payments": [{"id": str(p.id), "pack_id": p.pack_id, "amount_inr": p.amount_inr, "credits": p.credits,
                      "status": p.status, "created_at": p.created_at} for p in payments],
    }


class OrderIn(BaseModel):
    pack_id: str = Field(min_length=1, max_length=32)


@router.post("/payments/order")
async def create_order(body: OrderIn, user: VerifiedUser, db: DB) -> dict:
    await enforce("payment_order", str(user.id), "10/3600")
    if not await flags.is_enabled(flags.PAYMENTS):
        raise Forbidden("Payments are paused for a moment.", code="payments_paused")
    payment, order = await rzp.create_order(db, user, body.pack_id)
    await db.commit()
    s = get_settings()
    return {"order_id": order["id"], "amount": order["amount"], "currency": order["currency"],
            "key_id": s.razorpay_key_id, "name": s.app_name, "description": f"{payment.credits} Provok credits",
            "prefill": {"email": user.email, "name": user.display_name}, "payment_id": str(payment.id)}


class VerifyIn(BaseModel):
    razorpay_order_id: str = Field(max_length=64)
    razorpay_payment_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=128)


@router.post("/payments/verify")
async def verify_payment(body: VerifyIn, user: CurrentUser, db: DB) -> dict:
    """Called by the browser after Checkout succeeds. The webhook is the backstop if this never arrives."""
    if not rzp.verify_checkout_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature):
        raise AppError("Payment verification failed.", code="bad_signature", status_code=400)
    payment = await db.scalar(select(Payment).where(Payment.razorpay_order_id == body.razorpay_order_id))
    if payment is None or payment.user_id != user.id:
        raise AppError("Unknown payment.", code="unknown_payment", status_code=404)
    await rzp.mark_paid(db, body.razorpay_order_id, body.razorpay_payment_id, source="checkout")
    await db.commit()
    await db.refresh(user)
    return {"ok": True, "credits": user.credits}


@router.post("/payments/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request, db: DB) -> dict:
    raw = await request.body()
    if not rzp.verify_webhook_signature(raw, request.headers.get("x-razorpay-signature", "")):
        log.warning("razorpay_webhook_bad_signature")
        raise AppError("Invalid signature.", code="bad_signature", status_code=400)
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("Invalid payload.", code="bad_payload", status_code=400) from exc
    result = await rzp.handle_webhook(db, event)
    await db.commit()
    return {"status": result}
