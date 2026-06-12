# Self-host avec Docker Compose (celluletrade_cash_saas)

Ce guide déploie la plateforme multi-clients CelluleTrade (`celluletrade_cash_saas/`) sur
votre propre serveur (VPS), avec une base de données Postgres persistante.
`main.py` n'est pas concerné par ce guide et continue de tourner séparément
(ex: sur Render).

## Pré-requis

- Un serveur avec Docker et Docker Compose installés.
- Le token du bot Telegram **@celluletrade_cash_bot** (le même que `main.py`).

## 1. Configuration

À la racine du projet, copiez le fichier d'exemple :

```bash
cp celluletrade_cash_saas/.env.example .env
```

Ouvrez `.env` et complétez au minimum :

- `TELEGRAM_BOT_TOKEN` : token du bot (BotFather)
- `ADMIN_TELEGRAM_CHAT_ID` : votre chat_id Telegram (devient admin au `/start`)
- `TELEGRAM_BOT_USERNAME` : nom d'utilisateur du bot sans `@`
- `ENCRYPTION_KEY` : générez-la une seule fois avec :
  ```bash
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `POSTGRES_PASSWORD` : choisissez un mot de passe fort pour la base Postgres

Optionnel : `STRIPE_SECRET_KEY`, `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_LIFETIME`,
`SUPPORT_CONTACT`, `ALCHEMY_WS_URL` (surveillance Rise).

⚠️ Ne modifiez pas `DATABASE_URL` : `docker-compose.yml` la surcharge
automatiquement pour pointer vers le service Postgres `db`.

## 2. Lancement

À la racine du projet :

```bash
docker compose up -d --build
```

Cela démarre deux conteneurs :

- `db` : Postgres 16, avec un volume persistant `celluletrade_pgdata`
- `bot` : la plateforme `celluletrade_cash_saas` (long polling Telegram, pas de port exposé)

Au premier démarrage, `init_db()` crée automatiquement les tables dans Postgres.

## 3. Vérification

```bash
docker compose logs -f bot
```

Vous devez voir :

```
Bot démarré (long polling). Ouvrez Telegram et envoyez /start à votre bot.
```

Envoyez `/start` au bot sur Telegram pour vérifier que le menu s'affiche.

## 4. Mises à jour

```bash
git pull
docker compose up -d --build
```

Les données (utilisateurs, abonnements, clés API chiffrées) sont conservées
dans le volume `celluletrade_pgdata`.

## 5. Sauvegardes

```bash
docker compose exec db pg_dump -U celluletrade celluletrade > backup.sql
```

## Arrêt

```bash
docker compose down
```

(le volume `celluletrade_pgdata` est conservé ; utilisez `docker compose down -v`
pour le supprimer définitivement — irréversible).
