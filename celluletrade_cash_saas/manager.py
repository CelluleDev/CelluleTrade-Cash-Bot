"""
Point d'entrée de la plateforme CelluleTrade (multi-clients, 100% Telegram).

Lancement local (test) :
    python -m celluletrade_cash_saas.manager

Variables d'environnement requises (voir celluletrade_cash_saas/config.py) :
    TELEGRAM_BOT_TOKEN, ENCRYPTION_KEY, DATABASE_URL (optionnel, sqlite par défaut)
    Optionnel pour les paiements : STRIPE_SECRET_KEY, STRIPE_PRICE_MONTHLY,
    STRIPE_PRICE_LIFETIME, TELEGRAM_BOT_USERNAME

Pour tester l'interface : démarrez ce script, puis ouvrez une conversation
avec votre bot sur Telegram et envoyez /start.
"""

import logging

from celluletrade_cash_saas import config, stripe_billing
from celluletrade_cash_saas.db import init_db
from celluletrade_cash_saas.monitoring import MonitoringSupervisor
from celluletrade_cash_saas.telegram_bot import build_application

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _poll_stripe_job(context):
    stripe_billing.poll_pending_subscriptions()


async def _post_init(application):
    """Démarre le superviseur de surveillance Binance/Rise en arrière-plan."""
    supervisor = MonitoringSupervisor()
    application.bot_data["monitoring_supervisor"] = supervisor
    application.create_task(supervisor.run())


async def _post_shutdown(application):
    supervisor = application.bot_data.get("monitoring_supervisor")
    if supervisor:
        await supervisor.stop()


def main():
    init_db()
    application = build_application()
    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    if stripe_billing.is_configured():
        application.job_queue.run_repeating(
            _poll_stripe_job,
            interval=config.STRIPE_POLL_INTERVAL,
            first=10,
        )
        logger.info("Vérification périodique Stripe activée (toutes les %ss).", config.STRIPE_POLL_INTERVAL)
    else:
        logger.info("Stripe non configuré : les boutons de paiement seront masqués.")

    logger.info("Bot démarré (long polling). Ouvrez Telegram et envoyez /start à votre bot.")
    application.run_polling()


if __name__ == "__main__":
    main()
