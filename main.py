import os
import time
import requests
import hashlib
import hmac

# recuperation des cles api sur le serveur à ne pas mettre ici 
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

last_txid = None

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)

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


            if txid != last_txid:
                last_txid = txid

                message = (
                    f"💰 Nouveau dépôt Binance\n\n"
                    f"Crypto : {coin}\n"
                    f"Montant : {amount}\n"
                    f"Réseau : {network}"
                )

                send_telegram(message)

        time.sleep(60)

    except Exception as e:
        print(e)
        time.sleep(60)