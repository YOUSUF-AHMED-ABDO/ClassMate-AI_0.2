"""اختبار الاتصال بالمزوّدين بردود وهمية (من غير نت): python test_llm.py"""
import io, json, os, sys, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import llm

ok = True
def check(name, cond, extra=""):
    global ok
    ok &= bool(cond); print("✅" if cond else "❌", name, str(extra)[:100])

class R:
    def __init__(s, p): s.p = json.dumps(p).encode()
    def read(s): return s.p
    def __enter__(s): return s
    def __exit__(s, *a): pass

cap = []
def serve(payload):
    def f(req, timeout=0):
        cap.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
        return R(payload)
    urllib.request.urlopen = f

CHAT = {"choices": [{"message": {"content": "OK"}}]}
# كل المزوّدين المتوافقين مع OpenAI: الرابط الصح، بدون response_format (ماعدا OpenAI نفسه)
for prov, base in (("groq", "https://api.groq.com/openai/v1"), ("openrouter", "https://openrouter.ai/api/v1"),
                   ("mistral", "https://api.mistral.ai/v1"), ("openai", "https://api.openai.com/v1")):
    serve(CHAT); out = llm.complete(llm.LLMConfig(prov, "k123", ""), "S", "U", json_mode=True)
    url, hdr, body = cap[-1]
    check(f"{prov}: الرابط", url == base + "/chat/completions", url)
    check(f"{prov}: التوثيق والموديل", hdr.get("Authorization") == "Bearer k123" and body["model"] == llm.PROVIDERS[prov]["model"])
    check(f"{prov}: JSON mode", ("response_format" in body) == (prov == "openai"))
    check(f"{prov}: الرد", out == "OK")

# اختبار الاتصال
serve(CHAT); good, msg = llm.test_connection(llm.LLMConfig("groq", "k", ""))
check("test_connection ناجح", good and "شغّال" in msg, msg)
def err(code, text):
    def f(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(json.dumps({"error": {"message": text}}).encode()))
    urllib.request.urlopen = f
err(401, "Invalid API Key"); good, msg = llm.test_connection(llm.LLMConfig("groq", "bad", ""))
check("test_connection مفتاح غلط", not good and "المفتاح" in msg, msg)
err(404, "model not found"); good, msg = llm.test_connection(llm.LLMConfig("groq", "k", "nope"))
check("test_connection موديل غلط", not good and "الموديل" in msg, msg)
err(429, "rate limit"); llm.time.sleep = lambda s: None
good, msg = llm.test_connection(llm.LLMConfig("groq", "k", ""))
check("test_connection حد الاستخدام", not good and "الأقصى" in msg, msg)
urllib.request.urlopen = lambda *a, **k: R({"weird": 1})
good, msg = llm.test_connection(llm.LLMConfig("groq", "k", ""))
check("test_connection رد غريب مايكسرش", not good and "غير متوقع" in msg, msg)
# التخمين من شكل المفتاح
check("تخمين المفتاح", [llm.guess_provider(k) for k in ("gsk_1", "sk-or-1", "sk-ant-1", "AIza1", "sk-1", "x")]
      == ["groq", "openrouter", "anthropic", "gemini", "openai", None])

# ───── الانتظار والمحاولات: الواجهة ما تفضلش معلّقة ─────
import socket
class Clock:
    def __init__(self): self.t = 0.0
    def monotonic(self): return self.t
    def sleep(self, s): self.t += s
clock = Clock(); llm.time.monotonic, llm.time.sleep = clock.monotonic, clock.sleep
cfg = llm.LLMConfig("gemini", "k", "m")

def http_err(code, msg):
    def f(req, timeout=0):
        calls.append(timeout); clock.t += 1
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(json.dumps({"error": {"message": msg}}).encode()))
    return f

calls = []; clock.t = 0
urllib.request.urlopen = http_err(429, "Quota exceeded for metric ... limit: 0, model: gemini-3.8-flash")
try: llm.complete(cfg, "s", "u")
except llm.LLMError as e: err_msg = str(e)
check("429 limit:0 → محاولة واحدة وفشل سريع", len(calls) == 1 and clock.t < 3 and "Groq" in err_msg, (len(calls), clock.t))

calls = []; clock.t = 0
urllib.request.urlopen = http_err(429, "Too many requests, slow down")
try: llm.complete(cfg, "s", "u")
except llm.LLMError: pass
check("429 عادي → 3 محاولات بالكتير وأقل من 30 ثانية", len(calls) == 3 and clock.t < 30, (len(calls), clock.t))

calls = []; clock.t = 0
def hang(req, timeout=0):
    calls.append(timeout); clock.t += timeout          # الطلب بيستنى لحد الـ timeout
    raise socket.timeout("timed out")
urllib.request.urlopen = hang
try: llm.complete(cfg, "s", "u")
except llm.LLMError as e: tmsg = str(e)
check("خدمة معلّقة → بتفشل في أقل من 130 ثانية برسالة واضحة", clock.t <= 130 and "مش بترد" in tmsg, (len(calls), clock.t))
check("كل طلب له timeout أقصاه 60", all(c <= 60 for c in calls), calls)

calls = []; clock.t = 0
urllib.request.urlopen = http_err(503, "overloaded")
try: llm.complete(cfg, "s", "u")
except llm.LLMError: pass
check("503 → محاولتين إعادة بالكتير", len(calls) == 3 and clock.t < 30, (len(calls), clock.t))

print("\nALL OK" if ok else "\nFAILED"); raise SystemExit(0 if ok else 1)
