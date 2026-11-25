"""اختبار الحفظ والدمج واستخراج الذكاء الاصطناعي (بدون نت، باستخدام ردود وهمية)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from core import analyze, parse_chat
from store import Workspace, is_backup, list_spaces, load_space, save_space
import ai
from llm import LLMConfig, LLMError

ok = True
def check(name, cond, extra=""):
    global ok
    print(("✅" if cond else "❌"), name, extra)
    ok &= bool(cond)

CHAT1 = """15/11/2026, 10:00 - أحمد: الكويز يوم الخميس الساعة 10 ص
15/11/2026, 10:05 - سارة: تمام
15/11/2026, 10:05 - سارة: تمام
"""
CHAT2 = CHAT1 + """16/11/2026, 09:00 - د. منى: تم تأجيل الكويز ليوم الأحد
"""
ws = Workspace("test")
a, e = ws.merge(parse_chat(CHAT1), "c1.txt")
check("أول رفع", (a, e) == (3, 0), (a, e))                       # رسالتين متطابقتين = رسالتين
a, e = ws.merge(parse_chat(CHAT2), "c2.txt")
check("رفع أحدث: الجديد بس", (a, e) == (1, 3), (a, e))
a, e = ws.merge(parse_chat(CHAT2), "c2.txt")
check("رفع نفس الملف تاني", (a, e) == (0, 4), (a, e))
msgs = ws.sorted_messages()
check("الترتيب بالوقت", [m.when for m in msgs] == sorted(m.when for m in msgs))

# حفظ وتحميل
with tempfile.TemporaryDirectory() as d:
    save_space(d, ws)
    check("قائمة المحادثات", list_spaces(d) == ["test"])
    ws2 = load_space(d, "test")
    check("تحميل بعد الحفظ", len(ws2) == 4 and ws2.sorted_messages()[0].key == msgs[0].key)
raw = ws.to_json()
check("is_backup", is_backup(raw) and not is_backup(CHAT1))
other = Workspace.from_json(raw); w3 = Workspace("x"); w3.absorb(other)
check("دمج نسخة احتياطية", len(w3) == 4)

# الذكاء الاصطناعي: رد وهمي
calls = []
def fake(cfg, system, user, json_mode=False, **kw):
    calls.append(user)
    ids = [int(l.split()[0][1:]) for l in user.splitlines() if "(context)" not in l.split()[1:2] and not l.startswith("#") is False]
    # أحمد: id 0 كويز، منى: تأجيل
    out = {"events": []}
    for line in user.splitlines():
        if "(context)" in line: continue
        i = int(line.split()[0][1:])
        if "الكويز يوم الخميس" in line:
            out["events"].append({"id": i, "kind": "exam", "title": "كويز", "date": "2026-11-19", "time": "10:00", "status": "new", "replaces": [], "confidence": 0.9})
        if "تأجيل" in line:
            out["events"].append({"id": i, "kind": "exam", "title": "تأجيل الكويز", "date": "2026-11-22", "time": None, "status": "changed", "replaces": [0], "confidence": 0.9})
    return json.dumps(out, ensure_ascii=False)

cfg = LLMConfig("openai", "k")
todo = ai.pending_indices(msgs, ws.ai)
res, errs = ai.extract_events(cfg, msgs, todo, complete_fn=fake)
ws.ai.update(res)
check("كل الرسائل اتسجلت", len(ws.ai) == 4 and not errs, errs)
check("رسالة عادية = None", ws.ai[msgs[1].key] is None)
an = analyze(msgs, ai=ws.ai)
active = [(e.day.isoformat(), e.status, e.source) for e in an.events]
check("AI: القديم اتغيّر والجديد active", sorted(s for _, s, _ in active) == ["active", "replaced"], active)
check("AI مصدر الحدث", all(src == "ai" for _, _, src in active))

# تحليل تزايدي: رسالة جديدة بس
ws.merge(parse_chat(CHAT2 + "17/11/2026, 08:00 - أحمد: الواجب بكرة\n"), "c3.txt")
msgs2 = ws.sorted_messages()
todo2 = ai.pending_indices(msgs2, ws.ai)
check("الجديد بس بيتبعت", len(todo2) == 1, todo2)

# خطأ في المفتاح بيوقف بدل ما يكرر
def bad(cfg, system, user, json_mode=False, **kw):
    raise LLMError("المفتاح (API key) غلط")
res, errs = ai.extract_events(cfg, msgs2, list(range(len(msgs2))), complete_fn=bad)
check("خطأ مفتاح: مفيش نتائج وخطأ واضح", not res and len(errs) == 1, errs)
# رد مش JSON
res, errs = ai.extract_events(cfg, msgs2, [0], complete_fn=lambda *a, **k: "مش JSON")
check("رد مش JSON: بيتسجل خطأ والرسائل تتعاد", not res and errs)

print("\nALL OK" if ok else "\nFAILED")
raise SystemExit(0 if ok else 1)
