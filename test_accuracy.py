"""اختبارات الدقة: python test_accuracy.py"""
from datetime import date

from core import analyze, extract_date_info, extract_time_info, parse_chat

SUN = date(2026, 11, 15)   # الأحد
MON = date(2026, 11, 16)   # الاثنين


def chat(*lines):
    return parse_chat("\n".join(lines) + "\n")


def check(name, got, want):
    ok = got == want
    print(("✅" if ok else "❌"), name, "" if ok else f"-> got {got!r}, want {want!r}")
    return ok


results = []
# 1) ميعاد لسه متحددش
results.append(check("لسه متحددش", extract_date_info("الامتحان لسه ما اتحددش اليوم", SUN)[0], None))
# 2) ساعة من غير ص/م = تقدير
results.append(check("الساعة 2 تقدير", extract_time_info("السكشن الأربعاء الساعة 2"), ("14:00", True)))
results.append(check("3 م مؤكد", extract_time_info("الساعة 3 م"), ("15:00", False)))
# 3) أكتر من تاريخ: يختار الجديد
d, alld, *_ = extract_date_info("اتأجل الكويز من الخميس إلى الأحد", MON)
results.append(check("الجديد بعد إلى", d, date(2026, 11, 22)))
results.append(check("كل التواريخ", len(alld), 2))
results.append(check("بدل X", extract_date_info("الكويز يوم الأحد بدل الخميس", MON)[0], date(2026, 11, 22)))
# 4) الأسبوع الجاي + يوم
results.append(check("الاسبوع الجاي الخميس", extract_date_info("الاجتماع الاسبوع الجاي يوم الخميس", SUN)[0], date(2026, 11, 26)))
results.append(check("الأسبوع الجاي بدون يوم", extract_date_info("الميد الاسبوع الجاي", SUN)[0], None))
# 5) ل/ب الجر
results.append(check("ليوم الأحد", extract_date_info("اتأجلت ليوم الأحد", MON)[0], date(2026, 11, 22)))
results.append(check("لبكرة", extract_date_info("اتقدمت لبكرة", MON)[0], date(2026, 11, 17)))
# 6) أرقام عادية مش تواريخ
results.append(check("2-3 مش تاريخ", extract_date_info("حل 2-3 أسئلة بس", SUN)[0], None))
results.append(check("أرقام هندية", extract_date_info("التسليم ٢٠/١١", SUN)[0], date(2026, 11, 20)))
# 7) تغيير يلغي القديم
m = chat("15/11/2026, 10:00 - أحمد: الكويز يوم الخميس الساعة 10 ص",
         "16/11/2026, 09:00 - د. منى: تم تأجيل الكويز ليوم الأحد")
a = analyze(m)
results.append(check("القديم اتغيّر", [e.status for e in a.events], ["replaced", "active"]) if len(a.events) == 2 else check("events", len(a.events), 2))
# 8) إلغاء بدون تاريخ
m = chat("15/11/2026, 10:00 - أحمد: السكشن يوم الأربعاء الساعة 12 ظ",
         "16/11/2026, 09:00 - د. منى: تم إلغاء السكشن")
a = analyze(m)
results.append(check("إلغاء", [e.status for e in a.events], ["cancelled"]))
# 9) رسالة معدلة
m = chat("15/11/2026, 10:00 - أحمد: تسليم الواجب بكرة <This message was edited>")
results.append(check("edited tag", m[0].text, "تسليم الواجب بكرة"))
# 10) سؤال مش ميعاد
a = analyze(chat("15/11/2026, 10:00 - أحمد: مين رايح السكشن بكرة؟"))
results.append(check("سؤال", len(a.events), 0))

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
