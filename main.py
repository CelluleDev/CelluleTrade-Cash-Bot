import os
import time
import requests
import hashlib
import hmac

# recuperation des cles api sur le serveur à ne pas mettre ici 

#Binance API
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

#Rise API


#Telegram API
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# plus de doublons, même après redémarrage du systeme
LAST_TX_FILE = "last_txid.txt"


def get_last_txid():
    if os.path.exists(LAST_TX_FILE):
        with open(LAST_TX_FILE, "r") as f:
            return f.read().strip()
    return None


def save_last_txid(txid):
    with open(LAST_TX_FILE, "w") as f:
        f.write(txid)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)

initialized = False
while True:
    try:
        timestamp = int(time.time() * 1000)

        query_string = f"timestamp={timestamp}"

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

        response = requests.get(url, headers=headers)

        deposits = response.json()

        if isinstance(deposits, list) and len(deposits) > 0:
            latest = deposits[0]

            txid = latest.get("txId")
            coin = latest.get("coin")
            amount = latest.get("amount")
            network = latest.get("network")

            last_txid = get_last_txid()

            if not initialized:
                save_last_txid(txid)
                initialized = True

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

        time.sleep(60)

    except Exception as e:
        print(e)
        time.sleep(60)