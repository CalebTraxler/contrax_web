from typing import Optional

import stripe

from .config import settings


class PaymentsError(Exception):
    pass


def create_checkout(report_id: str, email: Optional[str]) -> str:
    """Create a Stripe Checkout session for one report. Returns the checkout URL."""
    if not settings.stripe_secret_key:
        raise PaymentsError("STRIPE_SECRET_KEY is not configured")
    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="payment",
        customer_email=email or None,
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": settings.report_price_cents,
                "product_data": {
                    "name": "Contrax quote analysis",
                    "description": "Verdict, red flags, contractor check, and counter-offer",
                },
            },
        }],
        metadata={"report_id": report_id},
        success_url=f"{settings.base_url}/report.html?id={report_id}",
        cancel_url=f"{settings.base_url}/check.html?canceled=1",
    )
    return session.url


def verify_webhook(payload: bytes, sig_header: str):
    """Verify and parse a Stripe webhook. Returns the event or raises PaymentsError."""
    if not settings.stripe_webhook_secret:
        raise PaymentsError("STRIPE_WEBHOOK_SECRET is not configured")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise PaymentsError(f"Invalid webhook: {e}")
