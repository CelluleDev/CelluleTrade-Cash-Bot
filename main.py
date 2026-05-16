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

from flask import Flask
from threading import Thread

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


# ---------------------------------------------------------
# Wallet Rise / Websocket Alchemy Arbitrum / 
# ---------------------------------------------------------

ALCHEMY_WS_URL = os.getenv("ALCHEMY_WS_URL")


# =========================================================
# WALLET RISE A SURVEILLER
# =========================================================

# mettre wallet dans .env du serveur 

RISE_WALLET = Web3.to_checksum_address(
    os.getenv("RISE_WALLET")
)


# ---------------------------------------------------------
# Telegram API
# ---------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# =========================================================
# FICHIERS ANTI DOUBLONS
# =========================================================

# plus de doublons, même après redémarrage du systeme

LAST_TX_FILE = "last_txid.txt"

# anti doublons rise websocket

LAST_RISE_TX_FILE = "last_rise_txid.txt"


# =========================================================
# BINANCE ANTI DOUBLONS
# =========================================================

def get_last_txid():

    if os.path.exists(LAST_TX_FILE):

        with open(LAST_TX_FILE, "r") as f:
            return f.read().strip()

    return None


def save_last_txid(txid):

    with open(LAST_TX_FILE, "w") as f:
        f.write(txid)


# =========================================================
# RISE ANTI DOUBLONS
# =========================================================

def get_last_rise_txid():

    if os.path.exists(LAST_RISE_TX_FILE):

        with open(LAST_RISE_TX_FILE, "r") as f:
            return f.read().strip()

    return None


def save_last_rise_txid(txid):

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

        

        print("✅ Telegram envoyé")
        print(response.text)

    except Exception as e:

        print("❌ Telegram erreur :", e)


# =========================================================
# BINANCE LOOP
# =========================================================

async def binance_loop():

    initialized = False

    print("✅ Binance monitoring démarré")

    while True:

        try:

            timestamp = int(time.time() * 1000)

            
            query_string = f"timestamp={timestamp}&recvWindow=60000"

            signature = hmac.new(
                BINANCE_SECRET_KEY.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()

            url = (
                "https://api.binance.com/sapi/v1/capital/deposit/hisrec"
                f"?{query_string}&signature={signature}"
            )
            

            headers = {
                "X-MBX-APIKEY": BINANCE_API_KEY
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )

            deposits = response.json()

            print("✅ Binance deposits checked")

            if isinstance(deposits, list) and len(deposits) > 0:

                latest = deposits[0]

                txid = latest.get("txId")
                coin = latest.get("coin")
                amount = latest.get("amount")
                network = latest.get("network")

                last_txid = get_last_txid()

                # initialisation anti doublons

                if not initialized:

                    save_last_txid(txid)

                    initialized = True

                # nouveau depot detecté

                elif txid != last_txid:

                    message = (
                        f"💸 Dépôt Binance reçu\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"💰 Montant : {amount}\n\n"
                        f"🪙 Crypto : {coin}\n"
                        f"🌐 Réseau : {network}\n\n"
                        f"📥 Fonds crédités sur Binance\n"
                    )

                    send_telegram(message)

                    save_last_txid(txid)

            # verification toutes les 60 sec

            await asyncio.sleep(60)

        except Exception as e:

            print("❌ Binance error :", e)

            await asyncio.sleep(60)


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

                            send_telegram(message)

                            save_last_rise_txid(tx_hash)

        except Exception as e:

            print("❌ Rise websocket error :", e)

            # reconnexion auto websocket

            await asyncio.sleep(5)


# =========================================================
# MAIN
# =========================================================

async def main():

    await asyncio.gather(

        # Binance monitoring

        binance_loop(),

        # Rise websocket monitoring

        listen_rise_wallet()
    )


# =========================================================
# FLASK KEEP ALIVE RENDER
# =========================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "CelluleTrade Bot Running"


def run_flask():

    app.run(
        host="0.0.0.0",
        port=10000
    )


# lancement flask dans un thread séparé

Thread(
    target=run_flask,
    daemon=True
).start()


# =========================================================
# START SCRIPT
# =========================================================

asyncio.run(main())
