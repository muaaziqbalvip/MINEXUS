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
    set_user_timeframe, get_timeframe, register_group, list_groups,
    get_group_title, log_signal, set_signal_result, get_win_loss_stats,
    set_auto_broadcast, get_auto_broadcast_settings,
    PLAN_LIMITS, get_active_plan, activate_plan, check_and_increment_usage,
    create_payment_request, get_payment, update_payment_status,
    list_pending_payments, set_plan_qr_code, get_plan_qr_code,
)

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "19620MINEXUS")
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "8865257002"))
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")

TIMEFRAME_OPTIONS = [
    ("5 Sec", "5s"), ("15 Sec", "15s"), ("30 Sec", "30s"),
    ("1 Min", "1m"), ("2 Min", "2m"), ("3 Min", "3m"),
    ("5 Min", "5m"), ("15 Min", "15m"), ("30 Min", "30m"), ("1 Hour", "1h"),
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MI_NEXUS")

TF_LABELS = {code: label for label, code in TIMEFRAME_OPTIONS}


def is_admin(user_id):
    return user_id == ADMIN_USER_ID


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

    if is_unlocked(user.id):
        await send_main_menu(update, context)
    else:
        await update.message.reply_text(
            "🔐 *MI NEXUS TRADING BOT*\n\n"
            "Welcome! This bot is password protected.\n"
            "Please enter your access password to continue:",
            parse_mode="Markdown"
        )


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tf = get_timeframe(user_id)
    tf_label = TF_LABELS.get(tf, "1 Min")
    auto_bc, selected_group = get_auto_broadcast_settings(user_id)
    bc_status = "🟢 ON" if auto_bc else "🔴 OFF"

    keyboard = [
        [InlineKeyboardButton("⏱ Change Timeframe", callback_data="menu_timeframe")],
        [InlineKeyboardButton(f"📢 Auto-Broadcast: {bc_status}", callback_data="menu_broadcast_settings")],
        [InlineKeyboardButton("🎬 Post Session Start", callback_data="menu_session_start")],
        [InlineKeyboardButton("📊 My Stats", callback_data="menu_stats")],
        [InlineKeyboardButton("👥 Active Groups", callback_data="menu_groups")],
        [InlineKeyboardButton("ℹ️ How It Works", callback_data="menu_help")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    text = (
        "✅ *MI NEXUS UNLOCKED*\n\n"
        f"⏱ Timeframe: *{tf_label}*\n"
        f"📢 Auto-Broadcast: *{bc_status}*\n\n"
        "📸 Send me any trading chart screenshot and I'll analyze it:\n"
        "• Candlestick pattern detection (55+ patterns)\n"
        "• Trend momentum scoring\n"
        "• Next candle prediction (UP/DOWN)\n"
        "• Confidence percentage\n\n"
        "_Just upload an image to get started!_"
    )

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

    # Password check
    if text == BOT_PASSWORD:
        unlock_user(user.id)
        await update.message.reply_text(
            "✅ *Access Granted!* Welcome to MI NEXUS.",
            parse_mode="Markdown"
        )
        await send_main_menu(update, context)
    else:
        await update.message.reply_text("❌ Incorrect password. Try again:")


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

    # ---- Route plan selection ----
    if data.startswith("plan_"):
        plan_id = data.replace("plan_", "")
        await handle_plan_selection(query, context, plan_id)
        return

    # ---- Route admin panel callbacks ----
    if data.startswith("admin_") or data.startswith("setqr_") or data.startswith("payapprove_") or data.startswith("payreject_"):
        await handle_admin_callback(query, context, data)
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

    elif data == "menu_stats":
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN direction='UP' THEN 1 ELSE 0 END) FROM signal_log WHERE user_id=?", (user_id,))
        total, ups = cur.fetchone()
        conn.close()
        total = total or 0
        ups = ups or 0
        downs = total - ups
        await query.edit_message_text(
            f"📊 *Your Signal Stats*\n\n"
            f"Total Analyses: *{total}*\n"
            f"⬆️ UP signals: *{ups}*\n"
            f"⬇️ DOWN signals: *{downs}*",
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
        await query.edit_message_text(
            "ℹ️ *How MI NEXUS Works*\n\n"
            "1️⃣ Send a screenshot of any trading chart\n"
            "2️⃣ Our engine detects candlesticks using computer vision\n"
            "3️⃣ Classic patterns are matched (Hammer, Engulfing, Doji, etc.)\n"
            "4️⃣ Momentum + pattern scoring generates a bias\n"
            "5️⃣ You get UP/DOWN prediction + confidence %\n\n"
            "⚠️ *Disclaimer:* This is a technical pattern analysis tool. "
            "No prediction system can guarantee market outcomes. "
            "Trade responsibly.",
            parse_mode="Markdown"
        )

    elif data == "menu_back":
        auto_bc, _ = get_auto_broadcast_settings(user_id)
        bc_status = "🟢 ON" if auto_bc else "🔴 OFF"
        keyboard = [
            [InlineKeyboardButton("⏱ Change Timeframe", callback_data="menu_timeframe")],
            [InlineKeyboardButton(f"📢 Auto-Broadcast: {bc_status}", callback_data="menu_broadcast_settings")],
            [InlineKeyboardButton("🎬 Post Session Start", callback_data="menu_session_start")],
            [InlineKeyboardButton("📊 My Stats", callback_data="menu_stats")],
            [InlineKeyboardButton("👥 Active Groups", callback_data="menu_groups")],
            [InlineKeyboardButton("ℹ️ How It Works", callback_data="menu_help")],
        ]
        await query.edit_message_text(
            "✅ *MI NEXUS Main Menu*", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

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
        signal_id = int(signal_id)
        set_signal_result(signal_id, result.upper())

        is_win = result.upper() == "WIN"
        result_sticker_path = get_result_sticker(
            is_win, output_path=f"/tmp/mi_nexus_result_sticker_{user_id}_{signal_id}.webp"
        )

        auto_bc, selected_group = get_auto_broadcast_settings(user_id)
        target_groups = []
        if selected_group:
            target_groups = [(selected_group, get_group_title(selected_group))]
        else:
            target_groups = list_groups()[:1]  # fallback: first known group

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

        wins, losses = get_win_loss_stats(user_id)
        await query.edit_message_text(
            f"{'✅' if is_win else '❌'} Result logged: *{result.upper()}*\n"
            f"Posted to {sent} group(s).\n\n"
            f"📊 Your Record: *{wins}W / {losses}L*",
            parse_mode="Markdown"
        )


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

    processing_msg = await update.message.reply_text(
        "⚡ *MI NEXUS is scanning the chart...*\n_Detecting candles, patterns & momentum_",
        parse_mode="Markdown"
    )

    try:
        photo_file = await update.message.photo[-1].get_file()
        local_path = f"/tmp/mi_nexus_input_{user.id}_{update.message.message_id}.jpg"
        await photo_file.download_to_drive(local_path)

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

        rsi_signal = detect_rsi_signal(local_path)
        prediction = predict_next_candle(candles, rsi_signal=rsi_signal)
        tf_code = get_timeframe(user.id)
        tf_label = TF_LABELS.get(tf_code, "1 Min")

        pair_name = detect_pair_name(local_path) or "Chart Analysis"

        output_path = f"/tmp/mi_nexus_result_{user.id}_{update.message.message_id}.png"
        render_result_card(
            chart_image_path=local_path,
            prediction=prediction,
            pair_name=pair_name,
            timeframe_label=tf_label,
            utc_offset_hours=5,
            logo_path=LOGO_PATH if os.path.exists(LOGO_PATH) else None,
            output_path=output_path,
        )

        log_id = log_signal(user.id, prediction["direction"], prediction["confidence"], tf_code)

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

        # ---- Auto-broadcast: if enabled, send straight to the selected group ----
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

        # ---- WIN / LOSS result buttons ----
        result_keyboard = [[
            InlineKeyboardButton("✅ WIN", callback_data=f"result_WIN_{log_id}"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"result_LOSS_{log_id}"),
        ]]
        await update.message.reply_text(
            "📋 *After your trade closes, tap the result:*",
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
        status_text = f"✅ Your active plan: *{plan_label}*\n\n"
    else:
        status_text = "You don't have an active plan yet.\n\n"

    keyboard = [
        [InlineKeyboardButton("💵 Basic — Rs 500/mo (15/day)", callback_data="plan_basic")],
        [InlineKeyboardButton("💰 Pro — Rs 1000/mo (35/day)", callback_data="plan_pro")],
        [InlineKeyboardButton("👑 Unlimited — Rs 5000/mo", callback_data="plan_unlimited")],
    ]
    await update.message.reply_text(
        f"💎 *MI NEXUS Subscription Plans* 💎\n\n"
        f"{status_text}"
        f"Choose a plan below to see payment details:",
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
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return  # silently ignore for non-admins

    pending = list_pending_payments()
    keyboard = [
        [InlineKeyboardButton(f"💰 Pending Payments ({len(pending)})", callback_data="admin_pending")],
        [InlineKeyboardButton("📷 Set Plan QR Codes", callback_data="admin_setqr")],
        [InlineKeyboardButton("👥 Connected Groups", callback_data="menu_groups")],
    ]
    await update.message.reply_text(
        "🛠️ *MI NEXUS Admin Panel*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("MI NEXUS Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
