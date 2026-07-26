"""
MI NEXUS TRADING BOT
Local candlestick pattern analysis + next-candle bias prediction.
No external AI / paid API used - pure OpenCV + geometric rule engine.

Run:
    export BOT_TOKEN="your_telegram_bot_token"
    python bot.py
"""

import os
import json
import logging
import sqlite3
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
from utils.sticker_generator import generate_direction_sticker

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "19620MINEXUS")
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
DB_PATH = os.path.join(os.path.dirname(__file__), "mi_nexus.db")

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


# ----------------------------------------------------------------------
# DATABASE (SQLite - lightweight local storage, no external DB needed)
# ----------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            unlocked INTEGER DEFAULT 0,
            timeframe TEXT DEFAULT '1m',
            username TEXT,
            joined_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            added_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS signal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            direction TEXT,
            confidence REAL,
            timeframe TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, unlocked, timeframe FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def create_user(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, unlocked, timeframe, username, joined_at) VALUES (?, 0, '1m', ?, ?)",
        (user_id, username, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def unlock_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET unlocked=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def set_user_timeframe(user_id, tf_code):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET timeframe=? WHERE user_id=?", (tf_code, user_id))
    conn.commit()
    conn.close()


def is_unlocked(user_id):
    row = get_user(user_id)
    return bool(row and row[1] == 1)


def get_timeframe(user_id):
    row = get_user(user_id)
    return row[2] if row else "1m"


def register_group(chat_id, title):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO groups (chat_id, title, added_at) VALUES (?, ?, ?)",
        (chat_id, title, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def list_groups():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT chat_id, title FROM groups")
    rows = cur.fetchall()
    conn.close()
    return rows


def log_signal(user_id, direction, confidence, timeframe):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO signal_log (user_id, direction, confidence, timeframe, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, direction, confidence, timeframe, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


TF_LABELS = {code: label for label, code in TIMEFRAME_OPTIONS}


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

    keyboard = [
        [InlineKeyboardButton("⏱ Change Timeframe", callback_data="menu_timeframe")],
        [InlineKeyboardButton("📊 My Stats", callback_data="menu_stats")],
        [InlineKeyboardButton("👥 Active Groups", callback_data="menu_groups")],
        [InlineKeyboardButton("ℹ️ How It Works", callback_data="menu_help")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    text = (
        "✅ *MI NEXUS UNLOCKED*\n\n"
        f"⏱ Current Timeframe: *{tf_label}*\n\n"
        "📸 Send me any trading chart screenshot and I'll analyze it:\n"
        "• Candlestick pattern detection\n"
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
        keyboard = [
            [InlineKeyboardButton("⏱ Change Timeframe", callback_data="menu_timeframe")],
            [InlineKeyboardButton("📊 My Stats", callback_data="menu_stats")],
            [InlineKeyboardButton("👥 Active Groups", callback_data="menu_groups")],
            [InlineKeyboardButton("ℹ️ How It Works", callback_data="menu_help")],
        ]
        await query.edit_message_text(
            "✅ *MI NEXUS Main Menu*", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
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

        # Generate the matching UP/DOWN sticker once for this broadcast
        sticker_path = None
        if signal_direction:
            sticker_path = generate_direction_sticker(
                signal_direction, signal_confidence,
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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type in ("group", "supergroup"):
        # Groups only RECEIVE broadcasted signals - the bot never analyzes
        # images posted directly inside a group chat.
        return

    if not is_unlocked(user.id):
        await update.message.reply_text("🔐 Please enter the access password first. Use /start")
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

        prediction = predict_next_candle(candles)
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

        log_signal(user.id, prediction["direction"], prediction["confidence"], tf_code)

        is_up = prediction["direction"] == "UP"
        dir_emoji = "🟢⬆️" if is_up else "🔴⬇️"
        strength = prediction.get("strength", "MODERATE")
        strength_emoji = {"VERY STRONG": "🔥🔥🔥", "STRONG": "🔥🔥", "MODERATE": "🔥", "WEAK": "⚡"}.get(strength, "⚡")

        top_pattern = "N/A"
        if prediction.get("breakdown"):
            top_pattern = sorted(prediction["breakdown"], key=lambda p: p["reliability"], reverse=True)[0]["name"]

        caption = (
            f"💎 *MI NEXUS PREMIUM SIGNAL* 💎\n\n"
            f"{dir_emoji} Direction: *{prediction['direction']}*\n"
            f"📊 Confidence: *{prediction['confidence']}%* {strength_emoji}\n"
            f"⏱ Timeframe: *{tf_label}*\n"
            f"🕯️ Key Pattern: *{top_pattern}*\n"
            f"💹 Pair: *{pair_name}*\n\n"
            f"✅ _Trade smart, manage your risk._"
        )

        with open(output_path, "rb") as img:
            await update.message.reply_photo(photo=img, caption=caption, parse_mode="Markdown")

        # Send matching UP/DOWN sticker
        sticker_path = generate_direction_sticker(
            prediction["direction"], prediction["confidence"],
            output_path=f"/tmp/mi_nexus_sticker_{user.id}_{update.message.message_id}.webp"
        )
        with open(sticker_path, "rb") as sticker:
            await update.message.reply_sticker(sticker=sticker)

        # Store this signal so it can be broadcast to groups on request
        context.user_data["last_signal_path"] = output_path
        context.user_data["last_signal_caption"] = caption
        context.user_data["last_signal_direction"] = prediction["direction"]
        context.user_data["last_signal_confidence"] = prediction["confidence"]

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

        await processing_msg.delete()

        if os.path.exists(local_path):
            os.remove(local_path)

    except Exception as e:
        logger.exception("Error processing photo")
        await processing_msg.edit_text(f"❌ Error analyzing image: {str(e)}")


async def error_handler(update, context):
    logger.error("Exception:", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set!")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("MI NEXUS Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
