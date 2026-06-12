# =========================================================
# IMPORTS
# =========================================================

import os
import time
import requests
import hashlib
import hmac
import asyncio
import json
import websockets

from decimal import Decimal
from flask import Flask
from threading import Thread
from urllib.parse import urlencode

from web3 import Web3


# =========================================================
# VARIABLES D'ENVIRONNEMENT
# =========================================================

# recuperation des cles api sur le serveur à ne pas mettre ici


# ---------------------------------------------------------
# Binance API
# ---------------------------------------------------------

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
BINANCE_API_BASE_URL = os.getenv(
    "BINANCE_API_BASE_URL",
    "https://api.binance.com"
)
BINANCE_WS_API_URL = os.getenv(
    "BINANCE_WS_API_URL",
    "wss://ws-api.binance.com:443/ws-api/v3?returnRateLimits=false"
)
BINANCE_FALLBACK_INTERVAL = int(
    os.getenv("BINANCE_FALLBACK_INTERVAL", "900")
)
BINANCE_NOTIFY_FIRST_DEPOSIT = (
    os.getenv("BINANCE_NOTIFY_FIRST_DEPOSIT", "true").lower() == "true"
)


# ---------------------------------------------------------
# Wallet Rise / Websocket Alchemy Arbitrum /
# ---------------------------------------------------------

ALCHEMY_WS_URL = os.getenv("ALCHEMY_WS_URL")


# =========================================================
# WALLET RISE A SURVEILLER
# =========================================================

# mettre wallet dans .env du serveur

RISE_WALLET = os.getenv("RISE_WALLET")


# ---------------------------------------------------------
# Telegram API
# ---------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


REQUIRED_ENV_VARS = {
    "BINANCE_API_KEY": BINANCE_API_KEY,
    "BINANCE_SECRET_KEY": BINANCE_SECRET_KEY,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
}

RISE_ENV_VARS = {
    "ALCHEMY_WS_URL": ALCHEMY_WS_URL,
    "RISE_WALLET": RISE_WALLET,
}


def validate_environment():

    global RISE_WALLET

    missing_vars = [
        name
        for name, value in REQUIRED_ENV_VARS.items()
        if not value
    ]

    if missing_vars:
        raise RuntimeError(
            "Variables d'environnement manquantes : "
            + ", ".join(missing_vars)
        )

    missing_rise_vars = [
        name
        for name, value in RISE_ENV_VARS.items()
        if not value
    ]

    if missing_rise_vars:

        print(
            "⚠️ Rise désactivé, variables manquantes : "
            + ", ".join(missing_rise_vars)
        )

        return False

    try:
        RISE_WALLET = Web3.to_checksum_address(RISE_WALLET)
    except (TypeError, ValueError) as e:
        print("⚠️ Rise désactivé : RISE_WALLET invalide.")

        return False

    return True


# =========================================================
# FICHIERS ANTI DOUBLONS
# =========================================================

# plus de doublons, même après redémarrage du systeme

LAST_TX_FILE = "last_txid.txt"

# anti doublons rise websocket

LAST_RISE_TX_FILE = "last_rise_txid.txt"


# ---------------------------------------------------------
# Stockage persistant (Upstash Redis) sur Render
# ---------------------------------------------------------

# Render efface le filesystem local à chaque redémarrage /
# redeploy / spin-down. Pour ne pas reperdre last_txid à
# chaque restart (ce qui provoque des notifications en
# double), on bascule sur Upstash Redis (REST API) quand le
# bot tourne sur Render.
#
# Sur un serveur perso (disque persistant), la variable
# RENDER n'existe pas : le bot retombe automatiquement sur
# les fichiers locaux, sans rien à changer.

UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

USE_REDIS_STORAGE = bool(
    os.getenv("RENDER")
    and UPSTASH_REDIS_REST_URL
    and UPSTASH_REDIS_REST_TOKEN
)

if USE_REDIS_STORAGE:
    print("✅ Stockage anti-doublons : Upstash Redis")
else:
    print("✅ Stockage anti-doublons : fichiers locaux")


def _redis_headers():

    return {
        "Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"
    }


def _redis_get(key):

    try:
        response = requests.get(
            f"{UPSTASH_REDIS_REST_URL}/get/{key}",
            headers=_redis_headers(),
            timeout=10
        )

        response.raise_for_status()

        return response.json().get("result")

    except Exception as e:

        print(f"❌ Upstash get error ({key}) :", e)

        return None


def _redis_set(key, value):

    try:
        response = requests.get(
            f"{UPSTASH_REDIS_REST_URL}/set/{key}/{value}",
            headers=_redis_headers(),
            timeout=10
        )

        response.raise_for_status()

        return True

    except Exception as e:

        print(f"❌ Upstash set error ({key}) :", e)

        return False


# =========================================================
# BINANCE ANTI DOUBLONS
# =========================================================

def get_last_txid():

    if USE_REDIS_STORAGE:
        return _redis_get("celluletrade:last_txid")

    if os.path.exists(LAST_TX_FILE):

        with open(LAST_TX_FILE, "r") as f:
            return f.read().strip()

    return None


def save_last_txid(txid):

    if USE_REDIS_STORAGE:
        _redis_set("celluletrade:last_txid", txid)
        return

    with open(LAST_TX_FILE, "w") as f:
        f.write(txid)


# =========================================================
# RISE ANTI DOUBLONS
# =========================================================

def get_last_rise_txid():

    if USE_REDIS_STORAGE:
        return _redis_get("celluletrade:last_rise_txid")

    if os.path.exists(LAST_RISE_TX_FILE):

        with open(LAST_RISE_TX_FILE, "r") as f:
            return f.read().strip()

    return None


def save_last_rise_txid(txid):

    if USE_REDIS_STORAGE:
        _redis_set("celluletrade:last_rise_txid", txid)
        return

    with open(LAST_RISE_TX_FILE, "w") as f:
        f.write(txid)


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("ok"):

            print("❌ Telegram refusé :", result)

            return False

        print("✅ Telegram envoyé")
        print(result)

        return True

    except Exception as e:

        print("❌ Telegram erreur :", e)

        return False


# =========================================================
# BINANCE REST + WEBSOCKET
# =========================================================

def get_binance_headers():

    return {
        "X-MBX-APIKEY": BINANCE_API_KEY
    }


def sign_binance_params(params):

    query_string = urlencode(params)

    signature = hmac.new(
        BINANCE_SECRET_KEY.encode(),
        query_string.encode(),
        hashlib.sha256
    ).hexdigest()

    return f"{query_string}&signature={signature}"


def get_binance_deposits():

    print("🔎 Binance REST deposit history check...", flush=True)

    params = {
        "timestamp": int(time.time() * 1000),
        "recvWindow": 60000
    }

    signed_query = sign_binance_params(params)

    url = (
        f"{BINANCE_API_BASE_URL}/sapi/v1/capital/deposit/hisrec"
        f"?{signed_query}"
    )

    response = requests.get(
        url,
        headers=get_binance_headers(),
        timeout=10
    )

    response.raise_for_status()

    return response.json()


def process_binance_deposits(baseline_if_empty=False):

    deposits = get_binance_deposits()

    print("✅ Binance deposits checked")

    if not isinstance(deposits, list):

        print("❌ Binance réponse inattendue :", deposits)

        return False

    if len(deposits) == 0:

        print("✅ Aucun dépôt Binance")

        return False

    latest = max(
        deposits,
        key=lambda deposit: deposit.get("insertTime", 0)
    )

    txid = latest.get("txId")
    coin = latest.get("coin")
    amount = latest.get("amount")
    network = latest.get("network")

    if not txid:

        print("⚠️ Binance deposit sans txId")

        return False

    last_txid = get_last_txid()

    if last_txid is None and baseline_if_empty and not BINANCE_NOTIFY_FIRST_DEPOSIT:

        save_last_txid(txid)

        print("✅ Binance baseline enregistrée")

        return False

    if last_txid is None:

        print("⚠️ Aucun txId Binance enregistré, notification du dernier dépôt")

    if txid == last_txid:

        print("✅ Aucun nouveau dépôt Binance")

        return False

    message = (
        f"💸 Dépôt Binance reçu\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Montant : {amount}\n\n"
        f"🪙 Crypto : {coin}\n"
        f"🌐 Réseau : {network}\n\n"
        f"📥 Fonds crédités sur Binance\n"
    )

    if send_telegram(message):

        save_last_txid(txid)

        return True

    return False


def sign_binance_ws_params(params):

    query_string = urlencode(sorted(params.items()))

    signature = hmac.new(
        BINANCE_SECRET_KEY.encode(),
        query_string.encode(),
        hashlib.sha256
    ).hexdigest()

    signed_params = dict(params)

    signed_params["signature"] = signature

    return signed_params


async def subscribe_binance_user_stream(ws):

    print("🔑 Binance subscription signature...", flush=True)

    params = sign_binance_ws_params({
        "apiKey": BINANCE_API_KEY,
        "timestamp": int(time.time() * 1000)
    })

    request = {
        "id": int(time.time() * 1000),
        "method": "userDataStream.subscribe.signature",
        "params": params
    }

    await ws.send(json.dumps(request))

    response = json.loads(await ws.recv())

    if response.get("status") != 200:

        raise RuntimeError(f"Binance subscription refusée : {response}")

    print("✅ Listening Binance User Data Stream", flush=True)


def is_positive_binance_balance_update(data):

    event = data.get("event", data)

    if event.get("e") != "balanceUpdate":

        return False

    try:
        return Decimal(event.get("d", "0")) > 0
    except Exception:
        return False


async def refresh_binance_deposit_after_event():

    for attempt in range(1, 4):

        has_new_deposit = await asyncio.to_thread(
            process_binance_deposits,
            False
        )

        if has_new_deposit:

            return

        print(f"⏳ Binance dépôt pas encore visible, essai {attempt}/3")

        await asyncio.sleep(10)


async def listen_binance_wallet():

    print("✅ Binance websocket monitoring démarré")

    try:
        await asyncio.to_thread(
            process_binance_deposits,
            True
        )
    except Exception as e:
        print("❌ Binance baseline error :", e)

    while True:

        try:
            async with websockets.connect(BINANCE_WS_API_URL) as ws:

                await subscribe_binance_user_stream(ws)

                while True:

                    response = await ws.recv()

                    data = json.loads(response)

                    if is_positive_binance_balance_update(data):

                        print("💰 Binance balanceUpdate détecté")

                        await refresh_binance_deposit_after_event()

        except Exception as e:

            print("❌ Binance websocket error :", e)

            await asyncio.sleep(10)


async def binance_fallback_loop():

    print(
        f"✅ Binance fallback REST toutes les {BINANCE_FALLBACK_INTERVAL}s"
    )

    while True:

        await asyncio.sleep(BINANCE_FALLBACK_INTERVAL)

        try:
            await asyncio.to_thread(
                process_binance_deposits,
                True
            )
        except Exception as e:
            print("❌ Binance fallback error :", e)


# =========================================================
# RISE WEBSOCKET LISTENER
# =========================================================

async def listen_rise_wallet():

    print("✅ Rise websocket connecté")

    while True:

        try:

            # connexion websocket alchemy

            async with websockets.connect(ALCHEMY_WS_URL) as ws:

                # abonnement websocket wallet rise

                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": [
                        "logs",
                        {
                            "address": RISE_WALLET
                        }
                    ]
                }

                # envoi abonnement websocket

                await ws.send(
                    json.dumps(subscribe_msg)
                )

                print("✅ Listening Rise Wallet")

                # boucle websocket blockchain

                while True:

                    response = await ws.recv()

                    data = json.loads(response)

                    print(data)

                    # verification nouvel evenement blockchain

                    if "params" in data:

                        result = data["params"]["result"]

                        tx_hash = result.get(
                            "transactionHash"
                        )

                        block_number = result.get(
                            "blockNumber"
                        )

                        last_rise_txid = get_last_rise_txid()

                        # verification anti doublons

                        if tx_hash and tx_hash != last_rise_txid:

                            message = (
                                f"💸 Dépôt Rise reçu\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"🔗 TX Hash : {tx_hash}\n\n"
                                f"🌐 Réseau : Arbitrum\n"
                                f"📦 Block : {block_number}\n\n"
                                f"📥 Fonds détectés sur le wallet Rise\n"
                            )

                            if send_telegram(message):

                                save_last_rise_txid(tx_hash)

        except Exception as e:

            print("❌ Rise websocket error :", e)

            # reconnexion auto websocket

            await asyncio.sleep(5)


# =========================================================
# MAIN
# =========================================================

async def main(rise_enabled):

    tasks = [

        # Binance monitoring

        listen_binance_wallet(),

        # Binance REST fallback rare

        binance_fallback_loop()
    ]

    if rise_enabled:

        # Rise websocket monitoring

        tasks.append(
            listen_rise_wallet()
        )

    await asyncio.gather(*tasks)


# =========================================================
# FLASK KEEP ALIVE RENDER
# =========================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "CelluleTrade Bot Running"


# ---------------------------------------------------------
# Panel de test Telegram (Binance / Rise)
# ---------------------------------------------------------

TEST_PANEL_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>CelluleTrade Bot - Test Telegram</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f1115;
            color: #eee;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        h1 { margin-bottom: 30px; font-size: 20px; }
        .buttons { display: flex; gap: 16px; }
        button {
            padding: 15px 30px;
            font-size: 16px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }
        .binance { background: #f0b90b; color: #000; }
        .rise { background: #3b82f6; color: #fff; }
        button:disabled { opacity: 0.6; cursor: default; }
        #result {
            margin-top: 24px;
            font-size: 14px;
            white-space: pre-wrap;
            max-width: 420px;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>🧪 Test notifications Telegram</h1>
    <div class="buttons">
        <button class="binance" onclick="testNotif('binance', this)">Tester Binance</button>
        <button class="rise" onclick="testNotif('rise', this)">Tester Rise</button>
    </div>
    <div id="result"></div>

    <script>
        async function testNotif(type, btn) {
            const result = document.getElementById('result');
            btn.disabled = true;
            result.innerText = "Envoi en cours...";

            try {
                const res = await fetch('/test/' + type, { method: 'POST' });
                const data = await res.json();

                result.innerText = data.ok
                    ? "✅ " + type + " : " + (data.detail || "test envoyé sur Telegram")
                    : "❌ Échec : " + (data.error || JSON.stringify(data));
            } catch (e) {
                result.innerText = "❌ Erreur : " + e;
            } finally {
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""


@app.route('/test')
def test_panel():
    return TEST_PANEL_HTML


@app.route('/test/binance', methods=['POST'])
def test_binance_notification():

    # Test réel : interroge l'API Binance (lecture seule,
    # ne touche pas à last_txid donc n'affecte pas la
    # detection anti-doublon en cours)

    try:
        deposits = get_binance_deposits()
    except Exception as e:

        send_telegram(f"❌ Test Binance : erreur API Binance ({e})")

        return {"ok": False, "error": str(e)}

    if not isinstance(deposits, list) or len(deposits) == 0:

        message = (
            f"🧪 Test Binance (réel)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✅ Connexion API Binance OK\n"
            f"📭 Aucun dépôt trouvé sur le compte\n"
        )

        ok = send_telegram(message)

        return {"ok": ok, "detail": "Connexion OK, aucun dépôt trouvé"}

    latest = max(
        deposits,
        key=lambda deposit: deposit.get("insertTime", 0)
    )

    message = (
        f"🧪 Test Binance (réel)\n"
        f"━━━━━━━━━━━━━━━\n"
        f"✅ Connexion API Binance OK\n"
        f"💰 Dernier dépôt : {latest.get('amount')} {latest.get('coin')}\n"
        f"🌐 Réseau : {latest.get('network')}\n"
        f"🔗 TxID : {latest.get('txId')}\n\n"
        f"ℹ️ Lecture seule, n'affecte pas la détection anti-doublon\n"
    )

    ok = send_telegram(message)

    return {
        "ok": ok,
        "detail": (
            f"Dernier dépôt trouvé : "
            f"{latest.get('amount')} {latest.get('coin')} "
            f"({latest.get('network')})"
        )
    }


@app.route('/test/rise', methods=['POST'])
def test_rise_notification():

    # Test réel : interroge l'API Alchemy (lecture seule,
    # ne touche pas à last_rise_txid donc n'affecte pas la
    # detection anti-doublon en cours)

    if not ALCHEMY_WS_URL or not RISE_WALLET:

        send_telegram(
            "❌ Test Rise : ALCHEMY_WS_URL ou RISE_WALLET manquant"
        )

        return {"ok": False, "error": "Variables Rise manquantes"}

    alchemy_http_url = (
        ALCHEMY_WS_URL
        .replace("wss://", "https://")
        .replace("ws://", "http://")
    )

    try:
        response = requests.post(
            alchemy_http_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "alchemy_getAssetTransfers",
                "params": [{
                    "toAddress": RISE_WALLET,
                    "category": ["external", "erc20"],
                    "order": "desc",
                    "maxCount": "0x1",
                    "withMetadata": True
                }]
            },
            timeout=10
        )

        response.raise_for_status()

        result = response.json()

    except Exception as e:

        send_telegram(f"❌ Test Rise : erreur API Alchemy ({e})")

        return {"ok": False, "error": str(e)}

    transfers = result.get("result", {}).get("transfers", [])

    if not transfers:

        message = (
            f"🧪 Test Rise (réel)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✅ Connexion API Alchemy OK\n"
            f"📭 Aucune transaction entrante trouvée sur le wallet\n"
        )

        ok = send_telegram(message)

        return {"ok": ok, "detail": "Connexion OK, aucune tx trouvée"}

    latest = transfers[0]

    message = (
        f"🧪 Test Rise (réel)\n"
        f"━━━━━━━━━━━━━━━\n"
        f"✅ Connexion API Alchemy OK\n"
        f"💰 Dernière tx reçue : {latest.get('value')} {latest.get('asset')}\n"
        f"🔗 TX Hash : {latest.get('hash')}\n\n"
        f"ℹ️ Lecture seule, n'affecte pas la détection anti-doublon\n"
    )

    ok = send_telegram(message)

    return {
        "ok": ok,
        "detail": (
            f"Dernière tx reçue : "
            f"{latest.get('value')} {latest.get('asset')}"
        )
    }


def run_flask():

    app.run(
        host="0.0.0.0",
        port=10000
    )


def start_keep_alive():

    # lancement flask dans un thread séparé

    Thread(
        target=run_flask,
        daemon=True
    ).start()


# =========================================================
# START SCRIPT
# =========================================================

if __name__ == "__main__":

    rise_enabled = validate_environment()

    start_keep_alive()

    asyncio.run(main(rise_enabled))
