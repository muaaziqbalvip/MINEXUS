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

## Features (v11 — Premium 3D Digital Chart Rendering)

- 🎨 **Redrawn 3D digital candle chart** — instead of pasting your raw
  screenshot, the bot now redraws the detected candles itself as a clean
  premium chart: vertical gradient bodies (brighter at top, darker at
  bottom for a "lit from above" 3D look), glowing wicks, soft drop-shadows,
  subtle grid lines, and a dashed ghost-candle marker showing the predicted
  next direction. Falls back to the original screenshot automatically if
  candle detection doesn't have enough data to redraw from.

- 🚀 **Password removed** — replaced with a one-tap "Create Account / Login"
  button. Your Telegram account is your identity; there's nothing to type
  or forget.
- 🔒 **Bug fixes**: `/menu` → 📊 My Stats and the ✅ WIN / ❌ LOSS buttons
  were broken (still calling the old removed SQLite code) — both now work
  correctly against Firestore.
- 👤 **Client vs Admin separation** (this was a real gap before — fixed now):
  - Regular clients only ever get **their own personal signal** — analyzing
    a chart, seeing their own confidence/pattern breakdown, and logging
    their own WIN/LOSS for their personal stats.
  - **Auto-Broadcast, Post Session Start, group-share buttons, and posting
    WIN/LOSS results to groups are admin-only** — a regular client will
    never see or trigger a group post, even by accident.
- 🕯️ **89 pattern variants** — expanded further with Three Stars in the
  South, Breakaway, Side-by-Side White Lines, Ascending/Descending Hawk,
  Tasuki Gap, Three-Line Strike, Inside/Outside Bar, and Pin Bar (a common
  price-action term for hammer/shooting-star-style rejection candles) —
  covering the full canonical candlestick library plus common price-action
  variants.
- 📖 **Full step-by-step trading guide built into the bot** (📖 How To Use
  in the menu) — walks through getting a signal, reading every field on
  the card, deciding whether to enter, placing the trade, logging the
  result, and basic risk-management tips.

- 🔥 **Firebase Firestore persistence** — all data (users, groups, signal
  history, payments, plans) now survives GitHub Actions restarts, since it's
  no longer stored in a local SQLite file that resets between runs
- 🔐 **Authentication is just Telegram** — no separate Google/email login;
  each user's Telegram `user_id` is their identity, which is standard for bots
- 💳 **3-tier paid subscription system**:
  | Plan | Price | Daily Chart Analyses |
  |------|-------|----------------------|
  | Basic | Rs 500/month | 15/day |
  | Pro | Rs 1000/month | 35/day |
  | Unlimited | Rs 5000/month | Unlimited |
- 📷 **Manual QR-code payment flow** — user picks a plan (`/plans`), sees
  the admin's QR code for that plan, pays via any cash/bank app, then sends
  a screenshot back to the bot. The screenshot is uploaded to imgBB and the
  admin gets an Approve/Reject button. Approving instantly activates the plan.
- 🛠️ **Admin panel** (`/admin`, restricted to your Telegram ID only):
  - View & approve/reject pending payments
  - Upload/update the QR code image for each plan
  - View connected groups
  - Admin's own usage is exempt from daily limits
- ⏳ **Daily usage tracking** — each plan enforces its daily analysis limit
  automatically; limits reset every day, tracked per user in Firestore

- 🔬 **Statistically-recalibrated pattern weights**: reliability scores for
  every pattern were reviewed against independently-published, large-sample
  technical-analysis research on real-world candlestick performance. Two
  concrete corrections came out of that review:
  - Some famous, easy-to-spot patterns (Hanging Man, Shooting Star, Matching
    Low) have been found in large historical backtests to perform close to
    a coin-flip despite their popularity — their weights were lowered so
    they nudge the score gently instead of being treated as strong signals.
  - Patterns with consistently strong historical directional performance
    (Morning/Evening Star, Abandoned Baby, engulfing patterns, Marubozu)
    keep higher weights, reflecting their more consistent real-world track record.
- 📉 **RSI confluence detection** — the bot now looks for an RSI-style
  oscillator panel in the screenshot (common on Quotex/broker charts) and
  reads its approximate zone (Overbought / Oversold / Neutral). If the RSI
  zone agrees with the pattern-based direction, confidence gets a modest
  boost; if they disagree, confidence is pulled back — mirroring the
  well-documented real-world finding that combining RSI with candlestick
  confirmation improves accuracy over candlesticks alone. This is a visual
  approximation of RSI from the chart image, not an exact recalculation
  from raw price data, so it's used as supporting context rather than a
  standalone signal.

- 🎨 **Redesigned result card** with a premium two-column insight section:
  - **Market Sentiment card** — animated-style bull/bear icon drawn to match
    the signal direction, plus a 6-dot confidence-intensity meter
  - **Volatility card** — a wave visual that gets choppier as market
    choppiness increases, plus a matching intensity dot meter (LOW/MEDIUM/HIGH)
  - **Tip box** — a short contextual tip that adapts to the situation
    (e.g. "Choppy market — consider waiting this one out" when volatility is high)

- 🧠 **Smarter signal-quality scoring** (new in v6):
  - **Confluence bonus** — when multiple detected patterns agree on
    direction, confidence gets boosted; when they conflict, it's dampened
    back toward neutral instead of overstating certainty
  - **Choppiness detection** — counts recent direction flips to detect
    sideways/indecisive markets and automatically lowers confidence there,
    since patterns are less reliable outside a clean trend
  - **Support/Resistance proximity nudge** — a soft contextual adjustment
    based on whether price is near a recent swing high or swing low
  - **Market Condition indicator** — every signal card now shows
    "Clean Trend / Mixed / Choppy" so you know how much to trust it
  - **More robust body/wick detection** — candles with no visible wick
    (true Marubozu) are now distinguished from ones where wick detection
    simply failed, reducing false Marubozu calls

- 🚀 One-tap account creation — no password, Telegram identity only
- 📸 Send any chart screenshot → instant analysis
- 🕯️ Detects **74+ pattern variants** — the full classic candlestick library
  (Nison/Bulkowski reference set) plus extra subtle/small formations:
  all Doji types, Hammer/Hanging Man, Shooting Star/Inverted Hammer, Marubozu,
  Belt Hold, Engulfing, Piercing/Dark Cloud, Tweezer, Harami (+ Cross),
  On-Neck/In-Neck/Thrusting, Kicker, Meeting Lines, Morning/Evening Star (+ Doji),
  Abandoned Baby, Three Soldiers/Crows, Three Inside/Outside Up/Down,
  Stick Sandwich, Tri-Star, Advance Block, Deliberation, Upside Gap Two Crows,
  Rising/Falling Three Methods, Mat Hold, Doji Star, Homing Pigeon,
  Matching Low/High, Separating Lines, Ladder Top/Bottom, Concealing Baby
  Swallow, Unique Three River Bottom, Two Crows, Downside Gap Three Methods,
  Long/Short Day classification, Rickshaw Man
- 💹 **Pair/Asset name auto-detection** via OCR, with a live-price fallback for
  Quotex-style screens that don't show a pair name on the chart itself
- 🎯 **Tuned candle detection** — filters out UI icons, trade markers, and
  price badges that were previously misread as candles (tested against real
  Quotex screenshots)
- ⬆️⬇️ Next-candle UP/DOWN prediction with confidence % + strength rating
- 📋 Per-pattern reliability breakdown shown on the result card
- 🎨 **Your own stickers, sent automatically** for UP / DOWN / Session Start /
  WIN / LOSS — just drop your files in `assets/stickers/`; the bot never
  generates stickers itself, it only sends what you provide
- 📢 **Auto-Broadcast toggle (ON/OFF)** — when ON, every signal you analyze is
  sent straight to your chosen group with zero manual taps; when OFF, you get
  a one-tap "Send to Group" button instead
- 🎬 **Manual Session-Start posts** — pick a group, type a pair name (e.g.
  "EUR/USD OTC"), and your session-start sticker + announcement goes out
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

### 🎨 Stickers — 100% Your Own, No Auto-Generation
This bot does **not** generate any stickers itself. You provide your own
sticker files, and the bot simply sends the right one at the right moment.
Drop your files into `assets/stickers/` with these **exact names**:

| Slot | Filename | Sent when... |
|------|----------|--------------|
| UP signal | `up.webp` | A chart analysis predicts UP |
| DOWN signal | `down.webp` | A chart analysis predicts DOWN |
| Session start | `session_start.webp` | You post a manual "Session Start" to a group |
| Win result | `win.webp` | You tap the ✅ WIN button after a trade |
| Loss result | `loss.webp` | You tap the ❌ LOSS button after a trade |

Accepted formats: `.webp` (ideal, no conversion needed), `.png`, `.jpg` (auto-
converted to WEBP on the fly). If a file is missing for a given slot, the bot
simply skips sending a sticker for that one moment — everything else (the
signal card, the caption, the broadcast) still goes out normally, so nothing
ever breaks or crashes because a sticker isn't there yet.

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
│   ├── indicator_reader.py     # Visual RSI panel detection for confluence
│   ├── sticker_generator.py    # Looks up YOUR sticker files (no auto-gen)
│   └── image_renderer.py       # 9:16 result card generator
├── assets/
│   ├── logo.png                # MI NEXUS logo
│   └── stickers/                # 👉 put YOUR custom sticker files here
│       ├── up.webp              #    (skipped if missing, no auto-gen)
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

### 2. Create a Firebase project (for persistent data)
1. Go to [console.firebase.google.com](https://console.firebase.google.com) → **Add project**
2. Once created, go to **Build → Firestore Database → Create database**
   (choose "production mode", pick any region)
3. Go to **Project Settings (⚙️) → Service Accounts → Generate new private key**
   — this downloads a JSON file. Keep it safe; you'll paste its full contents
   into a GitHub Secret in step 4.

### 3. Get an imgBB API key (for payment screenshots + QR codes)
1. Go to [api.imgbb.com](https://api.imgbb.com) → sign up / log in
2. Copy your API key from the dashboard

### 4. Push this project to GitHub
```bash
cd mi_nexus_bot
git init
git add .
git commit -m "MI NEXUS bot initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/mi-nexus-bot.git
git push -u origin main
```

### 5. Add GitHub Secrets
Go to: **Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `BOT_TOKEN` | Your Telegram bot token from BotFather |
| `FIREBASE_CREDENTIALS_JSON` | Paste the **entire contents** of the service account JSON file from step 2 |
| `ADMIN_USER_ID` | Your Telegram numeric user ID (get it from @userinfobot) |
| `IMGBB_API_KEY` | Your imgBB API key from step 3 |

### 6. Enable GitHub Actions
- Go to the **Actions** tab in your repo
- Click **"I understand my workflows, enable them"**
- Manually trigger **"MI NEXUS Bot 24/7"** once (Run workflow button) to start it

The **watchdog** workflow will now check every 15 minutes and auto-restart
the bot if it stops (crash, GitHub 6-hour job limit, etc.) for near-zero downtime.

### 7. Set up your payment QR codes
1. Message your bot with `/admin` (only works for your `ADMIN_USER_ID`)
2. Tap **📷 Set Plan QR Codes** → choose a plan → send the QR code image
3. Repeat for all 3 plans (Basic / Pro / Unlimited)

### 8. Test it
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
export FIREBASE_CREDENTIALS_JSON='{"type": "service_account", ...}'   # full JSON as one line
export ADMIN_USER_ID="8865257002"
export IMGBB_API_KEY="your_imgbb_key"
python bot.py
```

---

## Customization

- **Account access:** no password needed anymore — access is controlled by the Create Account / Login button + your subscription plan status
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
