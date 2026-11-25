from datetime import date
from core import *

sample = open('sample_chat.txt', encoding='utf-8').read()
msgs = parse_chat(sample)
assert len(msgs) == 12, len(msgs)
a = analyze(msgs, trusted={"دكتور المادة"})
today = date(2026, 11, 16)
for e in a.events:
    print(e.day, weekday_name(e.day), e.time, e.kind, "|", e.title)
print("announcements:", len(a.announcements), "files:", len(a.files), "undated:", len(a.undated_tasks))
print(rule_based_summary(a, today))

# iOS + AM/PM + multiline + system + Arabic digits + media
ios = """\u200e[15/11/2026, 10:15:30] \u200eAhmed: Quiz tomorrow at 2:30 PM
and bring calculators
[15/11/2026, 10:16:00] Messages and calls are end-to-end encrypted.
[15/11/2026, 10:17:00] سارة: <Media omitted>
[16/11/2026, 9:05:10] د. منى: تسليم المشروع يوم ٢٠/١١ الساعة ٣ مساءً
16/11/2026, 11:00 م - علي: امتحان الميدتيرم بعد بكرة الساعة 9 صباحا
16/11/2026, 11:05 م - علي: اللينك https://drive.google.com/x
"""
m2 = parse_chat(ios)
for m in m2: print(m.when, m.sender, repr(m.text))
a2 = analyze(m2)
for e in a2.events: print(e.day, e.time, e.kind, e.title)
print([ (e.kind) for e in a2.files])
# US order detection
us = "11/15/2026, 10:15 AM - X: assignment due 11/20\n"
print(parse_chat(us)[0].when)
# search
print([m.text[:30] for _, m in search(msgs, "موعد السكشن؟")])
print([m.text[:30] for _, m in search(msgs, "المحاضره")])  # without ة
ics = events_to_ics(a.events); print(ics[:400])
