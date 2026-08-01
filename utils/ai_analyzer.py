"""
MI NEXUS - Groq AI Vision Analysis (optional layer)

Uses Groq's hosted vision-language models to give a second, AI-based read
on a chart screenshot, on top of (not instead of) the local geometric
pattern engine. This is admin-toggleable - when OFF, the bot behaves
exactly as before (pure local analysis, zero API calls, zero cost).
When ON, this adds an AI opinion that's blended into the final signal.

Multiple Groq API keys are supported (comma-separated in the
GROQ_API_KEYS secret) so requests can rotate across keys if one hits a
rate limit - this spreads load and reduces the chance of a single key's
free-tier limits blocking the bot.

Model choice: Groq has deprecated the older llama-3.2-*-vision-preview
models. The current (as of this writing) recommended vision-capable
models on Groq are the Llama 4 family, which support up to 5 images per
request and a 128K context window:
  - meta-llama/llama-4-scout-17b-16e-instruct   (faster, cheaper)
  - meta-llama/llama-4-maverick-17b-128e-instruct (larger, more capable)
Always double-check console.groq.com/docs/vision for the current model
list before relying on this in production, since Groq's lineup changes.
"""

import os
import base64
import json
import random

try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False

DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

ANALYSIS_PROMPT = """You are an expert technical analyst reviewing a trading chart screenshot.

Analyze the candlestick chart shown and respond with ONLY a JSON object (no other text, no markdown fences) in this exact shape:
{
  "direction": "UP" or "DOWN",
  "confidence": <number 50-95>,
  "reasoning": "<one short sentence explaining the key visual cue>",
  "patterns_seen": ["<pattern name>", ...],
  "market_condition": "trending" or "ranging" or "choppy"
}

Base your read only on what's visually present in the chart: candle colors, shapes, wick lengths, overall trend direction, and any visible indicators (RSI, moving averages, etc). Do not invent data that isn't visible. Be honest that this is a probabilistic read, not a guarantee - keep confidence realistic (avoid claiming above 95)."""


def _get_api_keys():
    """
    Reads one or more Groq API keys from the GROQ_API_KEYS env var
    (comma-separated), falling back to the single GROQ_API_KEY var for
    convenience. Returns a list (possibly empty).
    """
    multi = os.environ.get("GROQ_API_KEYS", "")
    if multi:
        return [k.strip() for k in multi.split(",") if k.strip()]
    single = os.environ.get("GROQ_API_KEY", "")
    return [single] if single else []


def is_ai_available():
    """Whether AI analysis can even be attempted (SDK installed + at least one key configured)."""
    return GROQ_SDK_AVAILABLE and len(_get_api_keys()) > 0


def _encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_chart_with_ai(image_path, model=None):
    """
    Sends the chart image to Groq's vision model for an AI-based read.
    Returns a dict matching the ANALYSIS_PROMPT JSON shape, or None if
    AI analysis isn't available/configured, or a dict with "error" set
    if the call failed (network, rate limit, bad response, etc) - callers
    should treat both None and an "error" key as "AI unavailable, fall
    back to local-only analysis" rather than crashing.
    """
    if not is_ai_available():
        return None

    keys = _get_api_keys()
    model = model or DEFAULT_MODEL

    try:
        image_b64 = _encode_image(image_path)
    except Exception as e:
        return {"error": f"could not read image: {e}"}

    # Try each configured key in a random order - if one is rate-limited
    # or invalid, we fall through to the next rather than failing outright.
    keys_to_try = keys[:]
    random.shuffle(keys_to_try)

    last_error = None
    for key in keys_to_try:
        try:
            client = Groq(api_key=key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ANALYSIS_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                            },
                        ],
                    }
                ],
                temperature=0.3,
                max_tokens=400,
            )
            raw_text = response.choices[0].message.content.strip()

            # Strip markdown code fences if the model added them despite instructions
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                if raw_text.lower().startswith("json"):
                    raw_text = raw_text[4:].strip()

            parsed = json.loads(raw_text)

            direction = str(parsed.get("direction", "")).upper()
            if direction not in ("UP", "DOWN"):
                last_error = f"model returned invalid direction: {direction}"
                continue

            confidence = parsed.get("confidence", 60)
            try:
                confidence = max(50, min(95, float(confidence)))
            except (TypeError, ValueError):
                confidence = 60.0

            return {
                "direction": direction,
                "confidence": confidence,
                "reasoning": parsed.get("reasoning", ""),
                "patterns_seen": parsed.get("patterns_seen", []),
                "market_condition": parsed.get("market_condition", "unknown"),
                "model_used": model,
            }

        except json.JSONDecodeError as e:
            last_error = f"could not parse AI response as JSON: {e}"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    return {"error": last_error or "all Groq API keys failed"}


def blend_ai_with_local(local_prediction, ai_result, ai_weight=0.35):
    """
    Combines the local pattern-engine prediction with the AI read into a
    single blended confidence. If the AI result has an error or is None,
    returns the local prediction unchanged (never breaks the pipeline).
    ai_weight controls how much the AI opinion can move the final
    confidence - kept moderate so a single AI call can't wildly override
    the geometric analysis.
    """
    if not ai_result or "error" in ai_result:
        return local_prediction

    blended = dict(local_prediction)
    local_direction = local_prediction["direction"]
    local_confidence = local_prediction["confidence"]
    ai_direction = ai_result["direction"]
    ai_confidence = ai_result["confidence"]

    if ai_direction == local_direction:
        # AI agrees - modest confidence boost
        new_confidence = local_confidence + (ai_confidence - local_confidence) * ai_weight * 0.5
        new_confidence = min(96, new_confidence)
        blended["direction"] = local_direction
        blended["confidence"] = round(new_confidence, 1)
        blended["ai_agrees"] = True
    else:
        # AI disagrees - pull confidence down rather than flipping direction
        # outright, since the local engine's geometric read is the more
        # deterministic/auditable signal; AI acts as a caution flag here.
        new_confidence = local_confidence - (local_confidence - 50) * ai_weight * 0.6
        new_confidence = max(50, new_confidence)
        blended["confidence"] = round(new_confidence, 1)
        blended["ai_agrees"] = False

    blended["ai_result"] = ai_result
    return blended
