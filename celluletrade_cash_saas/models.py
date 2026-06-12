import secrets
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

from celluletrade_cash_saas.crypto import decrypt_value, encrypt_value

Base = declarative_base()


class User(Base):
    """Un utilisateur = un compte Telegram (identifié par son chat_id)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username = Column(String(64))
    first_name = Column(String(128))

    is_admin = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    credentials = relationship(
        "ApiCredentials", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    subscription = relationship(
        "Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def has_active_access(self) -> bool:
        return self.subscription is not None and self.subscription.is_active

    @property
    def display_name(self) -> str:
        return f"@{self.telegram_username}" if self.telegram_username else (self.first_name or str(self.telegram_chat_id))

    def __repr__(self):
        return f"<User {self.display_name}>"


class ApiCredentials(Base):
    """Identifiants Binance (chiffrés) et wallet Rise d'un client."""

    __tablename__ = "api_credentials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    _binance_api_key = Column("binance_api_key", Text)
    _binance_secret_key = Column("binance_secret_key", Text)

    rise_wallet = Column(String(255))

    # Anti-doublons : dernier dépôt déjà notifié pour ce client
    last_binance_txid = Column(String(128))
    last_rise_txid = Column(String(128))

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="credentials")

    @property
    def binance_api_key(self):
        return decrypt_value(self._binance_api_key)

    @binance_api_key.setter
    def binance_api_key(self, value):
        self._binance_api_key = encrypt_value(value)

    @property
    def binance_secret_key(self):
        return decrypt_value(self._binance_secret_key)

    @binance_secret_key.setter
    def binance_secret_key(self, value):
        self._binance_secret_key = encrypt_value(value)

    @property
    def has_binance(self) -> bool:
        return bool(self._binance_api_key and self._binance_secret_key)

    @property
    def has_rise(self) -> bool:
        return bool(self.rise_wallet)

    @property
    def is_ready(self) -> bool:
        return self.has_binance or self.has_rise


class Subscription(Base):
    __tablename__ = "subscriptions"

    PLAN_NONE = "none"
    PLAN_MONTHLY = "monthly"      # 5€/mois
    PLAN_LIFETIME = "lifetime"    # 300€ paiement unique
    PLAN_FREE = "free"            # accès gratuit accordé via code

    STATUS_INACTIVE = "inactive"
    STATUS_ACTIVE = "active"
    STATUS_CANCELED = "canceled"
    STATUS_PENDING = "pending"    # paiement Stripe créé, en attente de confirmation

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    plan = Column(String(32), default=PLAN_NONE, nullable=False)
    status = Column(String(32), default=STATUS_INACTIVE, nullable=False)

    stripe_customer_id = Column(String(255))
    stripe_subscription_id = Column(String(255))
    stripe_checkout_session_id = Column(String(255))

    granted_by_admin = Column(Boolean, default=False, nullable=False)

    current_period_end = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscription")

    @property
    def is_active(self) -> bool:
        if self.status != self.STATUS_ACTIVE:
            return False
        if self.granted_by_admin or self.plan == self.PLAN_LIFETIME:
            return True
        if self.current_period_end and self.current_period_end < datetime.utcnow():
            return False
        return True

    @property
    def label(self) -> str:
        return {
            self.PLAN_NONE: "Aucun abonnement",
            self.PLAN_MONTHLY: "Abonnement mensuel (5€/mois)",
            self.PLAN_LIFETIME: "Accès à vie (300€)",
            self.PLAN_FREE: "Accès gratuit",
        }.get(self.plan, self.plan)


class FreeAccessCode(Base):
    """Code à usage unique permettant d'activer un accès gratuit."""

    __tablename__ = "free_access_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, nullable=False, index=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    used_by_user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used_at = Column(DateTime)

    @staticmethod
    def generate_code() -> str:
        return secrets.token_hex(4).upper()

    @property
    def is_used(self) -> bool:
        return self.used_by_user_id is not None
