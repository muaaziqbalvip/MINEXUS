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
            "timeframe": "1m",
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
    Checks whether the user can run another analysis today under their
    plan's daily limit, and increments their usage counter if allowed.
    Returns (allowed: bool, remaining: int|None, plan_id: str|None).
    remaining is None for unlimited plans.
    """
    db = init_firebase()
    plan_id = get_active_plan(user_id)

    if not plan_id:
        return False, 0, None  # no active plan

    limit = PLAN_LIMITS.get(plan_id, {}).get("daily_limit")
    if limit is None:
        return True, None, plan_id  # unlimited plan

    user = get_user(user_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage_date = user.get("daily_usage_date")
    usage_count = user.get("daily_usage_count", 0) if usage_date == today else 0

    if usage_count >= limit:
        return False, 0, plan_id

    new_count = usage_count + 1
    db.collection("users").document(str(user_id)).update({
        "daily_usage_date": today,
        "daily_usage_count": new_count,
    })
    return True, limit - new_count, plan_id


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
