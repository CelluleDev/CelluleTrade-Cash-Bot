"""
Configuration de la plateforme multi-clients (bot Telegram unique).

Toutes les valeurs viennent des variables d'environnement (.env en local,
variables d'environnement du serveur en production). Aucun nom de domaine
n'est nécessaire : le bot fonctionne en long polling et Stripe est vérifié
par scrutation périodique (pas de webhook).
"""

import os


def _normalize_db_url(url: str) -> str:
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Telegram chat_id de Mickael : devient automatiquement administrateur
# au premier /start (peut aussi être laissé vide et promu via la BDD).
ADMIN_TELEGRAM_CHAT_ID = os.getenv("ADMIN_TELEGRAM_CHAT_ID")

# --- Base de données ---
DATABASE_URL = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///celluletrade_cash_saas.db"))

# --- Chiffrement des clés API stockées en base ---
# Générer une fois avec :
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# --- Stripe ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_MONTHLY = os.getenv("STRIPE_PRICE_MONTHLY")    # abonnement 5€/mois
STRIPE_PRICE_LIFETIME = os.getenv("STRIPE_PRICE_LIFETIME")  # paiement unique 300€

# URL de redirection après paiement Stripe : pas de site -> on renvoie
# simplement vers la conversation Telegram du bot.
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")

# Intervalle (secondes) de vérification des paiements Stripe en attente
STRIPE_POLL_INTERVAL = int(os.getenv("STRIPE_POLL_INTERVAL", "300"))

# Contact affiché dans le menu d'aide du bot (ex: @mickael ou une adresse email)
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "")

# --- Surveillance multi-clients (Binance / Rise) ---
# Mêmes paramètres que main.py, repris ici pour la version multi-clients.

BINANCE_API_BASE_URL = os.getenv("BINANCE_API_BASE_URL", "https://api.binance.com")
BINANCE_WS_API_URL = os.getenv(
    "BINANCE_WS_API_URL",
    "wss://ws-api.binance.com:443/ws-api/v3?returnRateLimits=false",
)
BINANCE_FALLBACK_INTERVAL = int(os.getenv("BINANCE_FALLBACK_INTERVAL", "900"))
BINANCE_NOTIFY_FIRST_DEPOSIT = os.getenv("BINANCE_NOTIFY_FIRST_DEPOSIT", "true").lower() == "true"

# Websocket Alchemy (réseau Arbitrum) pour la surveillance des wallets Rise
ALCHEMY_WS_URL = os.getenv("ALCHEMY_WS_URL")

# Intervalle (secondes) entre deux scans de la base pour démarrer/arrêter
# les tâches de surveillance par client
MONITORING_POLL_INTERVAL = int(os.getenv("MONITORING_POLL_INTERVAL", "60"))
