"""اتصال موحّد بـ Claude وChatGPT وGemini عن طريق HTTP عادي (من غير أي مكتبة إضافية).

الدالة الوحيدة اللي بتهمك: complete(cfg, system, user, json_mode)."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# الأسماء دي ممكن تتغير مع الوقت: المستخدم يقدر يعدّل اسم الموديل من الواجهة.
PROVIDERS = {
    "groq": {
        "label": "Groq (مجاني، الأسهل)",
        "model": "openai/gpt-oss-120b",
        "env": ["GROQ_API_KEY"],
        "key_url": "https://console.groq.com/keys",
        "key_hint": "gsk_...",
        "free": "طبقة مجانية بإيميل بس، من غير كارت",
        "base": "https://api.groq.com/openai/v1",
    },
    "gemini": {
        "label": "Google Gemini",
        "model": "gemini-3.8-flash",
        "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "key_url": "https://aistudio.google.com/app/apikey",
        "key_hint": "AIza...",
        "free": "فيه طبقة مجانية (محدودة السرعة)",
    },
    "openrouter": {
        "label": "OpenRouter (موديلات مجانية)",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "env": ["OPENROUTER_API_KEY"],
        "key_url": "https://openrouter.ai/keys",
        "key_hint": "sk-or-...",
        "free": "موديلات :free بحد يومي صغير، من غير كارت",
        "base": "https://openrouter.ai/api/v1",
    },
    "mistral": {
        "label": "Mistral",
        "model": "mistral-small-latest",
        "env": ["MISTRAL_API_KEY"],
        "key_url": "https://console.mistral.ai/api-keys",
        "key_hint": "الصق المفتاح",
        "free": "خطة مجانية بحدود",
        "base": "https://api.mistral.ai/v1",
    },
    "openai": {
        "label": "OpenAI (ChatGPT)",
        "model": "gpt-5.4-nano",
        "env": ["OPENAI_API_KEY"],
        "key_url": "https://platform.openai.com/api-keys",
        "key_hint": "sk-...",
        "free": "مدفوع بالاستخدام (أقل رصيد حوالي 5 دولار)",
        "base": "https://api.openai.com/v1",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "model": "claude-haiku-5-5",
        "env": ["ANTHROPIC_API_KEY"],
        "key_url": "https://console.anthropic.com/settings/keys",
        "key_hint": "sk-ant-...",
        "free": "مدفوع بالاستخدام",
    },
}


def guess_provider(key: str) -> str | None:
    """بيخمّن المزوّد من شكل المفتاح، عشان لو حطيت مفتاح Groq في خانة Gemini نصلّحها لوحدنا."""
    k = key.strip()
    for prefix, prov in (("gsk_", "groq"), ("sk-or-", "openrouter"), ("sk-ant-", "anthropic"),
                         ("AIza", "gemini"), ("sk-", "openai")):
        if k.startswith(prefix):
            return prov
    return None


@dataclass
class LLMConfig:
    provider: str
    api_key: str
    model: str = ""

    @property
    def model_name(self) -> str:
        return self.model.strip() or PROVIDERS[self.provider]["model"]


class LLMError(Exception):
    """رسالة خطأ مفهومة بالعربي تتعرض للمستخدم. suggested = اسم موديل بديل اقترحه المزوّد (لو موجود)."""

    suggested: str = ""


def _post(url: str, headers: dict, body: dict, timeout: int = 60, deadline: int = 100) -> dict:
    """طلب POST بوقت أقصى محدد (deadline ثانية إجمالًا) ومحاولات إعادة قليلة، عشان الواجهة ما تفضلش معلّقة."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    start, attempt = time.monotonic(), 0

    def left() -> float:
        return deadline - (time.monotonic() - start)

    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=max(5, min(timeout, left()))) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
                detail = detail.get("error", detail)
                detail = detail.get("message", detail) if isinstance(detail, dict) else detail
            except Exception:
                detail = raw[:200]
            low = str(detail).lower().replace(" ", "")
            if e.code == 429 and ("limit:0" in low or "perday" in low):
                retries = 0  # الكوتة اليومية خلصت أو مش متاحة: الانتظار مالوش فايدة
            elif e.code == 429:
                retries = 2
            elif e.code in (500, 502, 503, 529):
                retries = 2
            else:
                retries = 0
            wait = (5, 10)[min(attempt - 1, 1)] if e.code == 429 else (3, 6)[min(attempt - 1, 1)]
            if attempt <= retries and left() > wait + 15:
                time.sleep(wait)
                continue
            err = LLMError(_explain(e.code, str(detail)))
            m = re.search(r"(?:use|try|switch to)\s+(?:models/)?([\w.\-]+)", str(detail), re.I)
            if m and ("no longer available" in str(detail) or e.code == 404):
                err.suggested = m.group(1)
                err.args = (err.args[0] + f" ← جرّب الموديل: {err.suggested}",)
            raise err from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt <= 1 and left() > 25:
                time.sleep(2)
                continue
            waited = int(time.monotonic() - start)
            raise LLMError(f"الخدمة مش بترد (استنيت {waited} ثانية) أو مفيش اتصال بالإنترنت. "
                           f"جرّب تاني بعد شوية، أو غيّر المزوّد/الموديل. ({type(e).__name__})") from None


def _explain(code: int, detail: str) -> str:
    detail = detail[:300]
    if code in (401, 403):
        return f"المفتاح (API key) غلط أو مش مفعّل أو معندوش صلاحية. ({detail})"
    if code == 404:
        return f"اسم الموديل غلط أو مش متاح لحسابك، جرّب اسم تاني. ({detail})"
    if code == 429:
        return (f"وصلت للحد الأقصى (كوتة أو سرعة الطلبات)، أو الرصيد خلص، أو الموديل ده مش متاح في الطبقة المجانية "
                f"لحسابك. غيّر الموديل من خانة «اسم الموديل»، أو استخدم مزوّد تاني (Groq مثلًا). ({detail})")
    if code == 400:
        return f"الخدمة رفضت الطلب. ({detail})"
    return f"خطأ من الخدمة ({code}): {detail}"


def complete(cfg: LLMConfig, system: str, user: str, json_mode: bool = False, max_tokens: int = 4000) -> str:
    key, model = cfg.api_key.strip(), cfg.model_name
    if not key:
        raise LLMError("مفيش مفتاح API.")
    if cfg.provider == "anthropic":
        r = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]},
        )
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text").strip()
    if cfg.provider in PROVIDERS and PROVIDERS[cfg.provider].get("base"):
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode and cfg.provider == "openai":  # باقي المزوّدين مش كلهم بيدعموا الوضع ده، والبرومبت كفاية
            body["response_format"] = {"type": "json_object"}
        r = _post(f"{PROVIDERS[cfg.provider]['base']}/chat/completions", {"Authorization": f"Bearer {key}"}, body)
        return (r["choices"][0]["message"].get("content") or "").strip()
    if cfg.provider == "gemini":
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        def call(mdl: str) -> dict:
            return _post(f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent",
                         {"x-goog-api-key": key}, body)
        try:
            r = call(model)
        except LLMError as e:
            if e.suggested and not cfg.model.strip() and e.suggested != model:
                r = call(e.suggested)  # الموديل الافتراضي اتشال: نجرّب اللي اقترحته جوجل
            else:
                raise
        cands = r.get("candidates") or []
        if not cands:
            raise LLMError(f"Gemini ما رجّعش إجابة (ممكن اتحجبت). {r.get('promptFeedback', '')}")
        return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
    raise LLMError(f"مزوّد غير معروف: {cfg.provider}")


def test_connection(cfg: LLMConfig) -> tuple[bool, str]:
    """طلب صغير جدًا بيقولك المفتاح والموديل شغالين ولا لأ، وبرسالة واضحة لو لأ."""
    try:
        r = complete(cfg, "Reply with the single word OK.", "ping", max_tokens=30)
    except LLMError as e:
        return False, str(e)
    except Exception as e:  # شكل رد غير متوقع
        return False, f"رد غير متوقع من الخدمة: {type(e).__name__}"
    return True, f"✅ شغّال! ({PROVIDERS[cfg.provider]['label']} · {cfg.model_name}) الرد: {r[:40] or '—'}"
