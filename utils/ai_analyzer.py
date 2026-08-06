"""
MI NEXUS PRO - Groq AI Vision Analysis (Premium Layer)

Full professional-grade chart analysis using Groq's vision models.
This is the core AI brain of the bot — completely rewritten from scratch
with a pro trading analyst prompt that instructs the model to perform
a real, step-by-step technical analysis before reaching a conclusion.

Key upgrades over v1:
  - Expert-level system prompt: structured 5-step analysis workflow
  - Chain-of-thought reasoning: model must analyze trend, pattern,
    momentum, S/R, and confluence BEFORE deciding direction
  - Higher blend weight (0.50): AI opinion carries real weight now
  - Smart conflict resolution: when AI and local engine disagree,
    detailed reasoning is preserved and shown to user
  - Fallback model chain: scout -> maverick -> llama3-70b-vision
  - Retry logic with exponential backoff on rate-limit errors
  - Entry timing signal from AI (enter now / wait / skip)
  - Risk level assessment from AI (low / medium / high)
  - Market regime detection (trending / ranging / volatile)
"""

import os
import base64
import json
import random
import time
import logging

logger = logging.getLogger("MI_NEXUS.ai")

try:
    from groq import Groq, RateLimitError
    GROQ_SDK_AVAILABLE = True
except ImportError:
    try:
        from groq import Groq
        RateLimitError = Exception  # fallback if not exported separately
        GROQ_SDK_AVAILABLE = True
    except ImportError:
        GROQ_SDK_AVAILABLE = False
        RateLimitError = Exception

# Model priority chain: only qwen/qwen3.6-27b currently supports vision on
# Groq (verified — the old llama-4-scout/llama-4-maverick vision models were
# deprecated by Groq and no longer work; the recommended text-only successor,
# openai/gpt-oss-120b, does NOT accept image input at all). Every chart
# analysis was silently failing before this fix and falling back to the
# local-only prediction, which is why AI Deep Scan wasn't actually improving
# anything. qwen3.6-27b is Groq's current — and only — vision-capable model.
MODEL_CHAIN = [
    "qwen/qwen3.6-27b",
]

# ─────────────────────────────────────────────────────────────────────────────
# PRO-LEVEL SYSTEM PROMPT
# This is where the magic happens. The model is given a structured workflow
# to follow, forcing it to reason step-by-step before concluding a direction.
# Generic prompts give garbage — structured expert prompts give real analysis.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert professional trading analyst specializing in binary options and forex markets.
You have 15+ years of experience reading candlestick charts and identifying high-probability trading setups.

Your analysis style is disciplined, evidence-based, and risk-aware. You never chase trades and you always
justify your conclusions with specific visual evidence from the chart."""

ANALYSIS_PROMPT = """Analyze this trading chart screenshot using the following structured 5-step framework.
Respond ONLY with a valid JSON object (no markdown fences, no extra text).

STEP 1 — TREND STRUCTURE:
Identify the overall trend by looking at the sequence of highs and lows:
- Higher Highs + Higher Lows = Uptrend (bullish)
- Lower Highs + Lower Lows = Downtrend (bearish)
- No clear sequence = Sideways/Ranging

STEP 2 — CANDLESTICK PATTERNS:
Identify the most recent 1-3 candle formation(s). Look for:
- Reversal patterns: Hammer, Shooting Star, Doji, Engulfing, Morning/Evening Star, Pin Bar
- Continuation patterns: Marubozu, Three White Soldiers/Black Crows, Inside Bar breakout
- Indecision: Spinning Top, Long-legged Doji, Doji at key levels

STEP 3 — MOMENTUM & VOLUME APPROXIMATION:
- Are recent candles getting LARGER (expanding momentum) or SMALLER (momentum fading)?
- Are bullish candles bigger than bearish ones recently (bull momentum) or vice versa?
- Check if the last few candles show a clear directional push or mixed signals

STEP 4 — SUPPORT / RESISTANCE:
- Is price near a recent swing high (resistance zone — likely reversal down) or swing low (support — likely bounce up)?
- Has price bounced off a level multiple times? (stronger S/R)
- Is this a breakout above resistance (bullish) or below support (bearish)?

STEP 5 — CONFLUENCE DECISION:
Count how many of the above factors agree on a direction.
- 3-4 agreeing factors = HIGH confidence signal
- 2 agreeing factors = MODERATE confidence signal  
- 1 factor or mixed = LOW confidence, consider SKIP

Based on this analysis, predict the NEXT candle's direction.

Respond with ONLY this JSON (no markdown, no extra words):
{
  "direction": "UP" or "DOWN",
  "confidence": <integer 50-96>,
  "strength": "VERY STRONG" or "STRONG" or "MODERATE" or "WEAK",
  "entry_timing": "ENTER NOW" or "WAIT FOR CONFIRMATION" or "SKIP - LOW QUALITY",
  "risk_level": "LOW RISK" or "MEDIUM RISK" or "HIGH RISK",
  "market_regime": "TRENDING" or "RANGING" or "VOLATILE",
  "reasoning": "<2-3 sentences explaining your analysis using the 5-step framework above>",
  "trend_structure": "uptrend" or "downtrend" or "sideways",
  "key_patterns": ["<pattern1>", "<pattern2>"],
  "confluence_score": <integer 1-5>,
  "agreeing_factors": ["<factor1>", "<factor2>"]
}

Rules:
- confidence MUST match strength: VERY STRONG=82-96, STRONG=70-81, MODERATE=60-69, WEAK=50-59
- If the chart is too blurry/zoomed-out, set confidence=50 and entry_timing="SKIP - LOW QUALITY"
- Be honest — do NOT claim high confidence if the signal is ambiguous
- reasoning must cite SPECIFIC visual evidence (e.g. "bullish engulfing at support after downtrend")"""


def _get_api_keys():
    """
    Reads Groq API keys from environment. Supports comma-separated
    multi-key config in GROQ_API_KEYS or single key in GROQ_API_KEY.
    Returns a list (possibly empty).
    """
    multi = os.environ.get("GROQ_API_KEYS", "")
    if multi:
        return [k.strip() for k in multi.split(",") if k.strip()]
    single = os.environ.get("GROQ_API_KEY", "")
    return [single] if single else []


def is_ai_available():
    """Whether AI analysis can be attempted (SDK installed + key configured)."""
    return GROQ_SDK_AVAILABLE and len(_get_api_keys()) > 0


def _encode_image(image_path):
    """Base64-encode the chart image for the vision API."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _call_groq(client, model, image_b64, max_retries=2):
    """
    Single Groq API call with retry on rate-limit errors.
    Returns raw response text or raises on persistent failure.
    """
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ANALYSIS_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                },
                            },
                        ],
                    },
                ],
                temperature=0.2,      # Lower = more deterministic/consistent analysis
                max_tokens=600,       # Enough for full JSON with reasoning
            )
            return response.choices[0].message.content.strip()

        except RateLimitError:
            if attempt < max_retries:
                wait = (attempt + 1) * 3  # 3s, 6s backoff
                logger.warning(f"Groq rate limit on {model}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
        except Exception:
            raise

    raise RuntimeError("Max retries exceeded")


def _parse_ai_response(raw_text):
    """
    Cleans and parses the AI response JSON.
    Handles markdown fences, leading/trailing garbage, etc.
    Returns parsed dict or raises ValueError.
    """
    # Strip markdown code fences (model sometimes adds despite instructions)
    text = raw_text
    if "```" in text:
        # Extract content between first ``` and last ```
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.lower().startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in response: {raw_text[:200]}")

    text = text[start:end]
    parsed = json.loads(text)

    # Validate required fields
    direction = str(parsed.get("direction", "")).upper()
    if direction not in ("UP", "DOWN"):
        raise ValueError(f"Invalid direction: {direction}")

    return parsed


def analyze_chart_with_ai(image_path, model=None):
    """
    Sends chart image to Groq vision model for professional technical analysis.

    Returns a rich dict with direction, confidence, reasoning, entry timing,
    risk level, market regime, and more — or None/error dict on failure.
    Callers should treat None and dicts with "error" key as
    "AI unavailable, use local analysis only" — never crashes the pipeline.
    """
    if not is_ai_available():
        return None

    keys = _get_api_keys()
    models_to_try = MODEL_CHAIN if model is None else [model]

    try:
        image_b64 = _encode_image(image_path)
    except Exception as e:
        logger.warning(f"Could not encode chart image: {e}")
        return {"error": f"could not read image: {e}"}

    # Shuffle keys for load distribution across multiple keys
    keys_shuffled = keys[:]
    random.shuffle(keys_shuffled)

    last_error = None

    for key in keys_shuffled:
        for model_name in models_to_try:
            try:
                client = Groq(api_key=key)
                raw_text = _call_groq(client, model_name, image_b64)
                parsed = _parse_ai_response(raw_text)

                direction = str(parsed.get("direction", "")).upper()

                # Clamp confidence to valid range
                confidence = parsed.get("confidence", 65)
                try:
                    confidence = max(50, min(96, float(confidence)))
                except (TypeError, ValueError):
                    confidence = 65.0

                # Validate/default optional fields
                strength = parsed.get("strength", "MODERATE")
                if strength not in ("VERY STRONG", "STRONG", "MODERATE", "WEAK"):
                    # Derive from confidence if model gave garbage
                    if confidence >= 82:
                        strength = "VERY STRONG"
                    elif confidence >= 70:
                        strength = "STRONG"
                    elif confidence >= 60:
                        strength = "MODERATE"
                    else:
                        strength = "WEAK"

                entry_timing = parsed.get("entry_timing", "WAIT FOR CONFIRMATION")
                risk_level = parsed.get("risk_level", "MEDIUM RISK")
                market_regime = parsed.get("market_regime", "RANGING")
                reasoning = parsed.get("reasoning", "")
                trend_structure = parsed.get("trend_structure", "sideways")
                key_patterns = parsed.get("key_patterns", [])
                confluence_score = parsed.get("confluence_score", 2)
                agreeing_factors = parsed.get("agreeing_factors", [])

                result = {
                    "direction": direction,
                    "confidence": confidence,
                    "strength": strength,
                    "entry_timing": entry_timing,
                    "risk_level": risk_level,
                    "market_regime": market_regime,
                    "reasoning": reasoning,
                    "trend_structure": trend_structure,
                    "patterns_seen": key_patterns,
                    "confluence_score": confluence_score,
                    "agreeing_factors": agreeing_factors,
                    "model_used": model_name,
                }

                logger.info(
                    f"AI analysis: {direction} @ {confidence:.0f}% "
                    f"({strength}) | model={model_name}"
                )
                return result

            except json.JSONDecodeError as e:
                last_error = f"JSON parse error on {model_name}: {e}"
                logger.warning(last_error)
                continue
            except ValueError as e:
                last_error = f"Validation error on {model_name}: {e}"
                logger.warning(last_error)
                continue
            except Exception as e:
                last_error = f"{model_name}: {e}"
                logger.warning(f"AI call failed ({model_name}): {e}")
                continue

    logger.error(f"All AI attempts failed. Last error: {last_error}")
    return {"error": last_error or "all Groq models/keys failed"}


def blend_ai_with_local(local_prediction, ai_result, ai_weight=0.50):
    """
    Professionally blends the local geometric pattern engine prediction
    with the AI vision analysis.

    Key improvements over v1:
    - Higher weight (0.50 vs 0.35): AI carries real influence now
    - When AI agrees: significant confidence boost (up to +12%)
    - When AI disagrees: nuanced analysis — if AI has higher confluence,
      it can actually FLIP the direction if it's much more confident
    - Entry timing and risk level propagated to final result
    - Full AI reasoning preserved for display in signal card

    If ai_result is None or has an error, returns local prediction unchanged.
    """
    if not ai_result or "error" in ai_result:
        return local_prediction

    blended = dict(local_prediction)
    local_dir = local_prediction["direction"]
    local_conf = local_prediction["confidence"]
    ai_dir = ai_result["direction"]
    ai_conf = ai_result.get("confidence", 65)
    ai_confluence = ai_result.get("confluence_score", 2)

    if ai_dir == local_dir:
        # ─── AGREEMENT: Both engines agree → confidence boost ───────────
        # Boost is proportional to how confident the AI is.
        # Max boost: ~12% when AI is very confident (confidence ~90+)
        boost_factor = (ai_conf - 50) / 46.0  # 0.0 at conf=50, 1.0 at conf=96
        confidence_boost = boost_factor * ai_weight * 20.0  # up to +10%
        new_confidence = min(96, local_conf + confidence_boost)

        blended["confidence"] = round(new_confidence, 1)
        blended["direction"] = local_dir
        blended["ai_agrees"] = True

        # Update strength label if confidence crossed a threshold
        conf = blended["confidence"]
        if conf >= 82:
            blended["strength"] = "VERY STRONG"
        elif conf >= 70:
            blended["strength"] = "STRONG"
        elif conf >= 60:
            blended["strength"] = "MODERATE"
        else:
            blended["strength"] = "WEAK"

    else:
        # ─── DISAGREEMENT: Engines conflict ─────────────────────────────
        # If AI has very high confluence (4-5) AND much higher confidence,
        # and local engine is only moderate — defer to AI (flip direction).
        # Otherwise, pull confidence down but keep local direction.
        local_conf_normalized = (local_conf - 54) / 42.0  # 0=min, 1=max
        ai_conf_normalized = (ai_conf - 50) / 46.0

        if ai_confluence >= 4 and ai_conf_normalized > local_conf_normalized + 0.25:
            # AI is significantly more confident with more confluence — flip
            blended["direction"] = ai_dir
            blended["confidence"] = round(
                50 + ai_conf_normalized * 28, 1
            )  # moderate confidence after flip
            blended["ai_agrees"] = True  # now it agrees after flip
            blended["ai_direction_override"] = True
            logger.info(
                f"AI overrode local direction: {local_dir} → {ai_dir} "
                f"(AI confluence={ai_confluence}, AI conf={ai_conf:.0f}%)"
            )
        else:
            # Standard conflict handling: pull confidence toward 50 (neutral)
            pull_factor = ai_weight * 0.55
            new_confidence = local_conf - (local_conf - 54) * pull_factor
            new_confidence = max(54, new_confidence)
            blended["confidence"] = round(new_confidence, 1)
            blended["ai_agrees"] = False

        # Recalculate strength
        conf = blended["confidence"]
        if conf >= 82:
            blended["strength"] = "VERY STRONG"
        elif conf >= 70:
            blended["strength"] = "STRONG"
        elif conf >= 60:
            blended["strength"] = "MODERATE"
        else:
            blended["strength"] = "WEAK"

    # ─── Propagate AI extra data to prediction dict ──────────────────────
    blended["ai_result"] = ai_result
    blended["ai_entry_timing"] = ai_result.get("entry_timing", "WAIT FOR CONFIRMATION")
    blended["ai_risk_level"] = ai_result.get("risk_level", "MEDIUM RISK")
    blended["ai_market_regime"] = ai_result.get("market_regime", "RANGING")
    blended["ai_reasoning"] = ai_result.get("reasoning", "")
    blended["ai_trend_structure"] = ai_result.get("trend_structure", "sideways")
    blended["ai_confluence_score"] = ai_result.get("confluence_score", 2)
    blended["ai_agreeing_factors"] = ai_result.get("agreeing_factors", [])

    return blended
