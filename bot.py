"""
MI NEXUS TRADING BOT
Local candlestick pattern analysis + next-candle bias prediction.
No external AI / paid API used - pure OpenCV + geometric rule engine.
Data is persisted in Firebase Firestore (survives GitHub Actions restarts).

Run:
    export BOT_TOKEN="your_telegram_bot_token"
    export FIREBASE_CREDENTIALS_JSON='{...service account json...}'
    export ADMIN_USER_ID="8865257002"
    export IMGBB_API_KEY="your_imgbb_key"
    python bot.py
"""

import os
import random
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from utils.candle_detector import detect_candles
from utils.pattern_engine import predict_next_candle
from utils.image_renderer import render_result_card
from utils.pair_detector import detect_pair_name
from utils.indicator_reader import detect_rsi_signal
from utils.sticker_generator import (
    get_direction_sticker, get_session_start_sticker, get_result_sticker
)
from utils.imgbb_uploader import upload_image
from utils.firebase_db import (
    init_firebase, get_user, create_user, unlock_user, is_unlocked,
    set_user_timeframe, get_timeframe, set_trade_duration, get_trade_duration,
    register_group, list_groups,
    get_group_title, log_signal, set_signal_result, get_win_loss_stats,
    set_auto_broadcast, get_auto_broadcast_settings,
    PLAN_LIMITS, get_active_plan, activate_plan, check_and_increment_usage,
    create_payment_request, get_payment, update_payment_status,
    list_pending_payments, set_plan_qr_code, get_plan_qr_code,
    block_user, unblock_user, is_blocked, freeze_user, unfreeze_user,
    is_frozen, list_all_users, find_user_by_username, increment_total_signals,
    get_bot_config, adjust_signal_sensitivity,
    start_free_trial, has_used_trial,
    get_quotex_tracking_link, get_quotex_deposit_status,
    get_quotex_tiers, set_quotex_tier, remove_quotex_tier, tier_for_amount,
    get_quotex_full_profile, list_users_with_quotex_activity,
)
import asyncio

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "8865257002"))
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
BANNER_PATH = os.path.join(os.path.dirname(__file__), "assets", "banner.png")
VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "assets", "videos")
INTRO_VIDEOS = [
    os.path.join(VIDEOS_DIR, "intro_1.mp4"),
    os.path.join(VIDEOS_DIR, "intro_2.mp4"),
    os.path.join(VIDEOS_DIR, "intro_3.mp4"),
]
# Chance (0.0-1.0) that a random intro/animation video is sent alongside
# an analysis - keeps it feeling premium without spamming every single time.
VIDEO_SHOW_CHANCE = 0.35

TIMEFRAME_OPTIONS = [
    ("5 Sec", "5s"), ("15 Sec", "15s"), ("30 Sec", "30s"),
    ("1 Min", "1m"), ("2 Min", "2m"), ("3 Min", "3m"),
    ("5 Min", "5m"), ("15 Min", "15m"), ("30 Min", "30m"), ("1 Hour", "1h"),
]

# Trade Duration = how long the user plans to hold the trade once placed.
# Separate from chart Timeframe (which candle interval is being analyzed) -
# a user might read a 1-min chart but place a 5-min duration trade.
TRADE_DURATION_OPTIONS = [
    ("5 Sec", "5s"), ("15 Sec", "15s"), ("30 Sec", "30s"),
    ("1 Min", "1m"), ("2 Min", "2m"), ("3 Min", "3m"),
    ("5 Min", "5m"), ("10 Min", "10m"), ("15 Min", "15m"),
    ("30 Min", "30m"), ("1 Hour", "1h"),
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MI_NEXUS")

TF_LABELS = {code: label for label, code in TIMEFRAME_OPTIONS}
DURATION_LABELS = {code: label for label, code in TRADE_DURATION_OPTIONS}


def is_admin(user_id):
    return user_id == ADMIN_USER_ID


async def maybe_send_intro_video(update: Update, context: ContextTypes.DEFAULT_TYPE, force=False):
    """
    Randomly (or forced) sends one of the MI NEXUS intro/animation clips.
    Silently does nothing if no video files are present or on send failure -
    this is a cosmetic touch, never a required step.
    """
    available = [v for v in INTRO_VIDEOS if os.path.exists(v)]
    if not available:
        return
    if not force and random.random() > VIDEO_SHOW_CHANCE:
        return
    try:
        with open(random.choice(available), "rb") as vid:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=vid,
                supports_streaming=True,
            )
    except Exception as e:
        logger.warning(f"Intro video send failed (non-critical): {e}")


BLOCKED_MESSAGE = (
    "🚫 *Access Restricted*\n\n"
    "Your account has been blocked from using MI NEXUS.\n"
    "If you believe this is a mistake, please contact the admin."
)

FROZEN_MESSAGE = (
    "🧊 *Account Frozen*\n\n"
    "Your account access has been temporarily frozen by the admin — "
    "signal analysis is paused until it's unfrozen.\n"
    "Please contact the admin for details."
)


async def _moderation_gate(update: Update, user_id: int) -> bool:
    # Checks block/freeze status for a non-admin user and replies with the
    # right message if they're gated. Returns True if the user should be
    # stopped here (blocked/frozen), False if they're free to continue.
    # Admins are always exempt.
    if is_admin(user_id):
        return False
    if is_blocked(user_id):
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(BLOCKED_MESSAGE, parse_mode="Markdown")
        return True
    if is_frozen(user_id):
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(FROZEN_MESSAGE, parse_mode="Markdown")
        return True
    return False


# ----------------------------------------------------------------------
# HANDLERS
# ----------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type in ("group", "supergroup"):
        register_group(chat.id, chat.title or "Unnamed Group")
        await update.message.reply_text(
            "🟢 *MI NEXUS* activated in this group!\n\n"
            "This group will now receive broadcasted signals sent from "
            "the bot's private chat. The bot does *not* analyze images "
            "posted directly here.",
            parse_mode="Markdown"
        )
        return

    create_user(user.id, user.username or user.first_name)

    if await _moderation_gate(update, user.id):
        return

    if is_unlocked(user.id):
        await send_main_menu(update, context)
    else:
        await play_intro_animation(update, context)

        # Premium banner image, if available, sets the visual tone before the welcome text
        if os.path.exists(BANNER_PATH):
            try:
                with open(BANNER_PATH, "rb") as banner:
                    await context.bot.send_photo(chat_id=chat.id, photo=banner)
            except Exception as e:
                logger.warning(f"Banner send failed (non-critical): {e}")

        # First-time users get a guaranteed animation clip for a strong first impression
        await maybe_send_intro_video(update, context, force=True)

        keyboard = [[InlineKeyboardButton("🚀 Create Account / Login", callback_data="account_login")]]
        await update.message.reply_text(
            "💎 *Welcome to MI NEXUS* 💎\n\n"
            "The world's most advanced local chart pattern analyzer.\n\n"
            "🕯️ 100+ candlestick patterns\n"
            "📊 RSI confluence scoring\n"
            "⬆️⬇️ Next-candle predictions\n"
            "💎 Premium signal cards\n"
            "🎯 Live-tuned signal engine\n\n"
            "Tap below to get started — no password needed, your Telegram "
            "account *is* your login.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def play_intro_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Plays a short, cinematic boot-up sequence via progressive message
    edits before the welcome card appears — gives MI NEXUS a 'pro engine
    starting up' feel instead of dumping a static wall of text.
    Uses only edit_text calls (no external video asset required), so it
    works everywhere without extra files to ship.
    """
    frames = [
        "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️  0%\n_Initializing MI NEXUS..._",
        "▪️▪️▫️▫️▫️▫️▫️▫️▫️▫️  20%\n_Loading pattern library (100+ formations)..._",
        "▪️▪️▪️▪️▫️▫️▫️▫️▫️▫️  40%\n_Calibrating RSI confluence engine..._",
        "▪️▪️▪️▪️▪️▪️▫️▫️▫️▫️  60%\n_Syncing prediction core..._",
        "▪️▪️▪️▪️▪️▪️▪️▪️▫️▫️  80%\n_Polishing premium signal cards..._",
        "▪️▪️▪️▪️▪️▪️▪️▪️▪️▪️  100%\n_🟢 MI NEXUS is online!_",
    ]
    try:
        msg = await update.message.reply_text(f"⚡ *MI NEXUS BOOT SEQUENCE*\n\n{frames[0]}", parse_mode="Markdown")
        for frame in frames[1:]:
            await asyncio.sleep(0.45)
            await msg.edit_text(f"⚡ *MI NEXUS BOOT SEQUENCE*\n\n{frame}", parse_mode="Markdown")
        await asyncio.sleep(0.5)
        await msg.delete()
    except Exception as e:
        logger.warning(f"Intro animation failed (non-critical): {e}")


def build_main_menu_keyboard(user_id):
    """Shared keyboard builder for the main menu — used by both the
    /start / /menu flow and the 'Back to Menu' callback, so both stay
    in sync automatically instead of drifting apart over time."""
    keyboard = [
        [
            InlineKeyboardButton("⏱ Timeframe", callback_data="menu_timeframe"),
            InlineKeyboardButton("⏳ Trade Duration", callback_data="menu_trade_duration"),
        ],
        [
            InlineKeyboardButton("📊 My Stats", callback_data="menu_stats"),
            InlineKeyboardButton("💳 My Plan", callback_data="menu_plan_status"),
        ],
        [InlineKeyboardButton("🔥 Upgrade Plan", callback_data="menu_upgrade_shortcut")],
        [InlineKeyboardButton("🔗 Get Free Quotex Link", callback_data="menu_quotex_link")],
        [InlineKeyboardButton("📖 How To Use — Full Guide", callback_data="menu_help")],
    ]

    if is_admin(user_id):
        auto_bc, selected_group = get_auto_broadcast_settings(user_id)
        bc_status = "🟢 ON" if auto_bc else "🔴 OFF"
        keyboard.insert(2, [
            InlineKeyboardButton(f"📢 Auto-Broadcast: {bc_status}", callback_data="menu_broadcast_settings"),
        ])
        keyboard.insert(3, [
            InlineKeyboardButton("🎬 Session Start", callback_data="menu_session_start"),
            InlineKeyboardButton("👥 Groups", callback_data="menu_groups"),
        ])
        keyboard.insert(4, [
            InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_open"),
        ])

    return InlineKeyboardMarkup(keyboard)


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tf = get_timeframe(user_id)
    tf_label = TF_LABELS.get(tf, "1 Min")
    dur = get_trade_duration(user_id)
    dur_label = DURATION_LABELS.get(dur, "1 Min")

    text = (
        "✨ *MI NEXUS — MAIN MENU* ✨\n\n"
        f"⏱ Chart Timeframe: *{tf_label}*\n"
        f"⏳ Trade Duration: *{dur_label}*\n\n"
        "📸 Send me any trading chart screenshot and I'll analyze it:\n"
        "• 100+ candlestick pattern detection\n"
        "• RSI confluence + trend momentum scoring\n"
        "• Next candle prediction (UP/DOWN)\n"
        "• Confidence percentage\n\n"
        "_Just upload an image to get started!_"
    )

    if is_admin(user_id):
        text += "\n\n🛠️ _Admin controls available below._"

    markup = build_main_menu_keyboard(user_id)

    if update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        return  # ignore plain text in groups (no password gate needed there)

    user = update.effective_user
    text = update.message.text.strip()

    if await _moderation_gate(update, user.id):
        return

    # ---- Admin: cancel any pending admin text-input flow ----
    if text == "/cancel" and is_admin(user.id):
        context.user_data["awaiting_admin_broadcast_text"] = False
        context.user_data["awaiting_quotex_tier"] = None
        await update.message.reply_text("❌ Cancelled.")
        return

    # ---- Admin: awaiting a Quotex tier add/edit/delete ----
    if is_admin(user.id) and context.user_data.get("awaiting_quotex_tier") is not None:
        target = context.user_data.get("awaiting_quotex_tier")
        context.user_data["awaiting_quotex_tier"] = None

        if target == "new":
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text(
                    "⚠️ Please send two numbers like `25 60`. Try again via "
                    "the admin panel.", parse_mode="Markdown"
                )
                return
            try:
                threshold, limit = float(parts[0]), int(parts[1])
            except ValueError:
                await update.message.reply_text("⚠️ Both values must be numbers. Try again via the admin panel.")
                return
            set_quotex_tier(threshold, limit)
            await update.message.reply_text(
                f"✅ New tier added: *${threshold}* → *{limit} analyses/day*",
                parse_mode="Markdown"
            )
            return
        else:
            threshold = target
            if text.strip().lower() == "delete":
                remove_quotex_tier(threshold)
                await update.message.reply_text(f"🗑️ Tier ${threshold} removed.")
                return
            try:
                new_limit = int(text.strip())
            except ValueError:
                await update.message.reply_text("⚠️ Please send a whole number, or `delete`. Try again via the admin panel.")
                return
            set_quotex_tier(threshold, new_limit)
            await update.message.reply_text(
                f"✅ Tier updated: *${threshold}* → *{new_limit} analyses/day*",
                parse_mode="Markdown"
            )
            return

    # ---- Admin: awaiting broadcast text to send to all groups ----
    if is_admin(user.id) and context.user_data.get("awaiting_admin_broadcast_text"):
        context.user_data["awaiting_admin_broadcast_text"] = False
        groups = list_groups()
        if not groups:
            await update.message.reply_text("⚠️ No connected groups to broadcast to yet.")
            return

        sent, failed = 0, 0
        broadcast_text = f"📢 *MI NEXUS ANNOUNCEMENT*\n\n{text}"
        for group_id, group_title in groups:
            try:
                await context.bot.send_message(chat_id=group_id, text=broadcast_text, parse_mode="Markdown")
                sent += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for group {group_id}: {e}")
                failed += 1
        await update.message.reply_text(
            f"✅ *Broadcast sent!*\n\n📨 Delivered: *{sent}*\n"
            f"{'⚠️ Failed: ' + str(failed) if failed else ''}",
            parse_mode="Markdown"
        )
        return

    # ---- Awaiting pair name for a manual "Session Start" post ----
    if context.user_data.get("awaiting_session_pair"):
        context.user_data["awaiting_session_pair"] = False
        group_id = context.user_data.get("session_target_group")

        if not group_id:
            await update.message.reply_text("⚠️ Session target lost. Please try again from the menu.")
            return

        pair_name = text
        tf = get_timeframe(user.id)
        tf_label = TF_LABELS.get(tf, "1 Min")
        group_name = get_group_title(group_id)

        sticker_path = get_session_start_sticker(
            output_path=f"/tmp/mi_nexus_session_sticker_{user.id}.webp"
        )

        session_caption = (
            f"🎬 *MI NEXUS — TRADING SESSION STARTED* 🎬\n\n"
            f"💹 Pair: *{pair_name}*\n"
            f"⏱ Timeframe: *{tf_label}*\n\n"
            f"📢 _Everyone open this pair — signals incoming!_ 🔥"
        )

        try:
            if sticker_path:
                with open(sticker_path, "rb") as sticker:
                    await context.bot.send_sticker(chat_id=group_id, sticker=sticker)
            await context.bot.send_message(chat_id=group_id, text=session_caption, parse_mode="Markdown")
            await update.message.reply_text(
                f"✅ Session-start post sent to *{group_name}*!", parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Session start post failed: {e}")
            await update.message.reply_text("⚠️ Failed to post — the bot may have been removed from that group.")
        return

    if is_unlocked(user.id):
        await update.message.reply_text(
            "📸 Please send a *chart screenshot* to get your signal.\n"
            "Use /menu to see options.",
            parse_mode="Markdown"
        )
        return

    # No account yet - prompt them to the Create Account / Login button instead
    keyboard = [[InlineKeyboardButton("🚀 Create Account / Login", callback_data="account_login")]]
    await update.message.reply_text(
        "👋 You don't have an account yet — tap below to get started, no password needed.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_unlocked(user.id):
        await update.message.reply_text("🔐 Please enter the access password first.")
        return
    await send_main_menu(update, context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if await _moderation_gate(update, user_id):
        return

    # ---- Route plan selection ----
    if data.startswith("plan_"):
        plan_id = data.replace("plan_", "")
        await handle_plan_selection(query, context, plan_id)
        return

    # ---- Account creation / login (replaces the old password flow) ----
    if data == "account_login":
        unlock_user(user_id)
        if not has_used_trial(user_id):
            keyboard = [[InlineKeyboardButton("🎁 Start My Free Trial (10 signals / 1 day)", callback_data="start_trial")]]
            await query.edit_message_text(
                "✅ *Account Created!*\n\n"
                "Welcome to MI NEXUS — you're all set.\n\n"
                "🎁 You have a *free trial* waiting: *10 free signal analyses, "
                "valid for 1 day*. Tap below to activate it now, or use /plans "
                "later to subscribe to a paid plan.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "✅ *Account Created!*\n\nWelcome to MI NEXUS — you're all set.",
                parse_mode="Markdown"
            )
        await send_main_menu(update, context)
        return

    if data == "start_trial":
        started = start_free_trial(user_id)
        if started:
            await query.edit_message_text(
                "🎁 *Free Trial Activated!*\n\n"
                "✅ 10 signal analyses\n"
                "⏳ Valid for 1 day\n\n"
                "Send a chart screenshot now to use your first signal!",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "⚠️ You've already used your free trial.\n\nUse /plans to subscribe to a paid plan.",
                parse_mode="Markdown"
            )
        return

    # ---- Route admin panel callbacks ----
    ADMIN_CALLBACK_PREFIXES = (
        "admin_", "setqr_", "payapprove_", "payreject_",
        "blockuser_", "unblockuser_", "freezeuser_", "unfreezeuser_",
        "tuner_", "quotexedit_", "quotexuser_",
    )
    if data.startswith(ADMIN_CALLBACK_PREFIXES):
        await handle_admin_callback(query, context, data)
        return

    # ---- Admin-only guard: broadcast + session-start controls are never
    # available to regular clients, even if they somehow trigger the callback ----
    ADMIN_ONLY_PREFIXES = (
        "menu_broadcast_settings", "autobc_", "menu_session_start",
        "sessionpick_", "broadcast_", "menu_groups",
    )
    if data.startswith(ADMIN_ONLY_PREFIXES) and not is_admin(user_id):
        await query.edit_message_text("🔒 This feature is available to the admin only.")
        return

    if data == "menu_timeframe":
        keyboard = []
        row = []
        for i, (label, code) in enumerate(TIMEFRAME_OPTIONS):
            row.append(InlineKeyboardButton(label, callback_data=f"tf_{code}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="menu_back")])
        await query.edit_message_text(
            "⏱ *Select Prediction Timeframe*\n\nThis is how far ahead the next candle prediction applies:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("tf_"):
        code = data.replace("tf_", "")
        set_user_timeframe(user_id, code)
        label = TF_LABELS.get(code, code)
        await query.edit_message_text(
            f"✅ Timeframe set to *{label}*\n\nNow send a chart screenshot to analyze!",
            parse_mode="Markdown"
        )

    elif data == "menu_trade_duration":
        keyboard = []
        row = []
        for i, (label, code) in enumerate(TRADE_DURATION_OPTIONS):
            row.append(InlineKeyboardButton(label, callback_data=f"dur_{code}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="menu_back")])

        current = get_trade_duration(user_id)
        current_label = DURATION_LABELS.get(current, "1 Min")

        await query.edit_message_text(
            "⏳ *SET YOUR TRADE DURATION*\n\n"
            f"Currently: *{current_label}*\n\n"
            "This is how long *you* plan to hold each trade once you "
            "place it — it gets shown on every signal card so you always "
            "know what duration the signal was meant for.\n\n"
            "_Tip: shorter durations (5s–1m) move faster and can be "
            "noisier; longer durations (5m+) tend to follow trends more "
            "smoothly._\n\n"
            "👇 Choose your trade duration:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("dur_"):
        code = data.replace("dur_", "")
        set_trade_duration(user_id, code)
        label = DURATION_LABELS.get(code, code)
        await query.edit_message_text(
            f"✅ *Trade Duration set to {label}*\n\n"
            f"Every signal card will now show this as your planned hold time.\n\n"
            f"Send a chart screenshot whenever you're ready!",
            parse_mode="Markdown"
        )

    elif data == "menu_stats":
        wins, losses = get_win_loss_stats(user_id)
        total_trades = wins + losses
        win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0

        active_plan = get_active_plan(user_id)
        plan_label = PLAN_LIMITS.get(active_plan, {}).get("label", "No active plan") if active_plan else "No active plan"

        await query.edit_message_text(
            f"📊 *Your Stats*\n\n"
            f"💳 Plan: *{plan_label}*\n\n"
            f"🎯 Trades Recorded: *{total_trades}*\n"
            f"✅ Wins: *{wins}*\n"
            f"❌ Losses: *{losses}*\n"
            f"📈 Win Rate: *{win_rate}%*\n\n"
            f"_Tap ✅ WIN or ❌ LOSS after each signal to keep this updated._",
            parse_mode="Markdown"
        )

    elif data == "menu_groups":
        groups = list_groups()
        if not groups:
            text = "👥 *No groups yet.*\n\nAdd this bot to a group and send /start there!"
        else:
            lines = "\n".join([f"• {title}" for _, title in groups])
            text = f"👥 *Active Groups ({len(groups)}):*\n\n{lines}"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "menu_help":
        keyboard = [[InlineKeyboardButton("⬅ Back to Menu", callback_data="menu_back")]]
        await query.edit_message_text(
            "📖 *MI NEXUS — COMPLETE GUIDE* 📖\n\n"
            "*━━━ STEP 1: Get Your Signal ━━━*\n"
            "📸 Take a screenshot of your chart (Quotex or any platform) "
            "showing at least 5-6 recent candles clearly.\n"
            "Send it directly to this chat.\n\n"

            "*━━━ STEP 2: Read The Signal Card ━━━*\n"
            "⬆️⬇️ *Direction* — predicted next-candle move (UP/DOWN)\n"
            "📊 *Confidence %* — how strong the signal is (54-96%)\n"
            "🔥 *Strength* — WEAK / MODERATE / STRONG / VERY STRONG\n"
            "🕯️ *Patterns* — which candlestick patterns were detected\n"
            "📈 *Market Condition* — Clean Trend / Mixed / Choppy\n"
            "📉 *RSI Zone* — Overbought/Oversold/Neutral, if detected\n\n"

            "*━━━ STEP 3: Decide Whether To Trade ━━━*\n"
            "✅ Best conditions to enter:\n"
            "  • Confidence 72%+ (STRONG or VERY STRONG)\n"
            "  • Market Condition = Clean Trend\n"
            "  • RSI agrees with the direction (if shown)\n\n"
            "⚠️ Be cautious / consider skipping when:\n"
            "  • Confidence is below 62% (WEAK)\n"
            "  • Market Condition = Choppy\n"
            "  • RSI disagrees with the pattern direction\n\n"

            "*━━━ STEP 4: Set Your Timeframe ━━━*\n"
            "Use ⏱ Change Timeframe in the menu to match your trade "
            "duration (5 sec up to 1 hour) — this is shown on your card "
            "for reference.\n\n"

            "*━━━ STEP 5: Place Your Trade ━━━*\n"
            "Open your broker platform, select the same pair as your "
            "chart, and place the trade in the *same direction* as the "
            "signal, for your chosen timeframe.\n\n"

            "*━━━ STEP 6: Log Your Result ━━━*\n"
            "After the trade closes, come back and tap ✅ WIN or ❌ LOSS "
            "under your signal — this updates your personal stats "
            "(📊 My Stats) so you can track your performance over time.\n\n"

            "*━━━ Risk Management Tips ━━━*\n"
            "• Never risk more than you can afford to lose\n"
            "• Don't chase losses with bigger trades\n"
            "• Skip choppy/low-confidence signals — waiting is a valid choice\n"
            "• Treat this as ONE input among many, not a guarantee\n\n"

            "⚠️ *Disclaimer:* This is a technical pattern-analysis tool. "
            "No prediction system — human or automated — can guarantee "
            "market outcomes. Trade responsibly and at your own risk.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "menu_back":
        await query.edit_message_text(
            "✨ *MI NEXUS Main Menu*", parse_mode="Markdown",
            reply_markup=build_main_menu_keyboard(user_id)
        )

    elif data == "menu_upgrade_shortcut":
        await query.edit_message_text(
            "💎 *Upgrade Your Plan*\n\nUse /plans in this chat to see available "
            "plans and subscribe — you'll get a QR code to pay and can send "
            "your payment screenshot right here.",
            parse_mode="Markdown"
        )

    elif data == "menu_quotex_link":
        link = get_quotex_tracking_link(user_id)
        total_deposit, quotex_limit = get_quotex_deposit_status(user_id)
        tiers = sorted(get_quotex_tiers(), key=lambda t: t[0])
        tiers_text = "\n".join(f"• Deposit ${t[0]} → {t[1]} analyses/day" for t in tiers)

        status_text = ""
        if total_deposit and total_deposit > 0:
            status_text = f"\n\n📊 Your verified deposit: *${total_deposit:.2f}* → *{quotex_limit or 0} analyses/day*"

        await query.edit_message_text(
            f"🔗 *Your Personal Quotex Link*\n\n`{link}`\n\n"
            f"Sign up through this link and deposit — your daily analysis "
            f"limit unlocks automatically:\n{tiers_text}"
            f"{status_text}",
            parse_mode="Markdown"
        )

    # ---------------- Plan Status (client-facing) ----------------
    elif data == "menu_plan_status":
        active_plan = get_active_plan(user_id)
        if active_plan:
            plan_label = PLAN_LIMITS.get(active_plan, {}).get("label", active_plan)
            limit = PLAN_LIMITS.get(active_plan, {}).get("daily_limit")
            limit_text = "Unlimited" if limit is None else f"{limit}/day"
            await query.edit_message_text(
                f"💳 *Your Plan*\n\n"
                f"Active Plan: *{plan_label}*\n"
                f"Daily Limit: *{limit_text}*\n\n"
                f"Use /plans to upgrade or renew.",
                parse_mode="Markdown"
            )
        else:
            if not has_used_trial(user_id):
                tkb = [[InlineKeyboardButton("🎁 Start Free Trial", callback_data="start_trial")]]
                await query.edit_message_text(
                    "💳 *No Active Plan*\n\n"
                    "You don't have a subscription yet — try your *free trial* "
                    "(10 signals, 1 day) or use /plans to subscribe.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(tkb)
                )
            else:
                await query.edit_message_text(
                    "💳 *No Active Plan*\n\n"
                    "You don't have a subscription yet.\n"
                    "Use /plans to see available plans and subscribe.",
                    parse_mode="Markdown"
                )

    # ---------------- Open Admin Panel from main menu ----------------
    elif data == "admin_open":
        if not is_admin(user_id):
            return
        await show_admin_panel(query, context)

    # ---------------- Auto-Broadcast Settings ----------------
    elif data == "menu_broadcast_settings":
        auto_bc, selected_group = get_auto_broadcast_settings(user_id)
        groups = list_groups()

        if not groups:
            await query.edit_message_text(
                "⚠️ *No groups connected yet.*\n\n"
                "Add this bot to a group first (send /start there), "
                "then come back to enable auto-broadcast.",
                parse_mode="Markdown"
            )
            return

        status = "🟢 ON" if auto_bc else "🔴 OFF"
        group_name = get_group_title(selected_group) if selected_group else "None selected"

        keyboard = []
        if auto_bc:
            keyboard.append([InlineKeyboardButton("🔴 Turn OFF Auto-Broadcast", callback_data="autobc_off")])
        else:
            keyboard.append([InlineKeyboardButton("🟢 Turn ON Auto-Broadcast", callback_data="autobc_pick_group")])
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="menu_back")])

        await query.edit_message_text(
            f"📢 *Auto-Broadcast Settings*\n\n"
            f"Status: *{status}*\n"
            f"Target Group: *{group_name}*\n\n"
            f"_When ON, every signal you analyze is automatically sent "
            f"to your selected group — no manual tap needed._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "autobc_pick_group":
        groups = list_groups()
        keyboard = [[InlineKeyboardButton(title, callback_data=f"autobc_set_{chat_id}")]
                    for chat_id, title in groups[:10]]
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="menu_broadcast_settings")])
        await query.edit_message_text(
            "👥 *Select the group for auto-broadcast:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("autobc_set_"):
        group_id = int(data.replace("autobc_set_", ""))
        set_auto_broadcast(user_id, True, group_id)
        group_name = get_group_title(group_id)
        await query.edit_message_text(
            f"✅ *Auto-Broadcast ENABLED*\n\nTarget: *{group_name}*\n\n"
            f"Every signal you analyze will now be sent there automatically.",
            parse_mode="Markdown"
        )

    elif data == "autobc_off":
        set_auto_broadcast(user_id, False)
        await query.edit_message_text("🔴 Auto-Broadcast turned OFF.", parse_mode="Markdown")

    # ---------------- Manual Session Start Post ----------------
    elif data == "menu_session_start":
        groups = list_groups()
        if not groups:
            await query.edit_message_text(
                "⚠️ *No groups connected yet.* Add this bot to a group first.",
                parse_mode="Markdown"
            )
            return
        keyboard = [[InlineKeyboardButton(title, callback_data=f"sessionpick_{chat_id}")]
                    for chat_id, title in groups[:10]]
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="menu_back")])
        await query.edit_message_text(
            "🎬 *Post Session Start*\n\nSelect which group to post to:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("sessionpick_"):
        group_id = int(data.replace("sessionpick_", ""))
        context.user_data["session_target_group"] = group_id
        context.user_data["awaiting_session_pair"] = True
        await query.edit_message_text(
            "✏️ *Type the pair/asset name for this session*\n\n"
            "Example: `EUR/USD OTC` or `Gold` or `BTC/USD`\n\n"
            "This will be posted as a VIP session-start alert.",
            parse_mode="Markdown"
        )

    elif data.startswith("broadcast_"):
        target = data.replace("broadcast_", "")
        signal_path = context.user_data.get("last_signal_path")
        signal_caption = context.user_data.get("last_signal_caption")
        signal_direction = context.user_data.get("last_signal_direction")
        signal_confidence = context.user_data.get("last_signal_confidence")

        if not signal_path or not os.path.exists(signal_path):
            await query.edit_message_text("⚠️ Signal expired. Please analyze a new chart.")
            return

        groups = list_groups()
        targets = groups if target == "all" else [g for g in groups if str(g[0]) == target]

        sticker_path = None
        if signal_direction:
            sticker_path = get_direction_sticker(
                signal_direction,
                output_path=f"/tmp/mi_nexus_broadcast_sticker_{user_id}.webp"
            )

        sent_count = 0
        for chat_id, title in targets:
            try:
                with open(signal_path, "rb") as img:
                    await context.bot.send_photo(
                        chat_id=chat_id, photo=img,
                        caption=signal_caption, parse_mode="Markdown"
                    )
                if sticker_path and os.path.exists(sticker_path):
                    with open(sticker_path, "rb") as sticker:
                        await context.bot.send_sticker(chat_id=chat_id, sticker=sticker)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast to {chat_id}: {e}")

        await query.edit_message_text(f"✅ Signal + sticker sent to {sent_count} group(s)!")

    # ---------------- Win / Loss Result ----------------
    elif data.startswith("result_"):
        _, result, signal_id = data.split("_", 2)
        set_signal_result(signal_id, result.upper())

        is_win = result.upper() == "WIN"
        wins, losses = get_win_loss_stats(user_id)
        total = wins + losses
        win_rate = round((wins / total) * 100, 1) if total > 0 else 0

        await query.edit_message_text(
            f"{'✅' if is_win else '❌'} Result logged: *{result.upper()}*\n\n"
            f"📊 Your Record: *{wins}W / {losses}L* ({win_rate}% win rate)",
            parse_mode="Markdown"
        )

        # Only the ADMIN's results get posted to groups - regular clients
        # just log their own personal result privately.
        if is_admin(user_id):
            result_sticker_path = get_result_sticker(
                is_win, output_path=f"/tmp/mi_nexus_result_sticker_{user_id}_{signal_id}.webp"
            )
            auto_bc, selected_group = get_auto_broadcast_settings(user_id)
            target_groups = []
            if selected_group:
                target_groups = [(selected_group, get_group_title(selected_group))]
            else:
                target_groups = list_groups()[:1]

            emoji = "🎉✅" if is_win else "❌💪"
            result_caption = (
                f"{emoji} *TRADE RESULT: {result.upper()}* {emoji}\n\n"
                f"MI NEXUS Signal Outcome\n"
                f"_{'Great call! Onwards to the next one.' if is_win else 'Not every trade wins — stay disciplined.'}_"
            )

            sent = 0
            for chat_id, title in target_groups:
                try:
                    if result_sticker_path:
                        with open(result_sticker_path, "rb") as sticker:
                            await context.bot.send_sticker(chat_id=chat_id, sticker=sticker)
                    await context.bot.send_message(chat_id=chat_id, text=result_caption, parse_mode="Markdown")
                    sent += 1
                except Exception as e:
                    logger.warning(f"Failed to post result to {chat_id}: {e}")

            if sent:
                await query.message.reply_text(f"📢 Also posted to {sent} group(s).")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type in ("group", "supergroup"):
        # Groups only RECEIVE broadcasted signals - the bot never analyzes
        # images posted directly inside a group chat.
        return

    # ---- Route: admin uploading a plan QR code ----
    if is_admin(user.id) and context.user_data.get("awaiting_qr_upload"):
        await handle_qr_upload(update, context)
        return

    if await _moderation_gate(update, user.id):
        return

    # ---- Route: user sending a payment screenshot ----
    if context.user_data.get("awaiting_payment_screenshot"):
        await handle_payment_screenshot(update, context)
        return

    if not is_unlocked(user.id):
        await update.message.reply_text("🔐 Please enter the access password first. Use /start")
        return

    # ---- Subscription plan gating (admin is exempt) ----
    if not is_admin(user.id):
        allowed, remaining, plan_id = check_and_increment_usage(user.id)
        if not allowed:
            if plan_id is None:
                if not has_used_trial(user.id):
                    keyboard = [[InlineKeyboardButton("🎁 Start Free Trial (10 signals / 1 day)", callback_data="start_trial")]]
                    await update.message.reply_text(
                        "🔒 *No Active Plan*\n\n"
                        "You need an active subscription to analyze charts — "
                        "or activate your *free trial* below to try MI NEXUS "
                        "right now (10 free signals, valid 1 day).\n\n"
                        "Use /plans to see paid plans anytime.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await update.message.reply_text(
                        "🔒 *No Active Plan*\n\n"
                        "You need an active subscription to analyze charts.\n"
                        "Use /plans to see available plans and subscribe.",
                        parse_mode="Markdown"
                    )
            else:
                plan_label = PLAN_LIMITS.get(plan_id, {}).get("label", plan_id)
                await update.message.reply_text(
                    f"🔒 *Daily Limit Reached*\n\n"
                    f"Your *{plan_label}* plan's daily analysis limit is used up.\n"
                    f"It resets tomorrow, or use /plans to upgrade.",
                    parse_mode="Markdown"
                )
            return

    await context.bot.send_chat_action(chat_id=chat.id, action="upload_photo")
    await maybe_send_intro_video(update, context)  # random chance, cosmetic only

    processing_msg = await update.message.reply_text(
        "⚡ *MI NEXUS Engine Starting...*\n░░░░░░░░░░ 0%",
        parse_mode="Markdown"
    )

    try:
        photo_file = await update.message.photo[-1].get_file()
        local_path = f"/tmp/mi_nexus_input_{user.id}_{update.message.message_id}.jpg"
        await photo_file.download_to_drive(local_path)

        await processing_msg.edit_text(
            "🔍 *Detecting candlesticks...*\n▓▓▓░░░░░░░ 30%",
            parse_mode="Markdown"
        )
        candles, cropped_chart, offset = detect_candles(local_path)

        if len(candles) < 3:
            await processing_msg.edit_text(
                "⚠️ *Could not detect enough candles.*\n\n"
                "Tips for best results:\n"
                "• Zoom in so candles are clearly visible\n"
                "• Avoid heavy overlays covering the chart\n"
                "• Use good lighting/contrast screenshots",
                parse_mode="Markdown"
            )
            return

        await processing_msg.edit_text(
            "🧮 *Matching 89 pattern signatures...*\n▓▓▓▓▓▓░░░░ 60%",
            parse_mode="Markdown"
        )
        rsi_signal = detect_rsi_signal(local_path)
        bot_cfg = get_bot_config()
        prediction = predict_next_candle(
            candles, rsi_signal=rsi_signal,
            sensitivity=bot_cfg.get("signal_sensitivity", 1.0)
        )
        tf_code = get_timeframe(user.id)
        tf_label = TF_LABELS.get(tf_code, "1 Min")
        dur_code = get_trade_duration(user.id)
        dur_label = DURATION_LABELS.get(dur_code, "1 Min")

        pair_name = detect_pair_name(local_path) or "Chart Analysis"

        await processing_msg.edit_text(
            "🎨 *Rendering your signal card...*\n▓▓▓▓▓▓▓▓▓░ 90%",
            parse_mode="Markdown"
        )

        output_path = f"/tmp/mi_nexus_result_{user.id}_{update.message.message_id}.png"
        render_result_card(
            chart_image_path=local_path,
            prediction=prediction,
            pair_name=pair_name,
            timeframe_label=tf_label,
            trade_duration_label=dur_label,
            utc_offset_hours=5,
            logo_path=LOGO_PATH if os.path.exists(LOGO_PATH) else None,
            output_path=output_path,
            candles=candles,
        )

        log_id = log_signal(user.id, prediction["direction"], prediction["confidence"], tf_code)
        increment_total_signals(user.id)

        is_up = prediction["direction"] == "UP"
        dir_emoji = "🟢⬆️" if is_up else "🔴⬇️"
        strength = prediction.get("strength", "MODERATE")
        strength_emoji = {"VERY STRONG": "🔥🔥🔥", "STRONG": "🔥🔥", "MODERATE": "🔥", "WEAK": "⚡"}.get(strength, "⚡")

        top_pattern = "N/A"
        if prediction.get("breakdown"):
            top_pattern = sorted(prediction["breakdown"], key=lambda p: p["reliability"], reverse=True)[0]["name"]

        pattern_count = len(prediction.get("breakdown", []))
        choppiness = prediction.get("choppiness", 0)
        if choppiness < 0.3:
            condition_text = "🟢 Clean Trend"
        elif choppiness < 0.6:
            condition_text = "🟡 Mixed"
        else:
            condition_text = "🔴 Choppy"

        rsi_line = ""
        rsi_data = prediction.get("rsi_signal")
        if rsi_data:
            rsi_agrees = prediction.get("rsi_agrees")
            agree_symbol = " ✅" if rsi_agrees else (" ⚠️" if rsi_agrees is False else "")
            rsi_line = f"📉 RSI Zone: *{rsi_data['zone']}*{agree_symbol}\n"

        caption = (
            f"💎 *MI NEXUS PREMIUM SIGNAL* 💎\n\n"
            f"{dir_emoji} Direction: *{prediction['direction']}*\n"
            f"📊 Confidence: *{prediction['confidence']}%* {strength_emoji}\n"
            f"⏱ Timeframe: *{tf_label}*\n"
            f"⏳ Trade Duration: *{dur_label}*\n"
            f"🕯️ Key Pattern: *{top_pattern}* ({pattern_count} total detected)\n"
            f"📈 Market Condition: *{condition_text}*\n"
            f"{rsi_line}"
            f"💹 Pair: *{pair_name}*\n\n"
            f"✅ _Trade smart, manage your risk._"
        )

        with open(output_path, "rb") as img:
            await update.message.reply_photo(photo=img, caption=caption, parse_mode="Markdown")

        # Send matching UP/DOWN sticker (only if you've provided one)
        sticker_path = get_direction_sticker(
            prediction["direction"],
            output_path=f"/tmp/mi_nexus_sticker_{user.id}_{update.message.message_id}.webp"
        )
        if sticker_path:
            with open(sticker_path, "rb") as sticker:
                await update.message.reply_sticker(sticker=sticker)

        # Store this signal so it can be broadcast to groups on request
        context.user_data["last_signal_path"] = output_path
        context.user_data["last_signal_caption"] = caption
        context.user_data["last_signal_direction"] = prediction["direction"]
        context.user_data["last_signal_confidence"] = prediction["confidence"]
        context.user_data["last_signal_id"] = log_id

        # ---- Auto-broadcast: ADMIN ONLY. Regular clients never get group
        # broadcast controls - they only ever receive their own signal. ----
        if is_admin(user.id):
            auto_bc, selected_group = get_auto_broadcast_settings(user.id)
            if auto_bc and selected_group:
                try:
                    with open(output_path, "rb") as img:
                        await context.bot.send_photo(
                            chat_id=selected_group, photo=img,
                            caption=caption, parse_mode="Markdown"
                        )
                    if sticker_path:
                        with open(sticker_path, "rb") as sticker:
                            await context.bot.send_sticker(chat_id=selected_group, sticker=sticker)
                    await update.message.reply_text(
                        f"📢 Auto-broadcast: sent to *{get_group_title(selected_group)}*",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Auto-broadcast failed: {e}")
                    await update.message.reply_text("⚠️ Auto-broadcast failed — group may have removed the bot.")
            else:
                groups = list_groups()
                if groups:
                    keyboard = [[InlineKeyboardButton(
                        f"📢 Send to {title}", callback_data=f"broadcast_{chat_id}"
                    )] for chat_id, title in groups[:8]]
                    keyboard.append([InlineKeyboardButton("📢 Send to ALL Groups", callback_data="broadcast_all")])
                    await update.message.reply_text(
                        "Want to share this signal to your groups?",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )

        # ---- WIN / LOSS result buttons (personal record for everyone) ----
        result_keyboard = [[
            InlineKeyboardButton("✅ WIN", callback_data=f"result_WIN_{log_id}"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"result_LOSS_{log_id}"),
        ]]
        await update.message.reply_text(
            "📋 *After your trade closes, tap the result to log it:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(result_keyboard)
        )

        await processing_msg.delete()

        if os.path.exists(local_path):
            os.remove(local_path)

    except Exception as e:
        logger.exception("Error processing photo")
        await processing_msg.edit_text(f"❌ Error analyzing image: {str(e)}")


# ----------------------------------------------------------------------
# SUBSCRIPTION PLANS + PAYMENT FLOW
# ----------------------------------------------------------------------

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.effective_chat.type in ("group", "supergroup"):
        return

    active_plan = get_active_plan(user.id)
    if active_plan:
        plan_label = PLAN_LIMITS.get(active_plan, {}).get("label", active_plan)
        status_text = f"✅ Active paid plan: *{plan_label}*\n"
    else:
        status_text = ""

    total_deposit, quotex_limit = get_quotex_deposit_status(user.id)
    if total_deposit and total_deposit > 0:
        status_text += f"💹 Quotex verified deposit: *${total_deposit:.2f}* → *{quotex_limit or 0} analyses/day*\n"

    if status_text:
        status_text += "\n"
    else:
        status_text = "You don't have an active plan yet.\n\n"

    tiers = get_quotex_tiers()  # [[threshold, limit], ...] sorted descending
    tiers_ascending = sorted(tiers, key=lambda t: t[0])
    quotex_lines = "\n".join(
        f"• Deposit *${t[0]}* → *{t[1]} analyses/day*" for t in tiers_ascending
    )

    link = get_quotex_tracking_link(user.id)

    keyboard = []
    if not active_plan and not has_used_trial(user.id):
        keyboard.append([InlineKeyboardButton("🎁 Free Trial — 10 signals / 1 day", callback_data="start_trial")])
    keyboard += [
        [InlineKeyboardButton("💵 Basic — Rs 500/mo (15/day)", callback_data="plan_basic")],
        [InlineKeyboardButton("💰 Pro — Rs 1000/mo (35/day)", callback_data="plan_pro")],
        [InlineKeyboardButton("👑 Unlimited — Rs 5000/mo", callback_data="plan_unlimited")],
        [InlineKeyboardButton("🔗 Get My Quotex Link", callback_data="menu_quotex_link")],
    ]

    await update.message.reply_text(
        f"💎 *MI NEXUS Subscription Plans* 💎\n\n"
        f"{status_text}"
        f"*── Option A: Pay Directly (Rs) ──*\n"
        f"Pick a plan below, pay via QR, send your screenshot — admin "
        f"approves and activates it.\n\n"
        f"*── Option B: Free via Quotex Deposit ──*\n"
        f"Sign up on Quotex through your personal link, deposit, and your "
        f"daily limit unlocks automatically — no payment to us at all:\n"
        f"{quotex_lines}\n\n"
        f"Your link:\n`{link}`\n\n"
        f"_Whichever option gives you a higher daily limit is the one "
        f"that applies._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_plan_selection(query, context, plan_id):
    user_id = query.from_user.id
    plan_label = PLAN_LIMITS.get(plan_id, {}).get("label", plan_id)
    qr_url = get_plan_qr_code(plan_id)

    context.user_data["awaiting_payment_screenshot"] = plan_id

    if qr_url:
        await query.message.reply_photo(
            photo=qr_url,
            caption=(
                f"💳 *{plan_label}*\n\n"
                f"Scan this QR code to pay, then send a screenshot of your "
                f"payment confirmation here in this chat.\n\n"
                f"Once you send the screenshot, it goes to the admin for approval."
            ),
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text(
            f"💳 *{plan_label}*\n\n"
            f"⚠️ Payment QR code not set up yet for this plan — please contact the admin.\n\n"
            f"Once available, send your payment screenshot here after paying.",
            parse_mode="Markdown"
        )


async def handle_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when a user sends a photo while awaiting_payment_screenshot is set."""
    user = update.effective_user
    plan_id = context.user_data.get("awaiting_payment_screenshot")
    context.user_data["awaiting_payment_screenshot"] = None

    photo_file = await update.message.photo[-1].get_file()
    local_path = f"/tmp/mi_nexus_payment_{user.id}.jpg"
    await photo_file.download_to_drive(local_path)

    screenshot_url = upload_image(local_path, name=f"payment_{user.id}_{plan_id}")
    if os.path.exists(local_path):
        os.remove(local_path)

    if not screenshot_url:
        await update.message.reply_text(
            "⚠️ Couldn't upload your screenshot right now. Please try again in a moment."
        )
        return

    payment_id = create_payment_request(user.id, user.username or user.first_name, plan_id, screenshot_url)
    plan_label = PLAN_LIMITS.get(plan_id, {}).get("label", plan_id)

    await update.message.reply_text(
        "✅ *Payment screenshot received!*\n\n"
        "Your subscription will be activated once the admin reviews and "
        "approves it. This is usually quick — thanks for your patience!",
        parse_mode="Markdown"
    )

    # Notify admin with approve/reject buttons
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"payapprove_{payment_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"payreject_{payment_id}"),
    ]]
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_USER_ID,
            photo=screenshot_url,
            caption=(
                f"💰 *New Payment Request*\n\n"
                f"User: @{user.username or user.first_name} (ID: `{user.id}`)\n"
                f"Plan: *{plan_label}*\n"
                f"Payment ID: `{payment_id}`"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.warning(f"Failed to notify admin of payment: {e}")


# ----------------------------------------------------------------------
# ADMIN PANEL
# ----------------------------------------------------------------------
async def show_admin_panel(query_or_update, context):
    """Renders the admin panel. Accepts either a CallbackQuery (edits the
    message) or falls through to reply_text for the /admin command."""
    pending = list_pending_payments()
    cfg = get_bot_config()
    sensitivity = cfg.get("signal_sensitivity", 1.0)
    keyboard = [
        [
            InlineKeyboardButton(f"💰 Pending Payments ({len(pending)})", callback_data="admin_pending"),
            InlineKeyboardButton("📷 Set Plan QR Codes", callback_data="admin_setqr"),
        ],
        [
            InlineKeyboardButton("🚫 Manage Members", callback_data="admin_members"),
            InlineKeyboardButton("👥 Connected Groups", callback_data="menu_groups"),
        ],
        [
            InlineKeyboardButton("💹 Quotex Deposit Tiers", callback_data="admin_quotex_tiers"),
            InlineKeyboardButton("📊 Quotex Users", callback_data="admin_quotex_users"),
        ],
        [InlineKeyboardButton(f"🎚️ Signal Tuner ({sensitivity}x)", callback_data="admin_tuner")],
        [InlineKeyboardButton("📢 Broadcast Text to All Groups", callback_data="admin_broadcast_text")],
    ]
    text = (
        "🛠️ *MI NEXUS Admin Panel*\n\n"
        f"💰 Pending payments: *{len(pending)}*\n"
        f"🎚️ Signal sensitivity: *{sensitivity}x*\n\n"
        "_Select a tool below._"
    )
    markup = InlineKeyboardMarkup(keyboard)

    if hasattr(query_or_update, "edit_message_text"):
        await query_or_update.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await query_or_update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def render_member_list(query, context, page=0):
    """
    Admin 'Manage Members' screen — lists recent users with inline
    Block/Unblock and Freeze/Unfreeze buttons next to each one, paginated
    5 at a time so the message stays readable.
    """
    all_users = list_all_users(limit=200)
    page_size = 5
    total_pages = max(1, (len(all_users) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    chunk = all_users[page * page_size: (page + 1) * page_size]

    lines = [f"🚫 *Manage Members* (page {page + 1}/{total_pages})\n"]
    keyboard = []

    if not chunk:
        lines.append("_No users found yet._")
    for u in chunk:
        uid = u.get("user_id")
        uname = u.get("username") or "no-username"
        status_bits = []
        if u.get("blocked"):
            status_bits.append("🚫 Blocked")
        if u.get("frozen"):
            status_bits.append("🧊 Frozen")
        status = " | ".join(status_bits) if status_bits else "✅ Active"
        plan = u.get("plan") or "No plan"
        lines.append(f"👤 *{uname}* (`{uid}`)\n   {status} • Plan: {plan}")

        row = []
        if u.get("blocked"):
            row.append(InlineKeyboardButton("✅ Unblock", callback_data=f"unblockuser_{uid}"))
        else:
            row.append(InlineKeyboardButton("🚫 Block", callback_data=f"blockuser_{uid}"))
        if u.get("frozen"):
            row.append(InlineKeyboardButton("🔥 Unfreeze", callback_data=f"unfreezeuser_{uid}"))
        else:
            row.append(InlineKeyboardButton("🧊 Freeze", callback_data=f"freezeuser_{uid}"))
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅ Prev", callback_data=f"memberpage_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡", callback_data=f"memberpage_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="admin_back_panel")])

    await query.edit_message_text(
        "\n\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def render_signal_tuner(query, context):
    """Admin 'Signal Sensitivity Tuner' — nudges the global multiplier
    that scales every prediction's final score (see predict_next_candle's
    `sensitivity` param), letting the admin dial the engine to be more
    conservative or more aggressive without redeploying code."""
    cfg = get_bot_config()
    sensitivity = cfg.get("signal_sensitivity", 1.0)

    if sensitivity <= 0.85:
        mood = "🟦 Conservative — fewer high-confidence calls, more caution"
    elif sensitivity >= 1.15:
        mood = "🟥 Aggressive — bolder confidence swings"
    else:
        mood = "🟩 Balanced — standard calibration"

    keyboard = [
        [
            InlineKeyboardButton("➖ Decrease", callback_data="tuner_down"),
            InlineKeyboardButton("🔄 Reset (1.0x)", callback_data="tuner_reset"),
            InlineKeyboardButton("➕ Increase", callback_data="tuner_up"),
        ],
        [InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="admin_back_panel")],
    ]
    await query.edit_message_text(
        f"🎚️ *Signal Sensitivity Tuner*\n\n"
        f"Current: *{sensitivity}x*\n"
        f"{mood}\n\n"
        f"_Range: 0.7x (safest) — 1.3x (boldest). Applies to every new "
        f"analysis instantly, no restart needed._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def finduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/finduser <username> — quick admin lookup with block/freeze buttons,
    for when scrolling the paginated member list would be slower."""
    admin = update.effective_user
    if not is_admin(admin.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: `/finduser <username>`", parse_mode="Markdown")
        return

    query_name = context.args[0]
    matches = find_user_by_username(query_name)
    if not matches:
        await update.message.reply_text(f"❌ No user found matching `{query_name}`.", parse_mode="Markdown")
        return

    for u in matches:
        uid = u.get("user_id")
        status_bits = []
        if u.get("blocked"):
            status_bits.append("🚫 Blocked")
        if u.get("frozen"):
            status_bits.append("🧊 Frozen")
        status = " | ".join(status_bits) if status_bits else "✅ Active"
        plan = u.get("plan") or "No plan"

        row = []
        if u.get("blocked"):
            row.append(InlineKeyboardButton("✅ Unblock", callback_data=f"unblockuser_{uid}"))
        else:
            row.append(InlineKeyboardButton("🚫 Block", callback_data=f"blockuser_{uid}"))
        if u.get("frozen"):
            row.append(InlineKeyboardButton("🔥 Unfreeze", callback_data=f"unfreezeuser_{uid}"))
        else:
            row.append(InlineKeyboardButton("🧊 Freeze", callback_data=f"freezeuser_{uid}"))

        await update.message.reply_text(
            f"👤 *{u.get('username')}* (`{uid}`)\n"
            f"{status} • Plan: {plan}\n"
            f"Total signals: {u.get('total_signals', 0)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([row])
        )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return  # silently ignore for non-admins
    await show_admin_panel(update, context)


async def handle_admin_callback(query, context, data):
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("Not authorized.", show_alert=True)
        return

    if data == "admin_pending":
        pending = list_pending_payments()
        if not pending:
            await query.edit_message_text("✅ No pending payments.")
            return
        lines = []
        for p in pending:
            plan_label = PLAN_LIMITS.get(p["plan"], {}).get("label", p["plan"])
            lines.append(f"• @{p.get('username', 'unknown')} — {plan_label} — `{p['payment_id']}`")
        await query.edit_message_text(
            "💰 *Pending Payments:*\n\n" + "\n".join(lines) +
            "\n\n_Use the Approve/Reject buttons sent with each payment notification._",
            parse_mode="Markdown"
        )

    elif data == "admin_members":
        await render_member_list(query, context, page=0)

    elif data.startswith("memberpage_"):
        page = int(data.replace("memberpage_", ""))
        await render_member_list(query, context, page=page)

    elif data.startswith("blockuser_"):
        target_id = int(data.replace("blockuser_", ""))
        block_user(target_id, reason="Blocked by admin")
        await query.answer(f"🚫 Blocked user {target_id}", show_alert=True)
        await render_member_list(query, context, page=0)

    elif data.startswith("unblockuser_"):
        target_id = int(data.replace("unblockuser_", ""))
        unblock_user(target_id)
        await query.answer(f"✅ Unblocked user {target_id}", show_alert=True)
        await render_member_list(query, context, page=0)

    elif data.startswith("freezeuser_"):
        target_id = int(data.replace("freezeuser_", ""))
        freeze_user(target_id)
        await query.answer(f"🧊 Froze account {target_id}", show_alert=True)
        await render_member_list(query, context, page=0)

    elif data.startswith("unfreezeuser_"):
        target_id = int(data.replace("unfreezeuser_", ""))
        unfreeze_user(target_id)
        await query.answer(f"🔥 Unfroze account {target_id}", show_alert=True)
        await render_member_list(query, context, page=0)

    elif data == "admin_tuner":
        await render_signal_tuner(query, context)

    elif data == "tuner_up":
        new_val = adjust_signal_sensitivity(+0.05)
        await query.answer(f"🎚️ Sensitivity: {new_val}x", show_alert=False)
        await render_signal_tuner(query, context)

    elif data == "tuner_down":
        new_val = adjust_signal_sensitivity(-0.05)
        await query.answer(f"🎚️ Sensitivity: {new_val}x", show_alert=False)
        await render_signal_tuner(query, context)

    elif data == "tuner_reset":
        from utils.firebase_db import set_bot_config_value
        set_bot_config_value("signal_sensitivity", 1.0)
        await query.answer("🎚️ Reset to 1.0x", show_alert=False)
        await render_signal_tuner(query, context)

    elif data == "admin_broadcast_text":
        context.user_data["awaiting_admin_broadcast_text"] = True
        await query.edit_message_text(
            "📢 *Broadcast Text to All Groups*\n\n"
            "Type the message you want to send to *every connected group* now.\n"
            "Send /cancel to abort.",
            parse_mode="Markdown"
        )

    elif data == "admin_back_panel":
        await show_admin_panel(query, context)

    # ---------------- Quotex Deposit Tier Management ----------------
    elif data == "admin_quotex_tiers":
        tiers = sorted(get_quotex_tiers(), key=lambda t: t[0])
        lines = "\n".join(f"• ${t[0]} → {t[1]} analyses/day" for t in tiers)
        keyboard = [
            [InlineKeyboardButton(f"✏️ Edit ${t[0]} tier", callback_data=f"quotexedit_{t[0]}")]
            for t in tiers
        ]
        keyboard.append([InlineKeyboardButton("➕ Add New Tier", callback_data="quotexedit_new")])
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="admin_back_panel")])
        await query.edit_message_text(
            f"💹 *Quotex Deposit Tiers*\n\n{lines}\n\n"
            f"_Tap a tier to change its daily-analysis limit, or add a new one._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("quotexedit_"):
        raw = data.replace("quotexedit_", "")
        if raw == "new":
            context.user_data["awaiting_quotex_tier"] = "new"
            await query.edit_message_text(
                "➕ *Add New Tier*\n\n"
                "Send two numbers separated by a space: `deposit_amount daily_limit`\n"
                "Example: `25 60` means a $25 deposit unlocks 60 analyses/day.",
                parse_mode="Markdown"
            )
        else:
            threshold = int(raw)
            context.user_data["awaiting_quotex_tier"] = threshold
            await query.edit_message_text(
                f"✏️ *Editing ${threshold} Tier*\n\n"
                f"Send the new daily-analysis limit as a number, or send "
                f"`delete` to remove this tier entirely.",
                parse_mode="Markdown"
            )

    # ---------------- Quotex Users Overview (strict oversight) ----------------
    elif data == "admin_quotex_users":
        users = list_users_with_quotex_activity()
        if not users:
            await query.edit_message_text(
                "📊 *Quotex Users*\n\nNo users have registered via a Quotex "
                "link yet.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="admin_back_panel")]])
            )
            return

        keyboard = [
            [InlineKeyboardButton(
                f"@{u['username'] or u['user_id']} — ${u['total_deposit']:.0f}",
                callback_data=f"quotexuser_{u['user_id']}"
            )] for u in users[:20]
        ]
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="admin_back_panel")])
        await query.edit_message_text(
            f"📊 *Quotex Users* ({len(users)} total)\n\n"
            f"_Tap a user for their full deposit/withdrawal breakdown._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("quotexuser_"):
        target_id = int(data.replace("quotexuser_", ""))
        profile = get_quotex_full_profile(target_id)
        target_user = get_user(target_id) or {}

        net_emoji = "🟢" if profile["net_position"] >= 0 else "🔴"

        await query.edit_message_text(
            f"📊 *Quotex Profile — @{target_user.get('username', target_id)}*\n\n"
            f"🆔 Telegram ID: `{target_id}`\n"
            f"🎮 Quotex Trader ID: `{profile['trader_id'] or 'N/A'}`\n"
            f"🌍 Country: {profile['country'] or 'N/A'}\n"
            f"✅ Registered: {'Yes' if profile['registered'] else 'No'}\n"
            f"📧 Email Confirmed: {'Yes' if profile['email_confirmed'] else 'No'}\n\n"
            f"💰 Total Deposited: *${profile['total_deposit']:.2f}*\n"
            f"💸 Total Withdrawn: *${profile['total_withdrawn']:.2f}*\n"
            f"{net_emoji} Net Position: *${profile['net_position']:.2f}*\n\n"
            f"🎯 Current Tier: *${profile['tier_threshold'] or 0}* → "
            f"*{profile['daily_limit'] or 0} analyses/day*\n"
            f"🕐 Last Deposit: {profile['last_deposit_at'] or 'N/A'}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="admin_quotex_users")]])
        )

    elif data == "admin_setqr":
        keyboard = [
            [InlineKeyboardButton("Basic Plan QR", callback_data="setqr_basic")],
            [InlineKeyboardButton("Pro Plan QR", callback_data="setqr_pro")],
            [InlineKeyboardButton("Unlimited Plan QR", callback_data="setqr_unlimited")],
        ]
        await query.edit_message_text(
            "📷 *Select which plan's QR code to update:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("setqr_"):
        plan_id = data.replace("setqr_", "")
        context.user_data["awaiting_qr_upload"] = plan_id
        await query.edit_message_text(
            f"📷 Send the QR code image for the *{PLAN_LIMITS.get(plan_id, {}).get('label', plan_id)}* plan now.",
            parse_mode="Markdown"
        )

    elif data.startswith("payapprove_") or data.startswith("payreject_"):
        payment_id = data.split("_", 1)[1]
        payment = get_payment(payment_id)
        if not payment:
            await query.edit_message_caption(caption="⚠️ Payment record not found (may have been processed already).")
            return

        target_user_id = payment["user_id"]
        plan_id = payment["plan"]
        plan_label = PLAN_LIMITS.get(plan_id, {}).get("label", plan_id)

        if data.startswith("payapprove_"):
            update_payment_status(payment_id, "approved")
            activate_plan(target_user_id, plan_id, days=30)
            await query.edit_message_caption(caption=f"✅ Approved — {plan_label} activated for user {target_user_id}.")
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"🎉 *Payment Approved!*\n\nYour *{plan_label}* is now active. Enjoy!",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to notify user of approval: {e}")
        else:
            update_payment_status(payment_id, "rejected")
            await query.edit_message_caption(caption=f"❌ Rejected payment for user {target_user_id}.")
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        "❌ *Payment Not Approved*\n\n"
                        "Your payment screenshot couldn't be verified. "
                        "Please contact the admin or try again with a clearer screenshot."
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to notify user of rejection: {e}")


async def handle_qr_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when the admin sends a photo while awaiting_qr_upload is set."""
    user = update.effective_user
    plan_id = context.user_data.get("awaiting_qr_upload")
    context.user_data["awaiting_qr_upload"] = None

    photo_file = await update.message.photo[-1].get_file()
    local_path = f"/tmp/mi_nexus_qr_{plan_id}.jpg"
    await photo_file.download_to_drive(local_path)

    qr_url = upload_image(local_path, name=f"qr_{plan_id}")
    if os.path.exists(local_path):
        os.remove(local_path)

    if not qr_url:
        await update.message.reply_text("⚠️ Upload failed — please try again.")
        return

    set_plan_qr_code(plan_id, qr_url)
    plan_label = PLAN_LIMITS.get(plan_id, {}).get("label", plan_id)
    await update.message.reply_text(f"✅ QR code updated for *{plan_label}*.", parse_mode="Markdown")


async def error_handler(update, context):
    logger.error("Exception:", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set!")

    init_firebase()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("plans", plans_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("finduser", finduser_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("MI NEXUS Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
