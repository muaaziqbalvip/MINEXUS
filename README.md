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

## Features

- 🔐 Password-gated access (`BOT_PASSWORD` secret, default `19620MINEXUS`)
- 📸 Send any chart screenshot → instant analysis
- 🕯️ Detects: Doji, Hammer, Shooting Star, Marubozu, Spinning Top,
  Bullish/Bearish Engulfing, Piercing Line, Dark Cloud Cover, Tweezer Top/Bottom,
  Morning Star, Evening Star, Three White Soldiers, Three Black Crows
- ⬆️⬇️ Next-candle UP/DOWN prediction with confidence %
- ⏱️ Per-user timeframe setting (5 sec → 1 hour)
- 🖼️ Beautiful 9:16 branded result card (MI NEXUS logo + glassmorphism style)
- 👥 Works in groups — auto-registers group, lists active groups
- 📊 Per-user signal history/stats
- 🚀 Runs 24/7 via GitHub Actions (auto-restart workflow + watchdog)

---

## Project Structure

```
mi_nexus_bot/
├── bot.py                      # Main Telegram bot
├── requirements.txt
├── utils/
│   ├── candle_detector.py      # OpenCV candle detection
│   ├── pattern_engine.py       # Pattern rules + prediction scoring
│   └── image_renderer.py       # 9:16 result card generator
├── assets/
│   └── logo.png                # MI NEXUS logo
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
