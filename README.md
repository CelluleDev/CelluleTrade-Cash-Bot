# celluletrade_cash_bot

# 📡 Binance & Rise Telegram Monitoring Bot

Bot Python de monitoring crypto en temps réel.

Le script surveille automatiquement :

- les dépôts Binance (pour recevoir les notifications de paiement de votre broker vers Binance quand vous faites un retrait)
- les transactions blockchain Rise sur Arbitrum (pour les retraits des prop firms et être alerté quand vous recevez le paiement sur Rise)

et envoie des notifications Telegram instantanées.

✅ Binance monitoring
✅ Rise blockchain monitoring
✅ WebSocket temps réel
✅ Telegram
✅ anti doublons
✅ reconnexion auto
✅ async propre
✅ variables .env
✅ timeouts
✅ logs debug.

## Partie technique

Le bot fonctionne avec trois blocs principaux :

### Binance

Binance est surveillé via le User Data Stream WebSocket signé.

Au démarrage, le bot lit une fois l'historique des dépôts Binance pour créer une baseline avec le dernier `txId`.

Ensuite, il ouvre un WebSocket Binance sur `wss://ws-api.binance.com:443/ws-api/v3` et s'abonne avec `userDataStream.subscribe.signature`.

Cette méthode remplace l'ancien système Binance `listenKey`, qui peut retourner une erreur `410 Gone` sur les versions récentes de l'API Binance.

Le bot écoute ensuite les événements `balanceUpdate`.

Quand Binance signale une augmentation de solde, le bot appelle l'API deposit history uniquement à ce moment-là pour récupérer les détails du dépôt :

- `txId`
- crypto
- montant
- réseau

Si le `txId` est nouveau, une notification Telegram est envoyée, puis le `txId` est sauvegardé dans `last_txid.txt`.

Un fallback REST tourne aussi toutes les 15 minutes par défaut, pour sécuriser le bot si le WebSocket coupe ou rate un événement.

Logs attendus au démarrage :

```text
✅ Binance websocket monitoring démarré
🔎 Binance REST deposit history check...
✅ Binance deposits checked
✅ Binance baseline enregistrée
✅ Binance fallback REST toutes les 900s
🔑 Binance subscription signature...
✅ Listening Binance User Data Stream
```

### Rise / Arbitrum

Rise est surveillé via un WebSocket Alchemy sur le réseau Arbitrum.

Le bot s'abonne aux logs liés au wallet configuré dans `RISE_WALLET`.

Quand une transaction est détectée, le bot récupère :

- le hash de transaction
- le numéro de block
- le réseau

Si le hash est nouveau, une notification Telegram est envoyée, puis le hash est sauvegardé dans `last_rise_txid.txt`.

Rise est optionnel : si `ALCHEMY_WS_URL` ou `RISE_WALLET` manque, Binance continue de fonctionner.

### Telegram

Les notifications sont envoyées via l'API Telegram.

Une transaction est marquée comme traitée seulement si Telegram confirme que le message a bien été envoyé.

Cela évite de perdre une notification si Telegram refuse ou si le réseau échoue.

### Serveur / hébergement

Le bot lance aussi un petit serveur Flask sur le port `10000`.

Ce serveur sert de endpoint de santé pour vérifier que le service tourne, quel que soit l'hébergeur utilisé.

### Variables d'environnement

Variables obligatoires :

```env
BINANCE_API_KEY=
BINANCE_SECRET_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Variables Rise optionnelles :

```env
ALCHEMY_WS_URL=
RISE_WALLET=
```

Variable optionnelle :

```env
BINANCE_FALLBACK_INTERVAL=900
BINANCE_WS_API_URL=wss://ws-api.binance.com:443/ws-api/v3?returnRateLimits=false
```
