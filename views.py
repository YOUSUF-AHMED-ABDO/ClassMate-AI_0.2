"""بناء الواجهة (HTML جاهز). كل الدوال بتحوّل بيانات لنص HTML من غير Streamlit، فنقدر نختبرها ونعرضها.
ملاحظة: الـ HTML بيتبني في سطر واحد بدون مسافات أول السطر، عشان Markdown ما يعتبرهوش كود."""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta

from core import Event, days_left_label, weekday_name
from theme import course_color

KIND_CLASS = {"امتحان/كويز": "exam", "تسليم": "deadline", "إعلان": "ann", "محاضرة/سكشن/موعد": "sched", "ملف/رابط": "file"}
KIND_ICON = {"exam": "📝", "deadline": "📌", "ann": "📢", "sched": "🕘", "file": "📎"}
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
LONG_TEXT = 420
MAX_LINES = 6


def esc(t: str) -> str:
    # $ بتتحول لكيان HTML عشان Markdown ما يعتبرهاش معادلة رياضية
    return html.escape(t).replace("\r", "").replace("\n", "<br>").replace("$", "&#36;")


def arabic_date(d: date) -> str:
    return f"{weekday_name(d)} {d.day} {MONTHS[d.month - 1]} {d.year}"


def highlight(text: str, query: str = "") -> str:
    out = esc(text)
    for tok in {t for t in re.findall(r"\w+", query) if len(t) > 1}:
        out = re.sub(f"({re.escape(html.escape(tok))})", r"<mark>\1</mark>", out, flags=re.I)
    return out


def eta_label(ev: Event, today: date, now: datetime | None = None) -> str:
    """«بعد 3 ساعات» لو النهارده الفعلي ومعروف الوقت، وإلا «بكرة» / «بعد 4 أيام»."""
    if ev.day is None:
        return ""
    if now and ev.day == now.date() == today and ev.time:
        h, m = (int(x) for x in ev.time.split(":"))
        mins = int((datetime.combine(ev.day, datetime.min.time()).replace(hour=h, minute=m) - now).total_seconds() // 60)
        if mins <= -60:
            return "خلص النهارده"
        if mins <= 0:
            return "شغّال دلوقتي"
        if mins < 60:
            return f"بعد {mins} دقيقة"
        return f"بعد {mins // 60} ساعة" + (f" و{mins % 60} دقيقة" if mins % 60 else "")
    return days_left_label(ev.day, today)


def chip(text: str, cls: str = "", style: str = "") -> str:
    return f"<span class='cm-chip {cls}'" + (f" style='{style}'" if style else "") + f">{text}</span>"


def course_chip(name: str, known: list[str] | None = None) -> str:
    return chip(f"<i></i>{esc(name)}", "course", f"--cc:{course_color(name, known)}") if name else ""


def _cut(text: str) -> tuple[str, str]:
    """بيقصّ الرسالة الطويلة (بالحروف أو بعدد الأسطر) ويرجّع (الظاهر, الباقي)."""
    lines = text.split("\n")
    head = "\n".join(lines[:MAX_LINES])
    head = head[:LONG_TEXT]
    return (head, text[len(head):]) if len(head) < len(text) else (text, "")


def _body(text: str, query: str, cls: str) -> str:
    head, rest = _cut(text)
    if not rest.strip():
        return f"<div class='{cls}'>{highlight(text, query)}</div>"
    return (f"<div class='{cls}'>{highlight(head.rstrip(), query)}…</div>"
            f"<details><summary>عرض الرسالة كاملة</summary><div class='cm-sm'>{highlight(rest.lstrip(), query)}</div></details>")


def event_card(ev: Event, today: date | None = None, show_day: bool = False, query: str = "",
               known_courses: list[str] | None = None, now: datetime | None = None) -> str:
    kcls = KIND_CLASS.get(ev.kind, "")
    cls = ["cm-card", kcls]
    chips = [chip(f"{KIND_ICON.get(kcls, '💬')} {esc(ev.kind)}")]
    if ev.course:
        chips.append(course_chip(ev.course, known_courses))
    dead = ev.status != "active"
    if dead:
        cls.append("dead")
        chips.append(chip(esc(ev.note or "قديم")))
    if ev.done:
        cls.append("done")
        chips.append(chip("✔ خلّصته", "ok"))
    if show_day and ev.day and today:
        diff = (ev.day - today).days
        if not dead and not ev.done:
            cls.append("past" if diff < 0 else ("soon" if diff <= 2 else ""))
        t = f" · {ev.time}{'؟' if ev.time_guessed else ''}" if ev.time else ""
        hot = " hot" if (0 <= diff <= 2 and not dead and not ev.done) else ""
        chips.insert(0, chip(f"⏰ {esc(eta_label(ev, today, now))}{t}", "when" + hot))
    if ev.source == "ai":
        chips.append(chip("🤖 AI"))
    if ev.source == "manual":
        chips.append(chip("✍️ يدوي"))
    elif ev.edited:
        chips.append(chip("✏️ معدّل"))
    if ev.needs_review and not dead:
        why = ("الساعة تقدير" if ev.time_guessed else "فيها أكتر من تاريخ" if len(ev.all_dates) > 1
               else "فيها أكتر من وقت" if len(set(ev.all_times)) > 1 else "غير مؤكد")
        chips.append(chip(f"⚠️ راجعه · {why}", "warn"))
    if ev.ai_title:
        main = f"<div class='cm-title'>{esc(ev.ai_title)}</div>" + _body(ev.msg.text, query, "cm-sm")
    else:
        main = _body(ev.msg.text, query, "cm-body")
    meta = "" if ev.source == "manual" else f"<div class='cm-meta'>👤 {esc(ev.msg.sender)} · {ev.msg.when:%d/%m/%Y %H:%M}</div>"
    return f"<div class='{' '.join(c for c in cls if c)}'><div class='cm-row'>{''.join(chips)}</div>{main}{meta}</div>"


def message_card(text: str, sender: str, when: datetime, query: str = "") -> str:
    return (f"<div class='cm-card'><div class='cm-body'>{highlight(text, query)}</div>"
            f"<div class='cm-meta'>👤 {esc(sender)} · {when:%d/%m/%Y %H:%M}</div></div>")


def day_header(d: date, today: date, n: int = 0) -> str:
    tag = f" · {days_left_label(d, today)}" if abs((d - today).days) <= 7 else ""
    cnt = f"<span class='cnt'>{n} موعد</span>" if n else ""
    return f"<div class='cm-day'>📅 {weekday_name(d)} {d.day} {MONTHS[d.month - 1]}{esc(tag)} {cnt}</div>"


def tiles(items: list[tuple[str, int | str, str]]) -> str:
    cells = "".join(f"<div class='cm-tile'><div class='i'>{i}</div><div class='n'>{n}</div><div class='l'>{esc(l)}</div></div>"
                    for i, n, l in items)
    return f"<div class='cm-tiles'>{cells}</div>"


def hero(chat_name: str, today: date, nxt: Event | None, known_courses: list[str] | None = None,
         now: datetime | None = None) -> str:
    name = esc(chat_name) if chat_name else "جروب الدفعة"
    greet = (f"<div class='cm-greet'><h1>أهلاً 👋</h1><p class='cm-sub'>{name}</p>"
             f"<span class='cm-date'>📆 {arabic_date(today)}</span></div>")
    if nxt:
        t = f" · الساعة {nxt.time}{'؟' if nxt.time_guessed else ''}" if nxt.time else ""
        title = nxt.ai_title or " ".join(nxt.msg.text.split())
        title = title if len(title) <= 130 else title[:127] + "…"
        chips = chip(f"{KIND_ICON.get(KIND_CLASS.get(nxt.kind, ''), '💬')} {esc(nxt.kind)}")
        if nxt.course:
            chips += course_chip(nxt.course, known_courses)
        chips += chip(f"{weekday_name(nxt.day)} {nxt.day.day} {MONTHS[nxt.day.month - 1]}{t}", "when")
        if nxt.needs_review:
            chips += chip("⚠️ راجعه", "warn")
        nxt_html = (f"<div class='cm-next'><div class='cm-lbl'>⏭ الحدث الجاي</div><div class='cm-eta'>{esc(eta_label(nxt, today, now))}</div>"
                    f"<div class='cm-nt'>{esc(title)}</div><div class='cm-row'>{chips}</div></div>")
    else:
        nxt_html = ("<div class='cm-next'><div class='cm-lbl'>⏭ الحدث الجاي</div><div class='cm-eta'>مفيش حاجة 🎉</div>"
                    "<div class='cm-nt'>مفيش مواعيد جاية متعرّفة. ارفع تصدير أحدث أو ضيف موعد بإيدك.</div></div>")
    return f"<div class='cm-hero'>{greet}{nxt_html}</div>"


def legend(counts: dict[str, int], known: list[str]) -> str:
    return "<div class='cm-legend'>" + "".join(course_chip(n, known) .replace("</span>", f" · {c}</span>")
                                              for n, c in counts.items()) + "</div>"


def empty(msg: str) -> str:
    return f"<div class='cm-empty'>{esc(msg)}</div>"


def week_start_of(d: date) -> date:
    """بداية الأسبوع عندنا السبت."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def week_grid(events: list[Event], start: date, today: date, show_old: bool = False, max_per_day: int = 4) -> str:
    cols = []
    for i in range(7):
        d = start + timedelta(days=i)
        evs = [e for e in events if e.day == d and (show_old or e.status == "active")]
        evs.sort(key=lambda e: e.time or "99:99")
        pills = []
        for e in evs[:max_per_day]:
            k = KIND_CLASS.get(e.kind, "")
            head = f"{e.time or ''}{'؟' if e.time_guessed else ''} {esc(e.course or e.kind)}".strip()
            title = e.ai_title or " ".join(e.msg.text.split())
            title = title if len(title) <= 46 else title[:44] + "…"
            pills.append(f"<div class='cm-pill {k}{' done' if e.done else ''}'><b>{head}</b><span>{esc(title)}</span></div>")
        if len(evs) > max_per_day:
            pills.append(f"<div class='cm-more'>+{len(evs) - max_per_day} كمان</div>")
        today_cls = (" today" if d == today else "") + ("" if (evs or d == today) else " empty")
        badge = " · النهارده" if d == today else ""
        cols.append(f"<div class='cm-col{today_cls}'><div class='h'><b>{weekday_name(d)}{badge}</b><span>{d.day}/{d.month}</span></div>{''.join(pills)}</div>")
    return f"<div class='cm-weekwrap'><div class='cm-week'>{''.join(cols)}</div></div>"
