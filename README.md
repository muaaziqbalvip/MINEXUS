# MI NEXUS — Trading Chart Signal Bot

Fully local candlestick pattern analyzer + next-candle bias predictor.
**No AI API, no external paid service** — pure OpenCV + geometric rule engine.

---

## ⚠️ Important Honesty Note

This bot detects candlestick shapes/colors from a screenshot and applies
classic technical-analysis pattern rules (Hammer, Engulfing, Doji, Morning/Evening
Star, etc.) plus a momentum score to produce a directional bias (UP/DOWN) with
a confidence percentage.

**No system — AI or rule-based — can guarantee real market outcomes.**
This is a technical-pattern visualization tool, not a guaranteed signal source.
Treat it as an educational aid, not financial advice.

---

## Features (v4 — 55+ Patterns, VIP Stickers, Auto-Broadcast, Win/Loss Tracking)

- 🔐 Password-gated access (`BOT_PASSWORD` secret, default `19620MINEXUS`)
- 📸 Send any chart screenshot → instant analysis
- 🕯️ Detects **55+ pattern variants** across the full classic candlestick
  library (Nison/Bulkowski reference set) — 1, 2, 3, and 5-candle formations:
  all Doji types, Hammer/Hanging Man, Shooting Star/Inverted Hammer, Marubozu,
  Belt Hold, Engulfing, Piercing/Dark Cloud, Tweezer, Harami (+ Cross),
  On-Neck/In-Neck/Thrusting, Kicker, Meeting Lines, Morning/Evening Star (+ Doji),
  Abandoned Baby, Three Soldiers/Crows, Three Inside/Outside Up/Down,
  Stick Sandwich, Tri-Star, Advance Block, Deliberation, Upside Gap Two Crows,
  Rising/Falling Three Methods, Mat Hold
- 💹 **Pair/Asset name auto-detection** via OCR, with a live-price fallback for
  Quotex-style screens that don't show a pair name on the chart itself
- 🎯 **Tuned candle detection** — filters out UI icons, trade markers, and
  price badges that were previously misread as candles (tested against real
  Quotex screenshots)
- ⬆️⬇️ Next-candle UP/DOWN prediction with confidence % + strength rating
- 📋 Per-pattern reliability breakdown shown on the result card
- 🎨 **VIP-style stickers** for UP / DOWN / Session Start / WIN / LOSS —
  **use YOUR OWN sticker files** (drop them in `assets/stickers/`) or let the
  bot auto-generate a gold-ring VIP fallback design automatically
- 📢 **Auto-Broadcast toggle (ON/OFF)** — when ON, every signal you analyze is
  sent straight to your chosen group with zero manual taps; when OFF, you get
  a one-tap "Send to Group" button instead
- 🎬 **Manual Session-Start posts** — pick a group, type a pair name (e.g.
  "EUR/USD OTC"), and a VIP session-start sticker + announcement goes out
  telling everyone to open that pair
- ✅❌ **WIN / LOSS result tracking** — after every signal, tap WIN or LOSS;
  the bot posts a matching result sticker + message to your group and keeps
  a running win/loss record for you
- ⏱️ Per-user timeframe setting (5 sec → 1 hour)
- 🖼️ Premium 9:16 branded result card (MI NEXUS logo, glow effects, pair badge,
  strength badge, confidence bar, pattern list)
- 💎 Emoji-rich premium Telegram captions
- 👥 Groups **only receive broadcasted signals** — the bot never analyzes
  images posted directly in a group (private-chat analysis only)
- 📊 Per-user signal history/stats + win/loss record
- 🚀 Runs 24/7 via GitHub Actions (auto-restart workflow + watchdog)

### 🎨 Using Your Own Stickers
Drop your own `.webp` (preferred), `.png`, or `.jpg` files into `assets/stickers/`
with these exact names — the bot will use them automatically instead of the
auto-generated fallback:

| Slot | Filename |
|------|----------|
| UP signal | `up.webp` |
| DOWN signal | `down.webp` |
| Session start | `session_start.webp` |
| Win result | `win.webp` |
| Loss result | `loss.webp` |

If a file is missing, the bot just auto-generates that one sticker — nothing breaks.

### 🎛️ A note on button colors
Telegram's native inline buttons (the kind this bot uses) can't have custom
background colors — Telegram's app decides that styling, not the bot. Colored
buttons are only possible via a Telegram Web App (a full embedded HTML page),
which is a much bigger, separately-hosted feature. This bot uses 🟢/🔴 emoji
indicators on buttons instead, which is the standard, zero-maintenance way to
show status at a glance.

### ⚠️ Known OCR limitation (honest note)
Quotex's actual trading screen usually shows **only a live price**, not the
pair name (e.g. "EUR/USD"), directly on the chart — the pair is chosen on a
separate screen. So on real Quotex screenshots, pair-name OCR will often come
back empty; the card falls back to "Chart Analysis" in that case. This is a
platform-UI limitation, not a bug in the OCR itself.

---

## Project Structure

```
mi_nexus_bot/
├── bot.py                      # Main Telegram bot
├── requirements.txt
├── utils/
│   ├── candle_detector.py      # OpenCV candle detection
│   ├── pattern_engine.py       # 55+ pattern rules + prediction scoring
│   ├── pair_detector.py        # OCR-based pair/asset name detection
│   ├── sticker_generator.py    # Custom-sticker lookup + VIP fallback generator
│   └── image_renderer.py       # 9:16 result card generator
├── assets/
│   ├── logo.png                # MI NEXUS logo
│   └── stickers/                # 👉 put YOUR custom sticker files here
│       ├── up.webp              #    (optional — auto-generated if missing)
│       ├── down.webp
│       ├── session_start.webp
│       ├── win.webp
│       └── loss.webp
└── .github/workflows/
    ├── mi_nexus_bot.yml        # Runs the bot (restarts every ~6h)
    └── watchdog.yml            # Checks every 15 min, restarts if bot stopped
```

---

## Setup — Step by Step

### 1. Create your Telegram Bot
1. Open Telegram, search **@BotFather**
2. Send `/newbot`, follow prompts
3. Copy the token it gives you (looks like `123456:ABC-DEF...`)

### 2. Push this project to GitHub
```bash
cd mi_nexus_bot
git init
git add .
git commit -m "MI NEXUS bot initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/mi-nexus-bot.git
git push -u origin main
```

### 3. Add GitHub Secrets
Go to: **Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name    | Value                              |
|-----------------|-------------------------------------|
| `BOT_TOKEN`     | Your Telegram bot token from BotFather |
| `BOT_PASSWORD`  | `19620MINEXUS` (or change it)       |

### 4. Enable GitHub Actions
- Go to the **Actions** tab in your repo
- Click **"I understand my workflows, enable them"**
- Manually trigger **"MI NEXUS Bot 24/7"** once (Run workflow button) to start it

The **watchdog** workflow will now check every 15 minutes and auto-restart
the bot if it stops (crash, GitHub 6-hour job limit, etc.) for near-zero downtime.

### 5. Test it
- Open Telegram, find your bot, send `/start`
- Enter password: `19620MINEXUS`
- Send a chart screenshot
- Get your MI NEXUS signal card back

---

## Local Testing (before deploying)

```bash
# System dependency for pair/asset OCR detection
sudo apt-get install -y tesseract-ocr   # Linux
# brew install tesseract                # macOS

pip install -r requirements.txt
export BOT_TOKEN="your_token_here"
export BOT_PASSWORD="19620MINEXUS"
python bot.py
```

---

## Customization

- **Change password:** update `BOT_PASSWORD` secret in GitHub
- **Adjust timeframes:** edit `TIMEFRAME_OPTIONS` in `bot.py`
- **Tune pattern sensitivity:** edit thresholds in `utils/pattern_engine.py`
- **Change UTC offset:** edit `utc_offset_hours` param passed to `render_result_card()` in `bot.py` (currently set to +5 for Pakistan)
- **Rebrand colors/logo:** edit `utils/image_renderer.py` palette constants,
  replace `assets/logo.png`

---

## Known Limitations

- Candle detection relies on color-based segmentation — works best with
  standard green/red (or teal/crimson) candle themes. Heavily custom or
  low-contrast themes may need color-range tuning in `candle_detector.py`.
- GitHub Actions free tier caps a single job at 6 hours; the workflow
  auto-restarts every ~6h and the watchdog catches any gaps within 15 min.
- This is pattern-recognition + statistics, not a guaranteed prediction engine.
