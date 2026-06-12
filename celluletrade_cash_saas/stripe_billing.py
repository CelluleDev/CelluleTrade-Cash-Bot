"""
Paiements Stripe (5€/mois ou 300€ paiement unique).

Pas de webhook : on crée des sessions Stripe Checkout et on vérifie leur
statut par scrutation périodique (voir `poll_pending_subscriptions`),
appelée régulièrement par `manager.py`. Cela évite d'avoir besoin d'un
nom de domaine ou d'un point d'entrée HTTP public.
"""

import logging
from datetime import datetime, timedelta

import stripe

from celluletrade_cash_saas import config
from celluletrade_cash_saas.db import session_scope
from celluletrade_cash_saas.models import Subscription, User

logger = logging.getLogger(__name__)

stripe.api_key = config.STRIPE_SECRET_KEY


def is_configured() -> bool:
    return bool(config.STRIPE_SECRET_KEY and config.STRIPE_PRICE_MONTHLY and config.STRIPE_PRICE_LIFETIME)


def _bot_redirect_url() -> str:
    """Pas de site web : on renvoie l'utilisateur vers la conversation Telegram."""
    if config.TELEGRAM_BOT_USERNAME:
        return f"https://t.me/{config.TELEGRAM_BOT_USERNAME}"
    return "https://t.me"


def create_checkout_session(user: User, plan: str):
    """Crée une session Stripe Checkout et renvoie (url, session_id)."""

    if plan == Subscription.PLAN_MONTHLY:
        mode = "subscription"
        price_id = config.STRIPE_PRICE_MONTHLY
    elif plan == Subscription.PLAN_LIFETIME:
        mode = "payment"
        price_id = config.STRIPE_PRICE_LIFETIME
    else:
        raise ValueError(f"Plan inconnu: {plan}")

    redirect_url = _bot_redirect_url()

    session = stripe.checkout.Session.create(
        mode=mode,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=redirect_url,
        cancel_url=redirect_url,
        client_reference_id=str(user.id),
        metadata={"cellule_user_id": str(user.id), "cellule_plan": plan},
    )

    return session.url, session.id


def poll_pending_subscriptions():
    """
    À appeler périodiquement (ex: toutes les `STRIPE_POLL_INTERVAL` secondes).

    - Active les abonnements/accès dont le paiement Stripe est confirmé.
    - Met à jour la date de fin de période des abonnements mensuels actifs
      et désactive ceux qui ont été annulés/expirés côté Stripe.
    """
    if not is_configured():
        return

    _check_pending_checkouts()
    _refresh_active_monthly_subscriptions()


def _check_pending_checkouts():
    with session_scope() as session:
        pending = (
            session.query(Subscription)
            .filter(
                Subscription.status == Subscription.STATUS_PENDING,
                Subscription.stripe_checkout_session_id.isnot(None),
            )
            .all()
        )
        session_ids = [(sub.id, sub.stripe_checkout_session_id) for sub in pending]

    for sub_id, checkout_session_id in session_ids:
        try:
            checkout = stripe.checkout.Session.retrieve(checkout_session_id)
        except Exception:
            logger.exception("Erreur lors de la vérification de la session Stripe %s", checkout_session_id)
            continue

        if checkout.payment_status != "paid":
            continue

        with session_scope() as session:
            sub = session.get(Subscription, sub_id)
            if not sub or sub.status != Subscription.STATUS_PENDING:
                continue

            sub.status = Subscription.STATUS_ACTIVE
            sub.stripe_customer_id = checkout.customer

            if sub.plan == Subscription.PLAN_MONTHLY:
                sub.stripe_subscription_id = checkout.subscription
                if checkout.subscription:
                    try:
                        stripe_sub = stripe.Subscription.retrieve(checkout.subscription)
                        sub.current_period_end = datetime.utcfromtimestamp(stripe_sub.current_period_end)
                    except Exception:
                        logger.exception("Erreur récupération abonnement Stripe %s", checkout.subscription)

            logger.info("Abonnement %s activé (plan=%s)", sub_id, sub.plan)


def _refresh_active_monthly_subscriptions():
    with session_scope() as session:
        active_monthly = (
            session.query(Subscription)
            .filter(
                Subscription.status == Subscription.STATUS_ACTIVE,
                Subscription.plan == Subscription.PLAN_MONTHLY,
                Subscription.stripe_subscription_id.isnot(None),
            )
            .all()
        )
        items = [(sub.id, sub.stripe_subscription_id) for sub in active_monthly]

    for sub_id, stripe_sub_id in items:
        try:
            stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
        except Exception:
            logger.exception("Erreur lors de la vérification de l'abonnement Stripe %s", stripe_sub_id)
            continue

        with session_scope() as session:
            sub = session.get(Subscription, sub_id)
            if not sub:
                continue

            if stripe_sub.status in ("active", "trialing"):
                sub.current_period_end = datetime.utcfromtimestamp(stripe_sub.current_period_end)
            elif stripe_sub.status in ("canceled", "unpaid", "incomplete_expired"):
                sub.status = Subscription.STATUS_CANCELED
                logger.info("Abonnement %s désactivé (statut Stripe=%s)", sub_id, stripe_sub.status)
