"""اختبارات المواد والتعديل اليدوي والتشيك لست والمواعيد اليدوية: python test_features.py"""
import os, sys
from collections import Counter
from datetime import date
sys.path.insert(0, os.path.dirname(__file__))
from core import analyze, detect_course, parse_chat, parse_courses_text, courses_to_text, DEFAULT_COURSES

ok = True
def check(name, cond, extra=""):
    global ok
    print(("✅" if cond else "❌"), name, extra)
    ok &= bool(cond)

# المواد
check("إدارة أعمال", detect_course("محاضره اداره الاعمال ٨ بليل اتعدلت", DEFAULT_COURSES) == "إدارة أعمال")
check("تفاضل", detect_course("كويز تفاضل بكره اربعه وربع", DEFAULT_COURSES) == "تفاضل وتكامل")
check("IS الإنجليزي", detect_course("في محاضرة IS النهارده الساعه 9", DEFAULT_COURSES) == "نظم معلومات")
check("this مش IS", detect_course("this thing", DEFAULT_COURSES) == "")
check("مفيش مادة", detect_course("مين رايح بكرة", DEFAULT_COURSES) == "")
custom = parse_courses_text("ذكاء: ai, ذكاء اصطناعي\nشبكات: network، شبكات")
check("مواد مخصصة", detect_course("سكشن الشبكات", custom) == "شبكات" and parse_courses_text(courses_to_text(custom)) == custom)

# تعديل يدوي + تشيك لست + موعد يدوي
msgs = parse_chat("15/11/2026, 10:00 - أحمد: الكويز يوم الخميس الساعة 10 ص\n15/11/2026, 10:05 - سارة: تسليم المشروع بكرة\n")
a = analyze(msgs)
k0, k1 = msgs[0].key, msgs[1].key
check("بدون تعديل", [str(e.day) for e in a.events] == ["2026-11-16", "2026-11-19"], [str(e.day) for e in a.events])
a = analyze(msgs, edits={k0: {"date": "2026-11-25", "time": "14:30"}, k1: {"hide": True}}, done={k0})
ev = a.events
check("التعديل اتطبّق", len(ev) == 1 and ev[0].day == date(2026, 11, 25) and ev[0].time == "14:30" and ev[0].edited and not ev[0].needs_review)
check("التشيك لست", ev[0].done)
a = analyze(msgs, manual=[{"id": "x1", "title": "مراجعة جماعية", "date": "2026-11-22", "time": "18:00", "kind": "lecture", "course": "تفاضل وتكامل"}])
man = [e for e in a.events if e.source == "manual"]
check("موعد يدوي", len(man) == 1 and man[0].day == date(2026, 11, 22) and man[0].course == "تفاضل وتكامل" and man[0].msg.key == "m:x1")
check("المواد في التحليل", "تفاضل وتكامل" in a.courses)

# على المحادثة الحقيقية (لو موجودة)
p = "/tmp/cs/chat.txt"
if os.path.exists(p):
    a = analyze(parse_chat(open(p, encoding="utf-8").read()))
    c = Counter(e.course or "—" for e in a.events)
    check("مواد على المحادثة الحقيقية", len(a.courses) >= 4, dict(c))
print("\nALL OK" if ok else "\nFAILED")
raise SystemExit(0 if ok else 1)
