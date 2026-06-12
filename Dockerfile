# Image pour la plateforme multi-clients CelluleTrade (celluletrade_cash_saas/)
# Lancement : python -m celluletrade_cash_saas.manager (long polling Telegram)

FROM python:3.11-slim

WORKDIR /app

# Dépendances système minimales pour psycopg2 / cryptography
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY celluletrade_cash_saas/ ./celluletrade_cash_saas/

CMD ["python", "-m", "celluletrade_cash_saas.manager"]
