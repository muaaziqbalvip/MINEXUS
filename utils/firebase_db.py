"""
MI NEXUS - Firebase Database Layer
Replaces the old SQLite storage with Firestore so data survives GitHub
Actions restarts. Authentication is just the Telegram user_id — no
separate login is needed since Telegram already identifies the user.

Setup:
1. Create a Firebase project (or reuse an existing one).
2. Firestore Database -> Create database (production mode).
3. Project Settings -> Service Accounts -> Generate new private key.
   This downloads a JSON file - its contents go into the
   FIREBASE_CREDENTIALS_JSON GitHub Secret (paste the whole JSON as text).

Collections used:
  users            { user_id, username, unlocked, timeframe, auto_broadcast,
                     selected_group, joined_at, plan, plan_expires_at,
                     daily_usage_date, daily_usage_count, blocked, frozen,
                     block_reason, total_signals, trial_used }
  groups           { chat_id, title, added_at }
  signal_log       { user_id, direction, confidence, timeframe, result,
                      created_at }
  bot_config       { signal_sensitivity, min_confidence_floor,
                      max_confidence_ceiling } — single "global" doc, tuned
                      live from the admin panel's Signal Sensitivity Tuner.
  payments         { payment_id, user_id, username, plan, screenshot_url,
                      status ("pending"/"approved"/"rejected"), created_at,
                      reviewed_at }
  plan_qr_codes    { plan_id -> { image_url, updated_at } }
"""

import os
import json
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def init_firebase():
    """Initializes the Firebase app once. Safe to call multiple times."""
    global _db
    if _db is not None:
        return _db

    if not firebase_admin._apps:
        cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if not cred_json:
            raise RuntimeError(
                "FIREBASE_CREDENTIALS_JSON environment variable is not set! "
                "Paste your Firebase service account JSON into this secret."
            )
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    return _db


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------
# USERS
# ----------------------------------------------------------------------
def get_user(user_id):
    db = init_firebase()
    doc = db.collection("users").document(str(user_id)).get()
    return doc.to_dict() if doc.exists else None


def create_user(user_id, username):
    db = init_firebase()
    ref = db.collection("users").document(str(user_id))
    if not ref.get().exists:
        ref.set({
            "user_id": user_id,
            "username": username,
            "unlocked": False,
            "country": None,
            "timeframe": "1m",
            "trade_duration": "1m",
            "auto_broadcast": False,
            "selected_group": None,
            "joined_at": _now_iso(),
            "plan": None,               # None | "trial" | "basic" | "pro" | "unlimited"
            "plan_expires_at": None,
            "daily_usage_date": None,
            "daily_usage_count": 0,
            "blocked": False,
            "frozen": False,
            "block_reason": None,
            "total_signals": 0,
            "trial_used": False,
        })
    else:
        # Existing user re-triggering /start - keep username fresh for admin search
        ref.update({"username": username})


def set_user_country(user_id, country_code):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"country": country_code})


def get_user_country(user_id):
    user = get_user(user_id)
    return user.get("country") if user else None


def set_has_existing_quotex_account(user_id, has_existing):
    """Records whether the user says they already had a Quotex account
    before joining the bot (vs signing up fresh through our link) - useful
    context for the admin since it affects whether the deposit-tier path
    via our tracking link will even work for them."""
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({
        "has_existing_quotex_account": has_existing
    })


def set_user_email(user_id, email):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"email": email})


def get_user_email(user_id):
    user = get_user(user_id)
    return user.get("email") if user else None


def set_user_profile_photo(user_id, photo_url):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"profile_photo_url": photo_url})


def get_user_profile(user_id):
    """Returns the full profile bundle for display on the Profile screen."""
    user = get_user(user_id) or {}
    return {
        "username": user.get("username"),
        "country": user.get("country"),
        "email": user.get("email"),
        "has_existing_quotex_account": user.get("has_existing_quotex_account"),
        "profile_photo_url": user.get("profile_photo_url"),
        "joined_at": user.get("joined_at"),
        "plan": user.get("plan"),
    }


def unlock_user(user_id):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"unlocked": True})


def is_unlocked(user_id):
    user = get_user(user_id)
    return bool(user and user.get("unlocked"))


def set_user_timeframe(user_id, tf_code):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"timeframe": tf_code})


def get_timeframe(user_id):
    user = get_user(user_id)
    return user.get("timeframe", "1m") if user else "1m"


def set_trade_duration(user_id, duration_code):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"trade_duration": duration_code})


def get_trade_duration(user_id):
    user = get_user(user_id)
    return user.get("trade_duration", "1m") if user else "1m"


def set_auto_broadcast(user_id, enabled, group_id=None):
    db = init_firebase()
    data = {"auto_broadcast": enabled}
    if group_id is not None:
        data["selected_group"] = group_id
    db.collection("users").document(str(user_id)).update(data)


def get_auto_broadcast_settings(user_id):
    user = get_user(user_id)
    if not user:
        return False, None
    return bool(user.get("auto_broadcast")), user.get("selected_group")


# ----------------------------------------------------------------------
# MEMBER MODERATION — Block / Freeze
# ----------------------------------------------------------------------
# "Blocked"  -> user is fully cut off. Every handler (photo/text/menu)
#               refuses them with a fixed message. Reversible via unblock.
# "Frozen"   -> user's ACCOUNT is frozen: their active plan is suspended
#               (they lose analysis access, same as no-plan) but their
#               account/profile/stats are preserved and they're not
#               blocked from opening the menu — used for "freeze the
#               account" without a full ban. Reversible via unfreeze.
def block_user(user_id, reason=None):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({
        "blocked": True,
        "block_reason": reason or "No reason given",
        "blocked_at": _now_iso(),
    })


def unblock_user(user_id):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({
        "blocked": False,
        "block_reason": None,
    })


def is_blocked(user_id):
    user = get_user(user_id)
    return bool(user and user.get("blocked"))


def freeze_user(user_id):
    """Freezes the account: plan access is suspended immediately."""
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({
        "frozen": True,
        "frozen_at": _now_iso(),
    })


def unfreeze_user(user_id):
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"frozen": False})


def is_frozen(user_id):
    user = get_user(user_id)
    return bool(user and user.get("frozen"))


def list_all_users(limit=200):
    """Returns recent users for the admin member-management panel."""
    db = init_firebase()
    docs = db.collection("users").order_by(
        "joined_at", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()
    return [d.to_dict() for d in docs]


def find_user_by_username(username):
    """Case-sensitive exact match search (Telegram usernames are unique)."""
    db = init_firebase()
    clean = username.lstrip("@")
    docs = db.collection("users").where("username", "==", clean).limit(5).stream()
    return [d.to_dict() for d in docs]


def increment_total_signals(user_id):
    db = init_firebase()
    ref = db.collection("users").document(str(user_id))
    doc = ref.get()
    current = doc.to_dict().get("total_signals", 0) if doc.exists else 0
    ref.update({"total_signals": current + 1})


# ----------------------------------------------------------------------
# GROUPS
# ----------------------------------------------------------------------
def register_group(chat_id, title):
    db = init_firebase()
    db.collection("groups").document(str(chat_id)).set({
        "chat_id": chat_id,
        "title": title,
        "added_at": _now_iso(),
    })


def list_groups():
    db = init_firebase()
    docs = db.collection("groups").stream()
    return [(int(d.id), d.to_dict().get("title", "Unnamed Group")) for d in docs]


def get_group_title(chat_id):
    db = init_firebase()
    doc = db.collection("groups").document(str(chat_id)).get()
    return doc.to_dict().get("title", "Unknown Group") if doc.exists else "Unknown Group"


# ----------------------------------------------------------------------
# SIGNAL LOG (history + win/loss)
# ----------------------------------------------------------------------
def log_signal(user_id, direction, confidence, timeframe):
    db = init_firebase()
    ref = db.collection("signal_log").document()
    ref.set({
        "user_id": user_id,
        "direction": direction,
        "confidence": confidence,
        "timeframe": timeframe,
        "result": None,
        "created_at": _now_iso(),
    })
    return ref.id


def set_signal_result(signal_id, result):
    db = init_firebase()
    db.collection("signal_log").document(signal_id).update({"result": result})


def get_win_loss_stats(user_id):
    db = init_firebase()
    wins = len(list(db.collection("signal_log")
                     .where("user_id", "==", user_id)
                     .where("result", "==", "WIN").stream()))
    losses = len(list(db.collection("signal_log")
                       .where("user_id", "==", user_id)
                       .where("result", "==", "LOSS").stream()))
    return wins, losses


# ----------------------------------------------------------------------
# SUBSCRIPTION PLANS + DAILY USAGE LIMITS
# ----------------------------------------------------------------------
PLAN_LIMITS = {
    "trial": {"label": "🎁 Free Trial (1 Day)", "daily_limit": 10},
    "basic": {"label": "Basic (Rs 500/mo)", "daily_limit": 15},
    "pro": {"label": "Pro (Rs 1000/mo)", "daily_limit": 35},
    "unlimited": {"label": "Unlimited (Rs 5000/mo)", "daily_limit": None},
}


def get_active_plan(user_id):
    """Returns the plan_id if active and not expired, else None."""
    user = get_user(user_id)
    if not user or not user.get("plan"):
        return None
    expires_at = user.get("plan_expires_at")
    if expires_at:
        try:
            expiry_dt = datetime.fromisoformat(expires_at)
            if datetime.now(timezone.utc) > expiry_dt:
                return None  # expired
        except Exception:
            pass
    return user.get("plan")


def activate_plan(user_id, plan_id, days=30):
    from datetime import timedelta
    db = init_firebase()
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    db.collection("users").document(str(user_id)).update({
        "plan": plan_id,
        "plan_expires_at": expires.isoformat(),
        "daily_usage_date": None,
        "daily_usage_count": 0,
    })


def has_used_trial(user_id):
    user = get_user(user_id)
    return bool(user and user.get("trial_used"))


def start_free_trial(user_id):
    """
    Activates the one-time free trial: 1 day validity, 10 total signal
    analyses (enforced via the normal daily-limit mechanism, since the
    whole trial only spans a single day anyway). Marks trial_used so the
    same account can never re-claim it after it ends/is used up.
    Returns False if the account already used its trial before.
    """
    if has_used_trial(user_id):
        return False
    activate_plan(user_id, "trial", days=1)
    db = init_firebase()
    db.collection("users").document(str(user_id)).update({"trial_used": True})
    return True


def check_and_increment_usage(user_id):
    """
    Checks whether the user can run another analysis today, and increments
    their usage counter if allowed. Two independent unlock paths are
    supported and the HIGHER limit of the two wins when both are present:
      1. A manually-approved paid plan (Basic/Pro/Unlimited via QR payment)
      2. A Quotex deposit tier (see utils/quotex_tiers.py) - unlocked
         automatically via the Quotex affiliate postback once a referred
         user's verified deposit total crosses a threshold.
    Returns (allowed: bool, remaining: int|None, plan_id: str|None).
    remaining is None for unlimited plans.
    """
    db = init_firebase()
    plan_id = get_active_plan(user_id)
    plan_limit = PLAN_LIMITS.get(plan_id, {}).get("daily_limit") if plan_id else None
    plan_is_unlimited = plan_id and plan_limit is None

    user = get_user(user_id) or {}
    quotex_limit = user.get("quotex_daily_limit")

    if plan_is_unlimited:
        return True, None, plan_id

    # Determine the effective limit: unlimited beats any number, otherwise
    # take whichever numeric limit (paid plan vs Quotex tier) is higher.
    candidates = [v for v in (plan_limit, quotex_limit) if v is not None]
    if not candidates:
        return False, 0, plan_id  # no active plan and no qualifying deposit

    effective_limit = max(candidates)
    effective_source = plan_id if (plan_limit == effective_limit and plan_limit is not None) else "quotex_tier"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage_date = user.get("daily_usage_date")
    usage_count = user.get("daily_usage_count", 0) if usage_date == today else 0

    if usage_count >= effective_limit:
        return False, 0, effective_source

    new_count = usage_count + 1
    db.collection("users").document(str(user_id)).update({
        "daily_usage_date": today,
        "daily_usage_count": new_count,
    })
    return True, effective_limit - new_count, effective_source


def get_quotex_tracking_link(user_id, base_link="https://broker-qx.pro/sign-up/fast/"):
    """
    Builds a per-user Quotex tracking link with the Telegram user_id
    embedded as the `lid` (Link ID) parameter - confirmed against the
    real Quotex Affiliate Center Postback screen, where `lid` maps to
    the {lid} macro that comes back in postback events, letting the
    postback endpoint match a deposit back to this specific Telegram user.
    """
    return f"{base_link}?lid={user_id}"


def get_quotex_deposit_status(user_id):
    """Returns (total_deposit, daily_limit) for display in the bot."""
    user = get_user(user_id) or {}
    return user.get("quotex_total_deposit", 0), user.get("quotex_daily_limit")


# ----------------------------------------------------------------------
# PAYMENTS
# ----------------------------------------------------------------------
def create_payment_request(user_id, username, plan_id, screenshot_url):
    db = init_firebase()
    ref = db.collection("payments").document()
    ref.set({
        "payment_id": ref.id,
        "user_id": user_id,
        "username": username,
        "plan": plan_id,
        "screenshot_url": screenshot_url,
        "status": "pending",
        "created_at": _now_iso(),
        "reviewed_at": None,
    })
    return ref.id


def get_payment(payment_id):
    db = init_firebase()
    doc = db.collection("payments").document(payment_id).get()
    return doc.to_dict() if doc.exists else None


def update_payment_status(payment_id, status):
    db = init_firebase()
    db.collection("payments").document(payment_id).update({
        "status": status,
        "reviewed_at": _now_iso(),
    })


def list_pending_payments():
    db = init_firebase()
    docs = db.collection("payments").where("status", "==", "pending").stream()
    return [d.to_dict() for d in docs]


# ----------------------------------------------------------------------
# PLAN QR CODES (admin-managed, per-plan payment QR images)
# ----------------------------------------------------------------------
def set_plan_qr_code(plan_id, image_url):
    db = init_firebase()
    db.collection("plan_qr_codes").document(plan_id).set({
        "image_url": image_url,
        "updated_at": _now_iso(),
    })


def get_plan_qr_code(plan_id):
    db = init_firebase()
    doc = db.collection("plan_qr_codes").document(plan_id).get()
    return doc.to_dict().get("image_url") if doc.exists else None


# ----------------------------------------------------------------------
# BOT CONFIG (admin-tunable global settings, e.g. signal sensitivity)
# ----------------------------------------------------------------------
_DEFAULT_CONFIG = {
    "signal_sensitivity": 1.0,   # 0.7 (conservative) .. 1.3 (aggressive)
    "min_confidence_floor": 54,  # lowest displayed confidence %
    "max_confidence_ceiling": 96,
    # Admin-editable Quotex deposit tiers: list of [threshold_usd, daily_limit]
    # sorted descending by threshold. Edited via the admin panel.
    "quotex_tiers": [[100, 300], [50, 120], [20, 40], [10, 18]],
    # Required channels/groups a user must join before they can use the
    # bot. List of dicts: {"name": display name, "chat_id": numeric ID or
    # @username, "url": invite link}. Empty list = no requirement.
    "required_channels": [],
    # Admin-toggleable: whether AI (Groq vision) analysis runs alongside
    # the local pattern engine. OFF by default - zero API cost/calls
    # unless the admin explicitly turns it on.
    "ai_analysis_enabled": False,
}


def get_bot_config():
    db = init_firebase()
    doc = db.collection("bot_config").document("global").get()
    cfg = dict(_DEFAULT_CONFIG)
    if doc.exists:
        cfg.update(doc.to_dict())
    return cfg


def set_bot_config_value(key, value):
    db = init_firebase()
    db.collection("bot_config").document("global").set({key: value}, merge=True)


def adjust_signal_sensitivity(delta):
    """Nudges sensitivity by delta, clamped to a safe [0.7, 1.3] range."""
    cfg = get_bot_config()
    new_val = round(max(0.7, min(1.3, cfg.get("signal_sensitivity", 1.0) + delta)), 2)
    set_bot_config_value("signal_sensitivity", new_val)
    return new_val


def get_quotex_tiers():
    """Returns the current admin-configured tier list: [[threshold, limit], ...]"""
    cfg = get_bot_config()
    return cfg.get("quotex_tiers", _DEFAULT_CONFIG["quotex_tiers"])


def set_quotex_tier(threshold, daily_limit):
    """
    Adds or updates a single tier (e.g. threshold=20, daily_limit=40).
    Keeps the tier list sorted descending by threshold.
    """
    tiers = get_quotex_tiers()
    tiers = [t for t in tiers if t[0] != threshold]  # replace if it already exists
    tiers.append([threshold, daily_limit])
    tiers.sort(key=lambda t: t[0], reverse=True)
    set_bot_config_value("quotex_tiers", tiers)
    return tiers


def remove_quotex_tier(threshold):
    tiers = get_quotex_tiers()
    tiers = [t for t in tiers if t[0] != threshold]
    set_bot_config_value("quotex_tiers", tiers)
    return tiers


def tier_for_amount(amount):
    """Given a deposit amount, returns (threshold, daily_limit) for the
    highest tier the amount qualifies for, or (None, None) if below all tiers."""
    for threshold, limit in get_quotex_tiers():
        if amount >= threshold:
            return threshold, limit
    return None, None


def get_quotex_full_profile(user_id):
    """
    Returns the complete Quotex-related profile for a user, for the
    admin's strict oversight view: registration status, total deposited,
    total withdrawn, net position, current tier, trader ID, country.
    """
    user = get_user(user_id) or {}
    total_deposit = user.get("quotex_total_deposit", 0)
    total_withdrawn = user.get("quotex_total_withdrawn", 0)
    threshold, limit = tier_for_amount(total_deposit) if total_deposit else (None, None)
    return {
        "registered": user.get("quotex_registered", False),
        "registered_at": user.get("quotex_registered_at"),
        "email_confirmed": user.get("quotex_email_confirmed", False),
        "trader_id": user.get("quotex_trader_id"),
        "country": user.get("quotex_country"),
        "total_deposit": total_deposit,
        "total_withdrawn": total_withdrawn,
        "net_position": total_deposit - total_withdrawn,
        "tier_threshold": threshold,
        "daily_limit": limit,
        "last_deposit_at": user.get("quotex_last_deposit_at"),
    }


def list_users_with_quotex_activity():
    """Returns all users who have any Quotex deposit/registration activity,
    for the admin's oversight list."""
    db = init_firebase()
    docs = db.collection("users").where("quotex_registered", "==", True).stream()
    results = []
    for d in docs:
        data = d.to_dict()
        results.append({
            "user_id": data.get("user_id"),
            "username": data.get("username"),
            "total_deposit": data.get("quotex_total_deposit", 0),
            "total_withdrawn": data.get("quotex_total_withdrawn", 0),
            "daily_limit": data.get("quotex_daily_limit"),
        })
    results.sort(key=lambda u: u["total_deposit"], reverse=True)
    return results


# ----------------------------------------------------------------------
# REQUIRED CHANNELS (mandatory join-before-access, admin-configurable)
# ----------------------------------------------------------------------
def get_required_channels():
    cfg = get_bot_config()
    return cfg.get("required_channels", [])


def add_required_channel(name, chat_id, url):
    channels = get_required_channels()
    channels = [c for c in channels if c["chat_id"] != chat_id]  # replace if exists
    channels.append({"name": name, "chat_id": chat_id, "url": url})
    set_bot_config_value("required_channels", channels)
    return channels


def remove_required_channel(chat_id):
    channels = get_required_channels()
    channels = [c for c in channels if c["chat_id"] != chat_id]
    set_bot_config_value("required_channels", channels)
    return channels


# ----------------------------------------------------------------------
# AI ANALYSIS TOGGLE (admin-controlled)
# ----------------------------------------------------------------------
def is_ai_analysis_enabled():
    cfg = get_bot_config()
    return cfg.get("ai_analysis_enabled", False)


def set_ai_analysis_enabled(enabled):
    set_bot_config_value("ai_analysis_enabled", bool(enabled))
    return enabled
