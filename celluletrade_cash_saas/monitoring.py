"""
Surveillance Binance / Rise par client.

Reprend la logique de `main.py` (websocket Binance + fallback REST,
websocket Rise/Alchemy) mais de façon multi-clients : une tâche par
client et par service (Binance / Rise), démarrée/arrêtée dynamiquement
selon les abonnements actifs et les identifiants configurés en base.

Le "dernier dépôt vu" (anti-doublons) est stocké en base
(`ApiCredentials.last_binance_txid` / `last_rise_txid`) au lieu de Redis,
puisque chaque client a ses propres identifiants.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal
from urllib.parse import urlencode

import requests
import websockets

from celluletrade_cash_saas import config
from celluletrade_cash_saas.db import session_scope
from celluletrade_cash_saas.models import ApiCredentials, Subscription, User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Telegram
# ---------------------------------------------------------

def send_telegram(chat_id, message: str) -> bool:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()

        if not result.get("ok"):
            logger.warning("Telegram refusé (chat_id=%s) : %s", chat_id, result)
            return False

        return True

    except Exception as e:
        logger.warning("Telegram erreur (chat_id=%s) : %s", chat_id, e)
        return False


# ---------------------------------------------------------
# Stockage anti-doublons (en base, par client)
# ---------------------------------------------------------

def get_last_binance_txid(user_id: int):
    with session_scope() as session:
        creds = session.query(ApiCredentials).filter_by(user_id=user_id).first()
        return creds.last_binance_txid if creds else None


def save_last_binance_txid(user_id: int, txid: str):
    with session_scope() as session:
        creds = session.query(ApiCredentials).filter_by(user_id=user_id).first()
        if creds:
            creds.last_binance_txid = txid


def get_last_rise_txid(user_id: int):
    with session_scope() as session:
        creds = session.query(ApiCredentials).filter_by(user_id=user_id).first()
        return creds.last_rise_txid if creds else None


def save_last_rise_txid(user_id: int, txid: str):
    with session_scope() as session:
        creds = session.query(ApiCredentials).filter_by(user_id=user_id).first()
        if creds:
            creds.last_rise_txid = txid


# ---------------------------------------------------------
# BINANCE REST + WEBSOCKET (par client)
# ---------------------------------------------------------

def _binance_headers(api_key: str):
    return {"X-MBX-APIKEY": api_key}


def _sign_binance_params(params: dict, secret_key: str) -> str:
    query_string = urlencode(params)
    signature = hmac.new(secret_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    return f"{query_string}&signature={signature}"


def _get_binance_deposits(api_key: str, secret_key: str):
    params = {
        "timestamp": int(time.time() * 1000),
        "recvWindow": 60000,
    }

    signed_query = _sign_binance_params(params, secret_key)
    url = f"{config.BINANCE_API_BASE_URL}/sapi/v1/capital/deposit/hisrec?{signed_query}"

    response = requests.get(url, headers=_binance_headers(api_key), timeout=10)
    response.raise_for_status()
    return response.json()


def process_binance_deposits(user_id: int, api_key: str, secret_key: str, chat_id, baseline_if_empty: bool = False) -> bool:
    try:
        deposits = _get_binance_deposits(api_key, secret_key)
    except Exception as e:
        logger.warning("Binance REST erreur (user=%s) : %s", user_id, e)
        return False

    if not isinstance(deposits, list) or not deposits:
        return False

    latest = max(deposits, key=lambda d: d.get("insertTime", 0))

    txid = latest.get("txId")
    coin = latest.get("coin")
    amount = latest.get("amount")
    network = latest.get("network")

    if not txid:
        return False

    last_txid = get_last_binance_txid(user_id)

    if last_txid is None and baseline_if_empty and not config.BINANCE_NOTIFY_FIRST_DEPOSIT:
        save_last_binance_txid(user_id, txid)
        return False

    if txid == last_txid:
        return False

    message = (
        f"💸 Dépôt Binance reçu\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Montant : {amount}\n\n"
        f"🪙 Crypto : {coin}\n"
        f"🌐 Réseau : {network}\n\n"
        f"📥 Fonds crédités sur Binance\n"
    )

    if send_telegram(chat_id, message):
        save_last_binance_txid(user_id, txid)
        return True

    return False


def _sign_binance_ws_params(params: dict, secret_key: str) -> dict:
    query_string = urlencode(sorted(params.items()))
    signature = hmac.new(secret_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    signed = dict(params)
    signed["signature"] = signature
    return signed


async def _subscribe_binance_user_stream(ws, api_key: str, secret_key: str):
    params = _sign_binance_ws_params(
        {"apiKey": api_key, "timestamp": int(time.time() * 1000)},
        secret_key,
    )

    request = {
        "id": int(time.time() * 1000),
        "method": "userDataStream.subscribe.signature",
        "params": params,
    }

    await ws.send(json.dumps(request))
    response = json.loads(await ws.recv())

    if response.get("status") != 200:
        raise RuntimeError(f"Binance subscription refusée : {response}")


def _is_positive_binance_balance_update(data: dict) -> bool:
    event = data.get("event", data)

    if event.get("e") != "balanceUpdate":
        return False

    try:
        return Decimal(event.get("d", "0")) > 0
    except Exception:
        return False


async def _refresh_binance_deposit_after_event(user_id: int, api_key: str, secret_key: str, chat_id):
    for attempt in range(1, 4):
        has_new_deposit = await asyncio.to_thread(
            process_binance_deposits, user_id, api_key, secret_key, chat_id, False
        )
        if has_new_deposit:
            return
        await asyncio.sleep(10)


async def listen_binance_wallet(user_id: int, api_key: str, secret_key: str, chat_id):
    logger.info("▶️ Binance monitoring démarré (user=%s)", user_id)

    try:
        await asyncio.to_thread(process_binance_deposits, user_id, api_key, secret_key, chat_id, True)
    except Exception as e:
        logger.warning("Binance baseline erreur (user=%s) : %s", user_id, e)

    while True:
        try:
            async with websockets.connect(config.BINANCE_WS_API_URL) as ws:
                await _subscribe_binance_user_stream(ws, api_key, secret_key)

                while True:
                    response = await ws.recv()
                    data = json.loads(response)

                    if _is_positive_binance_balance_update(data):
                        await _refresh_binance_deposit_after_event(user_id, api_key, secret_key, chat_id)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Binance websocket erreur (user=%s) : %s", user_id, e)
            await asyncio.sleep(10)


async def binance_fallback_loop(user_id: int, api_key: str, secret_key: str, chat_id):
    while True:
        await asyncio.sleep(config.BINANCE_FALLBACK_INTERVAL)
        try:
            await asyncio.to_thread(process_binance_deposits, user_id, api_key, secret_key, chat_id, True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Binance fallback erreur (user=%s) : %s", user_id, e)


async def monitor_binance(user_id: int, api_key: str, secret_key: str, chat_id):
    """Tâche complète Binance (websocket + fallback) pour un client."""
    await asyncio.gather(
        listen_binance_wallet(user_id, api_key, secret_key, chat_id),
        binance_fallback_loop(user_id, api_key, secret_key, chat_id),
    )


# ---------------------------------------------------------
# RISE WEBSOCKET (par client)
# ---------------------------------------------------------

async def monitor_rise(user_id: int, wallet_address: str, chat_id):
    logger.info("▶️ Rise monitoring démarré (user=%s)", user_id)

    if not config.ALCHEMY_WS_URL:
        logger.warning("ALCHEMY_WS_URL non configuré : surveillance Rise désactivée (user=%s)", user_id)
        return

    while True:
        try:
            async with websockets.connect(config.ALCHEMY_WS_URL) as ws:
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["logs", {"address": wallet_address}],
                }
                await ws.send(json.dumps(subscribe_msg))

                while True:
                    response = await ws.recv()
                    data = json.loads(response)

                    if "params" in data:
                        result = data["params"]["result"]
                        tx_hash = result.get("transactionHash")
                        block_number = result.get("blockNumber")

                        last_rise_txid = get_last_rise_txid(user_id)

                        if tx_hash and tx_hash != last_rise_txid:
                            message = (
                                f"💸 Dépôt Rise reçu\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"🔗 TX Hash : {tx_hash}\n\n"
                                f"🌐 Réseau : Arbitrum\n"
                                f"📦 Block : {block_number}\n\n"
                                f"📥 Fonds détectés sur le wallet Rise\n"
                            )

                            if send_telegram(chat_id, message):
                                save_last_rise_txid(user_id, tx_hash)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Rise websocket erreur (user=%s) : %s", user_id, e)
            await asyncio.sleep(5)


# ---------------------------------------------------------
# SUPERVISEUR
# ---------------------------------------------------------

def _eligible_users():
    """
    Renvoie {user_id: (chat_id, binance_fingerprint_or_None, rise_wallet_or_None)}
    pour les clients dont l'abonnement est actif.
    """
    result = {}

    with session_scope() as session:
        users = (
            session.query(User)
            .join(Subscription)
            .filter(Subscription.status == Subscription.STATUS_ACTIVE)
            .all()
        )

        for user in users:
            if not user.has_active_access:
                continue

            creds = user.credentials
            if not creds:
                continue

            binance_fp = None
            if creds.has_binance:
                binance_fp = (creds.binance_api_key, creds.binance_secret_key)

            rise_wallet = creds.rise_wallet if creds.has_rise else None

            if binance_fp or rise_wallet:
                result[user.id] = (user.telegram_chat_id, binance_fp, rise_wallet)

    return result


class MonitoringSupervisor:
    """
    Démarre/arrête dynamiquement les tâches de surveillance Binance/Rise
    en fonction de l'état de la base (abonnements actifs, identifiants
    configurés). À lancer en arrière-plan dans la boucle asyncio du bot.
    """

    def __init__(self):
        self._binance_tasks = {}  # user_id -> (asyncio.Task, fingerprint)
        self._rise_tasks = {}     # user_id -> (asyncio.Task, wallet)
        self._stopped = False

    async def run(self):
        logger.info(
            "Superviseur de surveillance démarré (toutes les %ss).",
            config.MONITORING_POLL_INTERVAL,
        )

        while not self._stopped:
            try:
                await self._sync_once()
            except Exception:
                logger.exception("Erreur dans le superviseur de surveillance")

            await asyncio.sleep(config.MONITORING_POLL_INTERVAL)

    async def stop(self):
        self._stopped = True
        for task, _ in list(self._binance_tasks.values()) + list(self._rise_tasks.values()):
            task.cancel()

    async def _sync_once(self):
        eligible = _eligible_users()

        # --- Binance ---
        for user_id, (chat_id, binance_fp, _rise) in eligible.items():
            current = self._binance_tasks.get(user_id)

            if binance_fp is None:
                if current:
                    current[0].cancel()
                    del self._binance_tasks[user_id]
                continue

            if current is None or current[1] != binance_fp:
                if current:
                    current[0].cancel()

                api_key, secret_key = binance_fp
                task = asyncio.create_task(monitor_binance(user_id, api_key, secret_key, chat_id))
                self._binance_tasks[user_id] = (task, binance_fp)

        for user_id in list(self._binance_tasks):
            if user_id not in eligible or eligible[user_id][1] is None:
                self._binance_tasks.pop(user_id)[0].cancel()

        # --- Rise ---
        for user_id, (chat_id, _binance, rise_wallet) in eligible.items():
            current = self._rise_tasks.get(user_id)

            if rise_wallet is None:
                if current:
                    current[0].cancel()
                    del self._rise_tasks[user_id]
                continue

            if current is None or current[1] != rise_wallet:
                if current:
                    current[0].cancel()

                task = asyncio.create_task(monitor_rise(user_id, rise_wallet, chat_id))
                self._rise_tasks[user_id] = (task, rise_wallet)

        for user_id in list(self._rise_tasks):
            if user_id not in eligible or eligible[user_id][2] is None:
                self._rise_tasks.pop(user_id)[0].cancel()
