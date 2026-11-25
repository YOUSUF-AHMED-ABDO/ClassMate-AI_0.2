"""ClassMate AI - المنطق الأساسي (بدون أي اعتماد على Streamlit، عشان نقدر نختبره بسهولة)."""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

# ───────────────────────── تطبيع النص العربي ─────────────────────────

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")  # تشكيل + تطويل
_INVISIBLE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def clean_invisible(text: str) -> str:
    return _INVISIBLE.sub("", text)


def normalize(text: str) -> str:
    """يوحّد الحروف والأرقام ويشيل التشكيل عشان البحث والمطابقة يبقوا أدق."""
    text = clean_invisible(text).translate(_DIGITS)
    text = _DIACRITICS.sub("", text).translate(_LETTERS)
    return text.lower()


# ───────────────────────── قراءة ملف واتساب ─────────────────────────

@dataclass
class Message:
    idx: int
    when: datetime
    sender: str
    text: str
    key: str = ""  # معرّف ثابت للرسالة، بيستخدم في الدمج بين التصديرات وفي نتايج الذكاء الاصطناعي


# يدعم: أندرويد "15/11/2026, 10:15 - اسم: نص"، وأيفون "[15/11/2026, 10:15:30] اسم: نص"،
# وصيغة 12 ساعة (AM/PM أو ص/م).
_HEADER = re.compile(
    r"^\[?(?P<d>\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4})[,،]?\s+"
    r"(?P<h>\d{1,2}):(?P<m>\d{2})(?::\d{2})?\s*(?P<ap>[APap]\.?[Mm]\.?|ص|م)?\]?\s*(?:[-–—]\s*)?(?P<body>.*)$"
)

_SKIP_TEXT = [
    "this message was deleted", "تم حذف هذه الرسالة", "you deleted this message", "المستند محذوف",
    "<voice message omitted>", "<audio omitted>", "<sticker omitted>", "<video omitted>", "<gif omitted>",
]


def _detect_order(raw_dates: list[str]) -> str:
    """بيحدد هل التاريخ يوم/شهر ولا شهر/يوم (الافتراضي يوم/شهر)."""
    for d in raw_dates:
        parts = re.split(r"[/\-.]", d)
        if len(parts[0]) == 4:
            return "ymd"
        a, b = int(parts[0]), int(parts[1])
        if a > 12:
            return "dmy"
        if b > 12:
            return "mdy"
    return "dmy"


def _to_datetime(d: str, h: int, mi: int, ap: str | None, order: str) -> datetime | None:
    parts = [int(x) for x in re.split(r"[/\-.]", d)]
    if len(parts) != 3:
        return None
    if order == "ymd":
        y, mo, da = parts
    elif order == "mdy":
        mo, da, y = parts
    else:
        da, mo, y = parts
    if y < 100:
        y += 2000
    if ap:
        a = ap.lower().replace(".", "")
        if a in ("pm", "م") and h < 12:
            h += 12
        elif a in ("am", "ص") and h == 12:
            h = 0
    try:
        return datetime(y, mo, da, h, mi)
    except ValueError:
        return None


_MEDIA_RE = re.compile(
    r"^(?:\[forwarded\]\s*)?<(image|video|sticker|gif|audio|voice message|document|contact card|location|photo) omitted>\s*(.*)$",
    re.I | re.S,
)
_EDITED_RE = re.compile(r"\s*<(?:this message was edited|تم تعديل هذه الرسالة)>\s*$", re.I)
_NOISE = ("<message_history_notice message>", "<unknown message>", "<media omitted>", "<تم استبعاد الوسائط>")


def media_kind(text: str) -> str:
    m = _MEDIA_RE.match(text.strip())
    return m.group(1).lower() if m else ""


def _finalize(messages: list[Message]) -> list[Message]:
    """تنضيف مشترك: تجاهل الوسائط الفاضية والمحذوف، وإعطاء كل رسالة مفتاح ثابت."""
    out: list[Message] = []
    for msg in messages:
        msg.text = _EDITED_RE.sub("", msg.text.strip())
        low = msg.text.lower().strip("_* ")
        if not low or low in _NOISE or any(low.startswith(sk) for sk in _SKIP_TEXT):
            continue
        m = _MEDIA_RE.match(msg.text)
        if m and m.group(1).lower() != "document" and not m.group(2).strip():
            continue  # صورة/صوت/فيديو من غير تعليق
        out.append(msg)
    seen: Counter = Counter()
    for i, msg in enumerate(out):
        msg.idx = i
        base = f"{msg.when:%Y%m%d%H%M}|{msg.sender}|{' '.join(msg.text.split())[:80]}"
        seen[base] += 1  # نفس الرسالة بنفس الدقيقة مرتين = رقمين مختلفين
        msg.key = hashlib.sha1(f"{base}|{seen[base]}".encode("utf-8")).hexdigest()[:14]
    return out


def _parse_txt(raw: str) -> list[Message]:
    raw = clean_invisible(raw).replace("\r\n", "\n")
    lines = raw.split("\n")
    heads = [(i, _HEADER.match(line)) for i, line in enumerate(lines)]
    order = _detect_order([m.group("d") for _, m in heads if m][:400])

    messages: list[Message] = []
    current: Message | None = None
    for line, (_, m) in zip(lines, heads):
        if m:
            current = None  # الرسالة اللي فاتت خلصت
            body = m.group("body")
            if ": " not in body and not body.endswith(":"):
                continue  # رسالة نظام (تشفير، انضمام، ...) - نتجاهلها
            sender, _, text = body.partition(":")
            when = _to_datetime(m.group("d"), int(m.group("h")), int(m.group("m")), m.group("ap"), order)
            if when is None:
                continue
            current = Message(len(messages), when, sender.strip(), text.strip())
            messages.append(current)
        elif current is not None:
            current.text += "\n" + line  # رسالة متعددة الأسطر
    return _finalize(messages)


_MD_DATE = re.compile(r"^##\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*$")
_MD_MSG = re.compile(r"^\[(\d{1,2}):(\d{2})\s*([AaPp][Mm])\]\s+\*\*(.+?):\*\*\s?(.*)$")
_MD_PLACE = re.compile(r"\[(Image|Video|Sticker|GIF|Audio|Voice message|Document|Contact card|Location)\]", re.I)


def _parse_md(raw: str) -> list[Message]:
    """صيغة Markdown: '## October 13, 2026' ثم '[10:22 AM] **الاسم:** النص'."""
    day: date | None = None
    messages: list[Message] = []
    current: Message | None = None
    for line in clean_invisible(raw).replace("\r\n", "\n").split("\n"):
        dm = _MD_DATE.match(line)
        if dm:
            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    day = datetime.strptime(f"{dm.group(1)} {dm.group(2)} {dm.group(3)}", fmt).date()
                    break
                except ValueError:
                    continue
            current = None
            continue
        mm = _MD_MSG.match(line)
        if mm and day:
            h, mi, ap = int(mm.group(1)), int(mm.group(2)), mm.group(3).lower()
            if ap == "pm" and h < 12:
                h += 12
            elif ap == "am" and h == 12:
                h = 0
            text = _MD_PLACE.sub(lambda x: f"<{x.group(1).lower()} omitted>", mm.group(5))
            text = text.replace("[message_history_notice message]", "<message_history_notice message>")
            text = text.replace("[unknown message]", "<unknown message>").replace("**", "")
            current = Message(len(messages), datetime.combine(day, datetime.min.time()).replace(hour=h, minute=mi),
                              mm.group(4).strip(), text)
            messages.append(current)
        elif line.startswith(">"):
            continue  # اقتباس الرد (الرسالة الأصلية) - مش جزء من النص
        elif re.match(r"^\[\d{1,2}:\d{2}\s*[AaPp][Mm]\]", line) or line.startswith(("---", "## ", "# ")):
            current = None  # رسالة نظام أو عنوان يوم = نهاية الرسالة (السطر الفاضي مش بيقفلها)
        elif current is not None:
            current.text += "\n" + _MD_PLACE.sub(lambda x: f"<{x.group(1).lower()} omitted>", line).replace("**", "")
    return _finalize(messages)


def parse_chat(raw: str) -> list[Message]:
    """بيعرف الصيغة لوحده: تصدير واتساب النصي (أندرويد/أيفون) أو ملف Markdown."""
    raw = raw.lstrip("\ufeff \n")
    return _parse_md(raw) if raw.startswith("# WhatsApp Chat Export") else _parse_txt(raw)


_PHONE_RE = re.compile(r"^[+\d\s\-()]{7,}$")


def mask_phone(name: str) -> str:
    """بيخفي رقم الموبايل ويسيب آخر 4 أرقام عشان نفرّق بين الأشخاص."""
    if _PHONE_RE.match(name.strip()):
        digits = re.sub(r"\D", "", name)
        return f"عضو ••{digits[-4:]}"
    return name


def mask_messages(messages: list[Message]) -> list[Message]:
    return [replace(m, sender=mask_phone(m.sender)) for m in messages]


# ───────────────────────── تصنيف الرسائل ─────────────────────────

TAG_LABELS = {
    "announcement": "إعلان",
    "deadline": "تسليم",
    "exam": "امتحان/كويز",
    "schedule": "محاضرة/سكشن/موعد",
    "file": "ملف/رابط",
}

_KEYWORDS = {
    "announcement": ["إعلان", "اعلان", "تنبيه", "مهم", "ملحوظة", "ملاحظة", "انتبهوا", "تم تغيير", "تم تغير", "اتغير",
                     "تم تأجيل", "اتأجل", "تأجيل", "تم إلغاء", "تم الغاء", "اتلغى", "إلغاء", "announcement", "urgent", "important"],
    "deadline": ["واجب", "تسليم", "سلموا", "تسلموا", "ديدلاين", "deadline", "assignment", "مشروع", "تكليف", "ريبورت",
                 "تقرير", "due", "submit", "سليكشن"],
    "exam": ["امتحان", "اختبار", "كويز", "quiz", "exam", "ميد", "midterm", "فاينل", "final", "اورال", "شفوي", "ميدتيرم"],
    "schedule": ["محاضرة", "محاضره", "سكشن", "section", "lecture", "لاب", "معمل", "ميعاد", "موعد", "جدول", "تمرين"],
    "file": ["pdf", "ppt", "pptx", "doc", "docx", "xlsx", "ملف", "رابط", "لينك", "link", "drive", "ملزمة", "ملزمه",
             "سلايدز", "slides", "شيت", "مذكرة", "مذكره"],
}


def _kw_regex(words: list[str]) -> re.Pattern:
    alts = "|".join(sorted({re.escape(normalize(w)) for w in words}, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:و|ب|ل|ف|ك|ال|وال|بال|لل|فال)?(?:{alts})(?:ات|ين|ون)?(?!\w)")


_TAG_RE = {tag: _kw_regex(words) for tag, words in _KEYWORDS.items()}
_URL_RE = re.compile(r"https?://\S+|www\.\S+")


def tag_message(text: str) -> list[str]:
    n = normalize(text)
    tags = [t for t, rx in _TAG_RE.items() if rx.search(n)]
    if _URL_RE.search(text) and "file" not in tags:
        tags.append("file")
    return tags


# ───────────────────────── استخراج التاريخ والوقت ─────────────────────────

_WEEKDAYS = {
    "اثنين": 0, "اتنين": 0, "ثلاثاء": 1, "تلاتاء": 1, "تلات": 1, "اربعاء": 2, "اربع": 2,
    "خميس": 3, "جمعه": 4, "سبت": 5, "احد": 6,
}
_WEEKDAY_NAMES = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
_WD_ALT = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))
# "يوم الخميس" / "الخميس" / "للخميس" / "ليوم الأحد"
_WD_RE = re.compile(rf"(?<!\w)(?:ل|ب)?(?:يوم\s+(?:ال)?|ال)({_WD_ALT})(?!\w)")
_REL_AFTER = re.compile(r"(?<!\w)(?:ل|ب)?(?:بعد\s+بكر[هةا]|بعد\s+غد[اً]?)(?!\w)")
_REL = [
    (re.compile(r"(?<!\w)(?:ل|ب)?(?:بكر[هةا]|غدا|غد)(?!\w)"), 1),
    (re.compile(r"(?<!\w)(?:ل|ب)?(?:النهارد[هةا]|انهارد[هةا]|اليوم|الليل[هة])(?!\w)"), 0),
]
_NEXT_WEEK = re.compile(r"(?<!\w)(?:الاسبوع|اسبوع)\s+(?:القادم|القادمه|الجاي|الجايه|اللي\s+جاي)(?!\w)")
_DATE_RE = re.compile(
    r"(?<![\d:/.\-])(?:(?P<d1>\d{1,2})[/\-.](?P<m1>\d{1,2})[/\-.](?P<y1>\d{2,4})|(?P<d2>\d{1,2})\s*/\s*(?P<m2>\d{1,2}))(?![\d:/])"
)
# كلام معناه إن الميعاد لسه متحددش، أو غير مؤكد
_UNDECIDED = re.compile(
    r"(?<!\w)(?:ما|مش|لم)\s+(?:ا?تحدد|يتحدد|يحدد|محدد|اتعرف)|"
    r"(?<!\w)(?:هيتحدد|هنحدد|هيتم\s+تحديد|سيتم\s+تحديد|هنبلغكم|هنقولكم|لاحقا|بعدين)(?!\w)"
)
_HEDGE = re.compile(r"(?<!\w)(?:غالبا|احتمال|ممكن|يمكن|تقريبا|اظن|مش\s+متاكد)(?!\w)")
# كلمات بتدل إن اللي بعدها هو القيمة "الجديدة"
_CHANGE_BEFORE = re.compile(r"(?<!\w)و?(?:الي|الجديد|الجديده|بقي|بقا|بقت|هيبقي|هتبقي|هيبقا|هتبقا|يبقا|اصبح|اصبحت)(?!\w)")

def _pick(n: str, cands: list, with_flag: bool = False):
    """cands = [(pos, value)]. بيفضّل القيمة بعد "إلى/الجديد/ل"، وبيتجاهل اللي بعد "بدل"."""
    cands = sorted(cands, key=lambda c: c[0])
    fresh = [c for c in cands if "بدل" not in n[max(0, c[0] - 14):c[0]]]
    cands = fresh or cands
    for pos, val in cands:
        if n[pos:pos + 1] == "ل" or _CHANGE_BEFORE.search(n[max(0, pos - 22):pos]):
            return (val, True) if with_flag else val
    return (cands[0][1], False) if with_flag else cands[0][1]


_WORD_NUMS = {
    "واحده": 1, "وحده": 1, "اتنين": 2, "اثنين": 2, "ثنتين": 2, "تلاته": 3, "ثلاثه": 3, "تلات": 3,
    "اربعه": 4, "اربع": 4, "خمسه": 5, "خمس": 5, "سته": 6, "ست": 6, "سبعه": 7, "سبع": 7,
    "تمانيه": 8, "ثمانيه": 8, "تمنيه": 8, "تمان": 8, "ثماني": 8, "تسعه": 9, "تسع": 9, "عشره": 10, "عشر": 10,
    "احداشر": 11, "حداشر": 11, "اتناشر": 12, "اثناعشر": 12,
}
_NUM_ALT = "|".join(sorted((re.escape(w) for w in _WORD_NUMS), key=len, reverse=True))
_MARK = (r"(?:بعد\s+الظهر|صباحا|صباح|الصبح|صبح|ظهرا|ظهر|الظهر|عصرا|عصر|العصر|مساءا|مساء|المساء|مسا|"
         r"بالليل|بليل|الليل|ليلا|ص|م|am|pm)")
_AM = {"ص", "am", "صباحا", "صباح", "الصبح", "صبح"}
_NIGHT = {"بالليل", "بليل", "الليل", "ليلا"}
_TIME_B = re.compile(rf"(?<![\d/:.])(?P<h>\d{{1,2}}):(?P<m>\d{{2}})(?!\d)(?:\s*(?P<mark>{_MARK})(?!\w))?")
_TIME_C = re.compile(
    rf"(?<![\w/:.])(?P<pre>(?:الساعه|ساعه)\s*)?(?:(?P<dig>\d{{1,2}})(?![\d:/])|(?P<word>{_NUM_ALT})(?!\w))"
    rf"(?:\s*و\s*(?P<plus>نص|نصف|ربع|تلت)(?!\w)|\s+الا\s+(?P<minus>ربع|تلت)(?!\w))?"
    rf"(?:\s*(?P<mark>{_MARK})(?!\w))?"
)


def _hhmm(h: int, mi: int, mark: str | None):
    """بيرجّع (HH:MM, تقدير؟). من غير ص/م الساعات 1–6 بتتحسب بعد الظهر ومعلّمة كتقدير."""
    if h > 23 or mi > 59:
        return None
    guessed = False
    if mark:
        if mark in _AM:
            h = 0 if h == 12 else h
        elif mark.startswith(("ظهر", "الظهر", "بعد")):
            h = h if h >= 11 else h + 12
        elif mark in _NIGHT and h == 12:
            h = 0
        elif h < 12:
            h += 12
    else:
        guessed = h <= 12
        if 1 <= h <= 6:
            h += 12
    return f"{h:02d}:{mi:02d}", guessed


def extract_times(text: str):
    """كل الأوقات اللي في الرسالة: [(مكان، (HH:MM, تقدير؟))]. بيفهم «٨ ونص» و«اربعه وربع» و«9بليل»."""
    n = normalize(text)
    out = []
    for m in _TIME_B.finditer(n):
        r = _hhmm(int(m["h"]), int(m["m"]), m["mark"])
        if r:
            out.append((m.start(), r))
    for m in _TIME_C.finditer(n):
        if not (m["pre"] or m["plus"] or m["minus"] or m["mark"]):
            continue  # رقم لوحده مش وقت
        h = int(m["dig"]) if m["dig"] else _WORD_NUMS[m["word"]]
        mi = 0
        if m["plus"]:
            mi = {"نص": 30, "نصف": 30, "ربع": 15, "تلت": 20}[m["plus"]]
        elif m["minus"]:
            h, mi = (h - 2) % 12 + 1, {"ربع": 45, "تلت": 40}[m["minus"]]
        r = _hhmm(h, mi, m["mark"])
        if r:
            out.append((m.start(), r))
    return out


def extract_time_info(text: str):
    """(HH:MM, تقدير؟) أو None. لو في أكتر من وقت بياخد اللي بعد "إلى/الجديد"."""
    cands = extract_times(text)
    return _pick(normalize(text), cands) if cands else None


def extract_time(text: str) -> str | None:
    r = extract_time_info(text)
    return r[0] if r else None


def _explicit(m: re.Match, sent: date) -> date | None:
    if m.group("d1"):
        d1, d2, y = int(m.group("d1")), int(m.group("m1")), m.group("y1")
    else:
        d1, d2, y = int(m.group("d2")), int(m.group("m2")), None
    yy = (int(y) + (2000 if len(y) <= 2 else 0)) if y else sent.year
    for day, mon in ((d1, d2), (d2, d1)):  # يوم/شهر أولًا
        try:
            found = date(yy, mon, day)
        except ValueError:
            continue
        if not y and found < sent - timedelta(days=30):
            found = found.replace(year=found.year + 1)
        return found
    return None


def _week_start(d: date) -> date:
    """بداية الأسبوع عندنا السبت."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def extract_date_info(text: str, sent: date):
    """بيرجّع (التاريخ المختار أو None, كل التواريخ, في تردد؟, التاريخ كان "جديد/متغيّر"؟)."""
    n = normalize(text)
    explicit, other = [], []
    for m in _DATE_RE.finditer(n):
        d = _explicit(m, sent)
        if d:
            explicit.append((m.start(), d))
    next_week = bool(_NEXT_WEEK.search(n))
    taken: list[tuple[int, int]] = []
    for m in _REL_AFTER.finditer(n):
        other.append((m.start(), sent + timedelta(days=2)))
        taken.append(m.span())
    for rx, delta in _REL:
        for m in rx.finditer(n):
            if not any(m.start() < e and m.end() > s for s, e in taken):
                other.append((m.start(), sent + timedelta(days=delta)))
    wds = []
    for m in _WD_RE.finditer(n):
        target = _WEEKDAYS[m.group(1)]
        if next_week:
            d = _week_start(sent) + timedelta(days=7 + (target - 5) % 7)
        else:
            d = sent + timedelta(days=(target - sent.weekday()) % 7 or 7)
        wds.append((m.start(), d))
    cands = explicit + other + wds
    if not explicit:
        if _UNDECIDED.search(n) or (next_week and not wds):
            cands = []
    if not cands:
        return None, [], False, False
    best, moved = _pick(n, cands, with_flag=True)
    return best, sorted({d for _, d in cands}), bool(_HEDGE.search(n)), moved


def extract_date(text: str, sent: date) -> date | None:
    return extract_date_info(text, sent)[0]



# ───────────────────────── المواد الدراسية ─────────────────────────

DEFAULT_COURSES = {
    "إدارة أعمال": ["اداره اعمال", "ادارة الاعمال", "business"],
    "حقوق الإنسان": ["حقوق انسان", "حقوق الانسان", "حقوق", "human rights"],
    "إنجليزي": ["انجليزي", "انجليزى", "english"],
    "تفاضل وتكامل": ["تفاضل", "تكامل", "calculus", "دريفاتيف", "derivative"],
    "نظم معلومات": ["نظم معلومات", "نظم المعلومات", "information systems", "is"],
    "علوم الحاسب": ["علوم حاسب", "علوم الحاسب", "computer science", "cs"],
    "إيكولوجي": ["ايكولوجي", "ecology", "بيئه"],
    "برمجة": ["برمجه", "programming", "python", "جافا"],
    "فيزياء": ["فيزياء", "physics"],
    "رياضيات": ["رياضيات", "جبر", "math"],
}


def parse_courses_text(text: str) -> dict:
    """سطر لكل مادة: «الاسم: كلمة، كلمة، كلمة»."""
    out = {}
    for line in text.splitlines():
        name, sep, words = line.partition(":")
        name = name.strip()
        kws = [w.strip() for w in re.split(r"[,،]", words) if w.strip()]
        if sep and name and kws:
            out[name] = kws
    return out


def courses_to_text(courses: dict) -> str:
    return "\n".join(f"{n}: {', '.join(k)}" for n, k in courses.items())


def _kw_pattern(word: str) -> re.Pattern:
    w = normalize(word)
    if re.fullmatch(r"[a-z0-9+#.\- ]+", w):  # كلمة إنجليزي: حدود حروف لاتينية
        return re.compile(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])")
    return re.compile(rf"(?<!\w)(?:و|ب|ل|ف|ك|ال|وال|بال|لل)?{re.escape(w)}(?:ات|ين|ون)?(?!\w)")


_COURSE_CACHE: dict = {}


def detect_course(text: str, courses: dict) -> str:
    """بيرجّع المادة الأكتر ذكرًا في الرسالة (أو فاضي)."""
    key = tuple((n, tuple(k)) for n, k in courses.items())
    pats = _COURSE_CACHE.get(key)
    if pats is None:
        pats = _COURSE_CACHE[key] = [(n, [_kw_pattern(w) for w in k]) for n, k in courses.items()]
    n = normalize(text)
    best, best_score = "", 0
    for name, rxs in pats:
        score = sum(1 for rx in rxs if rx.search(n))
        if score > best_score:
            best, best_score = name, score
    return best


# ───────────────────────── الأحداث والتحليل ─────────────────────────

_SUBJECT_WORDS = ["سكشن", "section", "محاضرة", "واجب", "مشروع", "كويز", "quiz", "امتحان", "ميد", "فاينل", "لاب", "معمل",
                  "تقرير", "تكليف", "اوراق", "ريبورت", "assignment", "بحث"]
_SUBJ_RE = {w: re.compile(rf"(?<!\w)(?:و|ب|ل|ف|ك|ال|وال|بال|لل)?{re.escape(normalize(w))}(?:ات|ين|ون)?(?!\w)")
            for w in _SUBJECT_WORDS}
_CHANGE_RE = re.compile(r"(?<!\w)(?:تغيير|تغير|اتغير|تعديل|اتعدل|تاجيل|اتاجل|اتاجلت|تاجل|الجديد|الجديده|نقل|اتنقل)(?!\w)")
_CANCEL_RE = re.compile(
    r"(?<!\w)(?:الغاء|اتلغي|اتلغت|ملغي|ملغيه|الغيت|الغي)(?!\w)|(?<!\w)ما?فيش\s+(?:ال)?(?:محاضر|سكشن|لاب|معمل)"
)


AI_KINDS = {
    "exam": "امتحان/كويز", "deadline": "تسليم", "lecture": "محاضرة/سكشن/موعد", "section": "محاضرة/سكشن/موعد",
    "lab": "محاضرة/سكشن/موعد", "announcement": "إعلان", "other": "عام",
}
_AI_TAG = {"exam": "exam", "deadline": "deadline", "lecture": "schedule", "section": "schedule", "lab": "schedule",
           "announcement": "announcement", "other": "announcement"}


@dataclass
class Event:
    msg: Message
    kind: str
    day: date | None
    time: str | None
    tags: list[str] = field(default_factory=list)
    score: int = 0
    all_dates: list[date] = field(default_factory=list)
    time_guessed: bool = False
    hedged: bool = False
    question: bool = False
    subjects: set[str] = field(default_factory=set)
    status: str = "active"  # active | replaced | cancelled
    note: str = ""
    moved: bool = False
    all_times: list[str] = field(default_factory=list)
    source: str = "rules"  # rules | ai
    ai_title: str = ""
    ai_skip: bool = False  # الذكاء الاصطناعي (أو أنت) قرر إنها مش حدث
    course: str = ""       # المادة الدراسية
    done: bool = False     # خلّصته (تشيك لست)
    edited: bool = False   # عدّلته يدويًا

    @property
    def title(self) -> str:
        t = self.ai_title or " ".join(self.msg.text.split())
        return t if len(t) <= 160 else t[:157] + "…"

    @property
    def needs_review(self) -> bool:
        if self.day is None:
            return False
        if self.source == "manual" or self.edited:
            return False
        if self.source == "ai":
            return self.hedged
        return self.time_guessed or self.hedged or len(self.all_dates) > 1 or len(set(self.all_times)) > 1


def _kind(tags: list[str]) -> str:
    for t in ("exam", "deadline", "announcement", "schedule", "file"):
        if t in tags:
            return TAG_LABELS[t]
    return "عام"


@dataclass
class Analysis:
    messages: list[Message]
    tagged: list[Event]  # كل الرسائل اللي ليها تصنيف
    announcements: list[Event]
    events: list[Event]  # رسائل ليها تاريخ مستخرج + (تسليم/امتحان/محاضرة/إعلان)
    undated_tasks: list[Event]
    files: list[Event]
    sender_counts: Counter
    per_day: Counter
    ai_used: int = 0  # كام رسالة اتحللت بالذكاء الاصطناعي
    courses: list = field(default_factory=list)  # أسماء المواد اللي ظهرت


def _resolve_status(tagged: list[Event]) -> None:
    """لو رسالة جديدة بتغيّر أو تلغي ميعاد قديم لنفس الموضوع، بنعلّم القديم (للأحداث المستخرجة بالقواعد)."""
    for i, ev in enumerate(tagged):
        if ev.question or not ev.subjects or ev.source == "ai" or ev.ai_skip:
            continue
        n = normalize(ev.msg.text)
        cancel = bool(_CANCEL_RE.search(n))
        moved = ev.moved and ev.day is not None
        change = (bool(_CHANGE_RE.search(n)) or (cancel and moved)) and ev.day is not None
        if not (cancel or change):
            continue
        for old in tagged[:i]:
            if old.status != "active" or old.question or not (old.subjects & ev.subjects):
                continue
            if cancel and not moved and (ev.day is None or old.day == ev.day):
                old.status, old.note = "cancelled", "اتلغى"
            elif change and old.day is not None and old.day != ev.day:
                old.status, old.note = "replaced", f"اتغيّر لـ {ev.day:%d/%m}"
        if cancel and not moved and ev.day is not None:
            ev.status, ev.note = "cancelled", "اتلغى"


def _parse_iso(v) -> date | None:
    try:
        return date.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def _apply_ai(ev: Event, r: dict) -> None:
    """نتيجة الذكاء الاصطناعي بتحل محل القواعد للرسالة دي."""
    kind = r.get("kind", "other")
    ev.source = "ai"
    ev.kind = AI_KINDS.get(kind, "عام")
    ev.tags = [t for t in ev.tags if t == "file"] + [_AI_TAG.get(kind, "announcement")]
    ev.day = _parse_iso(r.get("date"))
    ev.all_dates = [ev.day] if ev.day else []
    t = r.get("time")
    ev.time = t if isinstance(t, str) and re.fullmatch(r"\d{2}:\d{2}", t) else None
    ev.time_guessed, ev.all_times = False, ([ev.time] if ev.time else [])
    ev.hedged = float(r.get("confidence", 1) or 0) < 0.6
    ev.ai_title = str(r.get("title") or "")[:160]
    ev.score = max(ev.score, 3 if kind in ("exam", "deadline") else 2)
    if r.get("status") == "cancelled":
        ev.status, ev.note = "cancelled", "اتلغى"


def analyze(messages: list[Message], trusted: set[str] | None = None, ai: dict | None = None,
            courses: dict | None = None, edits: dict | None = None, done: set | list | None = None,
            manual: list | None = None) -> Analysis:
    """ai: {مفتاح الرسالة: نتيجة أو None}. None = الذكاء الاصطناعي شاف الرسالة وقرر إنها مش حدث.
    edits: {مفتاح: {"date","time","hide"}} تعديلاتك اليدوية. done: مفاتيح اللي خلّصتها. manual: مواعيد ضفتها بإيدك."""
    trusted, ai = trusted or set(), ai or {}
    courses = DEFAULT_COURSES if courses is None else courses
    edits, done, manual = edits or {}, set(done or []), manual or []
    tagged, announcements, events, undated, files = [], [], [], [], []
    by_key: dict[str, Event] = {}
    ai_used = 0
    for m in messages:
        tags = tag_message(m.text)
        mk = media_kind(m.text)
        if mk == "document":
            tags = ["file"]  # اسم ملف مش حدث («lecture 6.pdf»)
        r = ai.get(m.key) if m.key in ai else False
        if not tags and not r:
            continue
        score = sum({"announcement": 2, "exam": 3, "deadline": 3, "schedule": 1, "file": 0}[t] for t in tags)
        if m.sender in trusted:
            score += 3
        is_q = m.text.strip().endswith(("؟", "?")) or m.text.lstrip().lower().startswith("poll:")
        if mk == "document":
            day, all_dates, hedged, moved, times = None, [], False, False, []
        else:
            day, all_dates, hedged, moved = extract_date_info(m.text, m.when.date())
            times = extract_times(m.text)
        t = _pick(normalize(m.text), times) if times else None
        n = normalize(m.text)
        ev = Event(m, _kind(tags), day, t[0] if t else None, tags, score, all_dates, bool(t and t[1]), hedged,
                   is_q, {w for w, rx in _SUBJ_RE.items() if rx.search(n)}, moved=moved,
                   all_times=[x[1][0] for x in times])
        if m.key in ai:
            ai_used += 1
            if r:
                _apply_ai(ev, r)
                ev.question = False
            else:
                ev.ai_skip = True
        ev.course = detect_course(m.text, courses) if mk != "document" else ""
        if not ev.course and r and r.get("course"):
            ev.course = str(r["course"])[:40]
        tagged.append(ev)
        by_key[m.key] = ev
    # الذكاء الاصطناعي: "الرسالة دي بتغيّر رسالة قديمة"
    for ev in tagged:
        r = ai.get(ev.msg.key) if ev.msg.key in ai else None
        if ev.source == "ai" and r and r.get("status") == "changed" and ev.day:
            for k in r.get("replaces") or []:
                old = by_key.get(k)
                if old is not None and old is not ev and old.status == "active" and old.day != ev.day:
                    old.status, old.note = "replaced", f"اتغيّر لـ {ev.day:%d/%m}"
    _resolve_status(tagged)
    # تعديلاتك اليدوية بتكسب على أي حاجة تانية
    for ev in tagged:
        e = edits.get(ev.msg.key)
        if not e:
            continue
        ev.edited = True
        if e.get("hide"):
            ev.ai_skip = True
            continue
        if "date" in e:
            ev.day = _parse_iso(e["date"])
            ev.all_dates = [ev.day] if ev.day else []
        if "time" in e:
            ev.time = e["time"] or None
            ev.time_guessed, ev.all_times = False, ([ev.time] if ev.time else [])
        ev.hedged, ev.status, ev.note = False, "active", ""
        if ev.day and not any(t in ev.tags for t in ("exam", "deadline", "schedule", "announcement")):
            ev.tags.append("schedule")
    # مواعيد ضفتها بإيدك
    for mn in manual:
        d = _parse_iso(mn.get("date"))
        if not d:
            continue
        t = mn.get("time") or None
        kind = mn.get("kind", "other")
        when = datetime.combine(d, datetime.min.time())
        msg = Message(-1, when, "أنت", mn.get("title", ""), f"m:{mn.get('id', '')}")
        ev = Event(msg, AI_KINDS.get(kind, "عام"), d, t, [_AI_TAG.get(kind, "announcement")], 3, [d],
                   source="manual", course=mn.get("course", ""), all_times=[t] if t else [])
        tagged.append(ev)
    for ev in tagged:
        ev.done = ev.msg.key in done
    for ev in tagged:
        if "announcement" in ev.tags and ev.source != "manual":
            announcements.append(ev)
        if "file" in ev.tags and not ev.question:
            files.append(ev)
        if ev.ai_skip:
            continue
        actionable = not ev.question and any(t in ev.tags for t in ("exam", "deadline", "schedule", "announcement"))
        if actionable and ev.day:
            events.append(ev)
        elif not ev.question and any(t in ev.tags for t in ("exam", "deadline")):
            undated.append(ev)
    events.sort(key=lambda e: (e.day, e.time or "99:99"))
    return Analysis(
        messages, tagged, announcements, events, undated, files,
        Counter(m.sender for m in messages), Counter(m.when.date() for m in messages), ai_used,
        sorted({e.course for e in tagged if e.course}),
    )


def weekday_name(d: date) -> str:
    return _WEEKDAY_NAMES[d.weekday()]


def days_left_label(day: date, today: date) -> str:
    n = (day - today).days
    if n == 0:
        return "النهارده"
    if n == 1:
        return "بكرة"
    if n == 2:
        return "بعد بكرة"
    if n > 2:
        return f"بعد {n} أيام"
    if n == -1:
        return "امبارح"
    return f"من {-n} يوم"


def rule_based_summary(a: Analysis, today: date) -> str:
    if not a.messages:
        return "مفيش رسائل."
    first, last = a.messages[0].when, a.messages[-1].when
    out = [f"المحادثة فيها **{len(a.messages)}** رسالة من {len(a.sender_counts)} شخص، من {first:%d/%m/%Y} إلى {last:%d/%m/%Y}."]
    upcoming = [e for e in a.events if e.day >= today and e.status == "active"]
    if upcoming:
        out.append("\n**الجاي قريب:**")
        for e in upcoming[:5]:
            t = f" الساعة {e.time}" if e.time else ""
            out.append(f"- {weekday_name(e.day)} {e.day:%d/%m} ({days_left_label(e.day, today)}){t} — {e.kind}: {e.title}")
    if a.undated_tasks:
        out.append(f"\n**تسليمات/امتحانات من غير ميعاد واضح:** {len(a.undated_tasks)} (راجعها في تبويب «المهام والمواعيد»)")
    top = sorted(a.announcements, key=lambda e: (-e.score, -e.msg.idx))[:3]
    if top:
        out.append("\n**أهم الإعلانات:**")
        out += [f"- {e.msg.sender}: {e.title}" for e in top]
    return "\n".join(out)


# ───────────────────────── البحث ─────────────────────────

_STOP = {"في", "من", "على", "الى", "عن", "هو", "هي", "ايه", "ازاي", "امتي", "فين", "هل", "ما", "ماذا", "متي", "كام", "يوم"}


def search(messages: list[Message], query: str, limit: int = 30) -> list[tuple[int, Message]]:
    """بحث مرتّب بالأهمية، بيتجاهل التشكيل واختلاف الهمزات والتاء المربوطة."""
    q = normalize(query)
    tokens = [t for t in re.findall(r"\w+", q) if t not in _STOP and len(t) > 1] or re.findall(r"\w+", q)
    if not tokens:
        return []
    scored = []
    for m in messages:
        n = normalize(m.text)
        hits = sum(1 for t in tokens if t in n)
        if not hits:
            continue
        score = hits * 10 + (5 if q in n else 0) + (2 if tag_message(m.text) else 0)
        scored.append((score, m))
    scored.sort(key=lambda x: (-x[0], -x[1].idx))
    return scored[:limit]


# ───────────────────────── التصدير ─────────────────────────

def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def events_to_ics(events: list[Event]) -> str:
    """ملف تقويم .ics تقدر تفتحه في Google Calendar أو تقويم الموبايل."""
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ClassMate AI//AR", "CALSCALE:GREGORIAN"]
    for e in events:
        if not e.day:
            continue
        lines += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@classmate-ai", f"DTSTAMP:{now}",
                  f"SUMMARY:{_ics_escape(e.kind + ': ' + e.title[:80])}",
                  f"DESCRIPTION:{_ics_escape('من ' + e.msg.sender + ' — ' + e.msg.text)}"]
        if e.time:
            h, mi = (int(x) for x in e.time.split(":"))
            start = datetime.combine(e.day, datetime.min.time()).replace(hour=h, minute=mi)
            end = start + timedelta(hours=1)
            lines += [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{e.day:%Y%m%d}", f"DTEND;VALUE=DATE:{e.day + timedelta(days=1):%Y%m%d}"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
