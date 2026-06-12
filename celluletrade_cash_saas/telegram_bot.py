"""
Interface 100% Telegram de la plateforme CelluleTrade.

Chaque client interagit uniquement avec le bot Telegram (menus à boutons) :
- configurer sa clé API Binance (lecture seule) et/ou son wallet Rise
- voir le statut de son abonnement et payer (Stripe Checkout)
- activer un accès gratuit avec un code fourni par Mickael

Aucune interface web, aucun nom de domaine requis : le bot tourne en
long polling (`run_polling`).
"""

import logging
import re
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from celluletrade_cash_saas import config, stripe_billing
from celluletrade_cash_saas.db import session_scope
from celluletrade_cash_saas.models import ApiCredentials, FreeAccessCode, Subscription, User

logger = logging.getLogger(__name__)

# --- États de conversation ---
ASK_BINANCE_KEY, ASK_BINANCE_SECRET, ASK_RISE_WALLET, ASK_FREE_CODE = range(4)

BINANCE_KEY_RE = re.compile(r"^[A-Za-z0-9]{10,128}$")
RISE_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def get_or_create_user(session, tg_user) -> User:
    user = session.query(User).filter_by(telegram_chat_id=tg_user.id).first()
    if user:
        # Met à jour le pseudo / prénom au cas où ils auraient changé
        user.telegram_username = tg_user.username
        user.first_name = tg_user.first_name
        return user

    user = User(
        telegram_chat_id=tg_user.id,
        telegram_username=tg_user.username,
        first_name=tg_user.first_name,
        is_admin=bool(config.ADMIN_TELEGRAM_CHAT_ID) and str(tg_user.id) == str(config.ADMIN_TELEGRAM_CHAT_ID),
    )
    session.add(user)
    session.flush()

    session.add(ApiCredentials(user_id=user.id))
    session.add(Subscription(user_id=user.id))
    return user


def main_menu_text(user: User) -> str:
    creds = user.credentials
    sub = user.subscription

    binance_status = "✅ configurée" if creds and creds.has_binance else "❌ non configurée"
    rise_status = "✅ configuré" if creds and creds.has_rise else "❌ non configuré"

    if sub and sub.is_active:
        sub_status = f"✅ actif — {sub.label}"
    else:
        sub_status = "❌ inactif"

    lines = [
        "📡 *CelluleTrade — Bot de notifications*",
        "",
        f"Binance : {binance_status}",
        f"Rise : {rise_status}",
        f"Abonnement : {sub_status}",
        "",
    ]

    if not (sub and sub.is_active):
        lines.append("⚠️ Activez votre abonnement pour recevoir vos notifications.")
    elif not (creds and creds.is_ready):
        lines.append("⚠️ Configurez Binance et/ou Rise pour commencer à recevoir des notifications.")
    else:
        lines.append("✅ Tout est prêt, vous recevrez vos notifications ici.")

    return "\n".join(lines)


def main_menu_keyboard(user: User) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🟡 Binance", callback_data="menu_binance")],
        [InlineKeyboardButton("🔵 Rise", callback_data="menu_rise")],
        [InlineKeyboardButton("💳 Abonnement", callback_data="menu_sub")],
        [InlineKeyboardButton("ℹ️ Aide", callback_data="menu_help")],
    ]
    if user.is_admin:
        rows.append([InlineKeyboardButton("🛠 Admin", callback_data="menu_admin")])
    return InlineKeyboardMarkup(rows)


async def show_main_menu(update_or_query, user: User, edit: bool = False):
    text = main_menu_text(user)
    kb = main_menu_keyboard(user)

    if edit:
        await update_or_query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update_or_query.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


# ---------------------------------------------------------
# Commandes de base
# ---------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        await show_main_menu(update, user)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Annulé.")
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        await show_main_menu(update, user)
    return ConversationHandler.END


# ---------------------------------------------------------
# Menu : navigation (callbacks sans état)
# ---------------------------------------------------------

async def on_menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        await show_main_menu(query, user, edit=True)


async def on_menu_binance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        creds = user.credentials

        if creds and creds.has_binance:
            text = (
                "🟡 *Binance*\n\n"
                "✅ Votre clé API est configurée.\n\n"
                "Vous pouvez la remplacer ou la supprimer ci-dessous."
            )
            rows = [
                [InlineKeyboardButton("🔄 Remplacer la clé", callback_data="binance_set")],
                [InlineKeyboardButton("🗑 Supprimer la clé", callback_data="binance_remove")],
                [InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")],
            ]
        else:
            text = (
                "🟡 *Binance*\n\n"
                "Aucune clé configurée.\n\n"
                "👉 Sur Binance : *Gestion des API* → créez une nouvelle clé.\n"
                "Cochez *uniquement* « Activer la lecture » (ne cochez surtout pas "
                "« Activer les retraits » ni « Activer le trading »).\n"
                "Pour plus de sécurité, restreignez la clé à l'IP de notre serveur.\n\n"
                "Appuyez sur « Configurer » puis envoyez votre clé API, "
                "ensuite votre clé secrète."
            )
            rows = [
                [InlineKeyboardButton("➕ Configurer", callback_data="binance_set")],
                [InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")],
            ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_menu_rise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        creds = user.credentials

        if creds and creds.has_rise:
            text = (
                "🔵 *Rise*\n\n"
                f"✅ Wallet configuré : `{creds.rise_wallet}`\n\n"
                "Vous pouvez le remplacer ou le supprimer ci-dessous."
            )
            rows = [
                [InlineKeyboardButton("🔄 Remplacer le wallet", callback_data="rise_set")],
                [InlineKeyboardButton("🗑 Supprimer le wallet", callback_data="rise_remove")],
                [InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")],
            ]
        else:
            text = (
                "🔵 *Rise*\n\n"
                "Aucun wallet configuré.\n\n"
                "👉 Indiquez l'adresse de votre wallet Rise (réseau Arbitrum) qui "
                "reçoit les paiements de votre prop firm. Elle commence par `0x` "
                "et contient 42 caractères. Vous la trouverez dans l'application "
                "Rise, section « Wallet » ou « Recevoir »."
            )
            rows = [
                [InlineKeyboardButton("➕ Configurer", callback_data="rise_set")],
                [InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")],
            ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_binance_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Clé supprimée")
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        if user.credentials:
            user.credentials.binance_api_key = None
            user.credentials.binance_secret_key = None
    await on_menu_binance(update, context)


async def on_rise_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Wallet supprimé")
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        if user.credentials:
            user.credentials.rise_wallet = None
    await on_menu_rise(update, context)


async def on_menu_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contact = config.SUPPORT_CONTACT or "l'administrateur"
    text = (
        "ℹ️ *Aide*\n\n"
        "1️⃣ Activez votre abonnement (menu *Abonnement*) ou utilisez un code "
        "gratuit fourni par l'administrateur.\n"
        "2️⃣ Configurez votre clé API Binance *en lecture seule* et/ou votre "
        "wallet Rise (menus *Binance* / *Rise*).\n"
        "3️⃣ Vous recevrez automatiquement vos notifications de dépôt ici, "
        "dans cette conversation.\n\n"
        f"Besoin d'aide ? Contactez {contact}."
    )
    rows = [
        [InlineKeyboardButton("🗑️ Supprimer mon compte", callback_data="account_delete_confirm")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_account_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = (
        "🗑️ *Supprimer mon compte*\n\n"
        "Cette action est *irréversible* :\n"
        "• votre clé API Binance et votre wallet Rise seront supprimés\n"
        "• votre abonnement sera résilié (sans remboursement automatique)\n"
        "• vous ne recevrez plus aucune notification\n\n"
        "Confirmez-vous la suppression définitive de votre compte ?"
    )
    rows = [
        [InlineKeyboardButton("✅ Oui, supprimer définitivement", callback_data="account_delete_do")],
        [InlineKeyboardButton("⬅️ Annuler", callback_data="menu_help")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_account_delete_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)

        # Détacher les codes gratuits liés pour éviter les contraintes de clé
        # étrangère (création / utilisation par ce compte).
        session.query(FreeAccessCode).filter_by(created_by_user_id=user.id).update(
            {"created_by_user_id": None}
        )
        session.query(FreeAccessCode).filter_by(used_by_user_id=user.id).update(
            {"used_by_user_id": None}
        )

        session.delete(user)

    await query.answer("Compte supprimé.", show_alert=True)
    await query.edit_message_text(
        "🗑️ *Compte supprimé*\n\n"
        "Votre compte et toutes vos données ont été définitivement supprimés.\n\n"
        "Envoyez /start si vous souhaitez recréer un compte.",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------
# Abonnement
# ---------------------------------------------------------

async def on_menu_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        sub = user.subscription

        if sub and sub.is_active:
            text = f"💳 *Abonnement*\n\n✅ Actif — {sub.label}"
            rows = [[InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")]]
        else:
            text = (
                "💳 *Abonnement*\n\n"
                "❌ Aucun abonnement actif.\n\n"
                "Choisissez une formule, ou utilisez un code gratuit si vous en avez un."
            )
            rows = []
            if stripe_billing.is_configured():
                rows.append([InlineKeyboardButton("💶 5€ / mois", callback_data="sub_pay_monthly")])
                rows.append([InlineKeyboardButton("💎 300€ (accès à vie)", callback_data="sub_pay_lifetime")])
            rows.append([InlineKeyboardButton("🎁 J'ai un code gratuit", callback_data="sub_redeem")])
            rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_sub_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan = Subscription.PLAN_MONTHLY if query.data == "sub_pay_monthly" else Subscription.PLAN_LIFETIME

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)

        if not stripe_billing.is_configured():
            await query.edit_message_text(
                "Le paiement en ligne n'est pas encore configuré. Contactez l'administrateur.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Retour", callback_data="menu_sub")]]),
            )
            return

        url, session_id = stripe_billing.create_checkout_session(user, plan)

        sub = user.subscription or Subscription(user_id=user.id)
        sub.plan = plan
        sub.status = Subscription.STATUS_PENDING
        sub.stripe_checkout_session_id = session_id
        session.add(sub)

    label = "5€ / mois" if plan == Subscription.PLAN_MONTHLY else "300€ (accès à vie)"
    text = (
        f"💳 Paiement « {label} »\n\n"
        f"👉 [Cliquez ici pour payer]({url})\n\n"
        "Une fois le paiement effectué, votre abonnement sera activé "
        "automatiquement dans les minutes qui suivent."
    )
    rows = [[InlineKeyboardButton("⬅️ Retour", callback_data="menu_sub")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown", disable_web_page_preview=True)


# ---------------------------------------------------------
# Conversations (saisie de texte)
# ---------------------------------------------------------

async def binance_set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🟡 Envoyez votre *clé API* Binance.\n\nEnvoyez /annuler pour arrêter.",
        parse_mode="Markdown",
    )
    return ASK_BINANCE_KEY


async def binance_set_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not BINANCE_KEY_RE.match(text):
        await update.message.reply_text(
            "Format invalide (10 à 128 caractères alphanumériques attendus). "
            "Réessayez ou envoyez /annuler."
        )
        return ASK_BINANCE_KEY

    context.user_data["binance_api_key"] = text
    await update.message.reply_text("Merci. Maintenant envoyez votre *clé secrète* Binance.", parse_mode="Markdown")
    return ASK_BINANCE_SECRET


async def binance_set_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not BINANCE_KEY_RE.match(text):
        await update.message.reply_text(
            "Format invalide (10 à 128 caractères alphanumériques attendus). "
            "Réessayez ou envoyez /annuler."
        )
        return ASK_BINANCE_SECRET

    api_key = context.user_data.pop("binance_api_key", None)

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        if not user.credentials:
            user.credentials = ApiCredentials(user_id=user.id)
            session.add(user.credentials)
        user.credentials.binance_api_key = api_key
        user.credentials.binance_secret_key = text

    # Supprime le message contenant la clé secrète pour limiter son exposition
    try:
        await update.message.delete()
    except Exception:
        pass

    await update.message.reply_text("✅ Clé API Binance enregistrée et chiffrée.")
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        await show_main_menu(update, user)
    return ConversationHandler.END


async def rise_set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔵 Envoyez l'adresse de votre wallet Rise (format `0x...`, 42 caractères).\n\n"
        "Envoyez /annuler pour arrêter.",
        parse_mode="Markdown",
    )
    return ASK_RISE_WALLET


async def rise_set_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not RISE_WALLET_RE.match(text):
        await update.message.reply_text(
            "Adresse invalide (format `0x` suivi de 40 caractères hexadécimaux). "
            "Réessayez ou envoyez /annuler.",
            parse_mode="Markdown",
        )
        return ASK_RISE_WALLET

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        if not user.credentials:
            user.credentials = ApiCredentials(user_id=user.id)
            session.add(user.credentials)
        user.credentials.rise_wallet = text

    await update.message.reply_text("✅ Wallet Rise enregistré.")
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        await show_main_menu(update, user)
    return ConversationHandler.END


async def redeem_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎁 Envoyez votre code d'accès gratuit.\n\nEnvoyez /annuler pour arrêter."
    )
    return ASK_FREE_CODE


async def redeem_code_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_value = update.message.text.strip().upper()

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        code = session.query(FreeAccessCode).filter_by(code=code_value).first()

        if not code:
            await update.message.reply_text("Code introuvable. Vérifiez et réessayez, ou envoyez /annuler.")
            return ASK_FREE_CODE

        if code.is_used:
            await update.message.reply_text("Ce code a déjà été utilisé. Envoyez /annuler.")
            return ASK_FREE_CODE

        code.used_by_user_id = user.id
        code.used_at = datetime.utcnow()

        sub = user.subscription or Subscription(user_id=user.id)
        sub.plan = Subscription.PLAN_FREE
        sub.status = Subscription.STATUS_ACTIVE
        sub.granted_by_admin = True
        session.add(sub)
        session.add(code)

    await update.message.reply_text("✅ Accès gratuit activé. Merci !")
    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        await show_main_menu(update, user)
    return ConversationHandler.END


# ---------------------------------------------------------
# Admin
# ---------------------------------------------------------

async def on_menu_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        if not user.is_admin:
            await query.answer("Accès refusé.", show_alert=True)
            return

        total_users = session.query(User).count()
        active_subs = (
            session.query(Subscription)
            .filter(Subscription.status == Subscription.STATUS_ACTIVE)
            .count()
        )

    text = (
        "🛠 *Administration*\n\n"
        f"Utilisateurs inscrits : {total_users}\n"
        f"Abonnements actifs : {active_subs}\n\n"
        "Générez un code pour offrir un accès gratuit à vie à quelqu'un : "
        "envoyez-lui simplement le code, il pourra l'activer via "
        "« Abonnement » → « J'ai un code gratuit »."
    )
    rows = [
        [InlineKeyboardButton("🎁 Générer un code gratuit", callback_data="admin_gen_code")],
        [InlineKeyboardButton("👥 Gérer les accès", callback_data="admin_users")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_admin_gen_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    with session_scope() as session:
        user = get_or_create_user(session, update.effective_user)
        if not user.is_admin:
            await query.answer("Accès refusé.", show_alert=True)
            return

        code = FreeAccessCode(code=FreeAccessCode.generate_code(), created_by_user_id=user.id)
        session.add(code)
        session.flush()
        code_value = code.code

    await query.answer()
    text = (
        "🎁 *Nouveau code gratuit généré*\n\n"
        f"`{code_value}`\n\n"
        "Envoyez ce code à la personne concernée. Elle pourra l'activer via "
        "« Abonnement » → « J'ai un code gratuit »."
    )
    rows = [
        [InlineKeyboardButton("➕ Générer un autre code", callback_data="admin_gen_code")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="menu_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    with session_scope() as session:
        admin = get_or_create_user(session, update.effective_user)
        if not admin.is_admin:
            await query.answer("Accès refusé.", show_alert=True)
            return

        active_users = (
            session.query(User)
            .join(Subscription)
            .filter(Subscription.status == Subscription.STATUS_ACTIVE)
            .order_by(User.id)
            .limit(25)
            .all()
        )

        rows = []
        for u in active_users:
            label = f"🚫 {u.display_name} — {u.subscription.label}"
            rows.append([InlineKeyboardButton(label, callback_data=f"admin_revoke_{u.id}")])

    await query.answer()

    if not rows:
        text = "👥 *Gérer les accès*\n\nAucun abonnement actif pour le moment."
    else:
        text = (
            "👥 *Gérer les accès*\n\n"
            "Appuyez sur un utilisateur pour couper son accès "
            "(son abonnement repassera en *inactif*)."
        )

    rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_admin")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def on_admin_revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    target_id = int(query.data.removeprefix("admin_revoke_"))

    with session_scope() as session:
        admin = get_or_create_user(session, update.effective_user)
        if not admin.is_admin:
            await query.answer("Accès refusé.", show_alert=True)
            return

        target = session.get(User, target_id)
        if not target or not target.subscription:
            await query.answer("Utilisateur introuvable.", show_alert=True)
            return

        sub = target.subscription
        sub.status = Subscription.STATUS_CANCELED
        sub.granted_by_admin = False
        target_name = target.display_name

    await query.answer(f"Acces coupe pour {target_name}", show_alert=True)
    await on_admin_users(update, context)


# ---------------------------------------------------------
# Construction de l'application
# ---------------------------------------------------------

def build_application() -> Application:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN n'est pas configuré.")

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(binance_set_start, pattern="^binance_set$"),
            CallbackQueryHandler(rise_set_start, pattern="^rise_set$"),
            CallbackQueryHandler(redeem_code_start, pattern="^sub_redeem$"),
        ],
        states={
            ASK_BINANCE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, binance_set_key)],
            ASK_BINANCE_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, binance_set_secret)],
            ASK_RISE_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, rise_set_wallet)],
            ASK_FREE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_code_apply)],
        },
        fallbacks=[CommandHandler("annuler", cmd_cancel)],
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(conv_handler)

    application.add_handler(CallbackQueryHandler(on_menu_main, pattern="^menu_main$"))
    application.add_handler(CallbackQueryHandler(on_menu_binance, pattern="^menu_binance$"))
    application.add_handler(CallbackQueryHandler(on_menu_rise, pattern="^menu_rise$"))
    application.add_handler(CallbackQueryHandler(on_menu_sub, pattern="^menu_sub$"))
    application.add_handler(CallbackQueryHandler(on_menu_help, pattern="^menu_help$"))
    application.add_handler(CallbackQueryHandler(on_account_delete_confirm, pattern="^account_delete_confirm$"))
    application.add_handler(CallbackQueryHandler(on_account_delete_do, pattern="^account_delete_do$"))
    application.add_handler(CallbackQueryHandler(on_menu_admin, pattern="^menu_admin$"))

    application.add_handler(CallbackQueryHandler(on_binance_remove, pattern="^binance_remove$"))
    application.add_handler(CallbackQueryHandler(on_rise_remove, pattern="^rise_remove$"))

    application.add_handler(CallbackQueryHandler(on_sub_pay, pattern="^sub_pay_(monthly|lifetime)$"))
    application.add_handler(CallbackQueryHandler(on_admin_gen_code, pattern="^admin_gen_code$"))
    application.add_handler(CallbackQueryHandler(on_admin_users, pattern="^admin_users$"))
    application.add_handler(CallbackQueryHandler(on_admin_revoke_user, pattern="^admin_revoke_\\d+$"))

    return application
