import io
import os
import re
import uuid
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import ai
import theme
import views
from core import (DEFAULT_COURSES, analyze, courses_to_text, events_to_ics, mask_messages, parse_chat,
                  parse_courses_text, rule_based_summary, search)
from llm import PROVIDERS, LLMConfig, LLMError, guess_provider, test_connection
from store import Workspace, delete_space, is_backup, list_spaces, load_space, save_space

st.set_page_config(page_title="ClassMate AI", page_icon="🎓", layout="wide")

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(HERE, "sample_chat.txt")
DATA_DIR = os.environ.get("CLASSMATE_DATA_DIR", os.path.join(HERE, "data"))
NEW = "➕ محادثة جديدة"
KINDS = {"exam": "امتحان/كويز", "deadline": "تسليم", "lecture": "محاضرة/سكشن", "announcement": "إعلان", "other": "أخرى"}
QUICK = ["إيه اللي جاي الأسبوع ده؟", "إيه التسليمات؟", "الامتحانات القريبة", "إيه اللي اتغيّر؟"]

KEY_GUIDES = {
    "groq": """**Groq** (مجاني، من غير كارت، الأسهل)
1. ادخل [console.groq.com](https://console.groq.com) وسجّل بإيميلك أو حساب جوجل.
2. من [API Keys](https://console.groq.com/keys) دوس **Create API Key** وانسخ المفتاح (بيبدأ بـ `gsk_`).
3. الصقه في خانة «مفتاح API» في القايمة الجانبية، وعلّم على الموافقة. التطبيق هيعرف إنه Groq لوحده.
4. للحدود اليومية راجع صفحة Limits في حسابك، لأنها بتتغير.""",
    "openrouter": """**OpenRouter** (موديلات مجانية)
1. سجّل في [openrouter.ai](https://openrouter.ai) وادخل [Keys](https://openrouter.ai/keys) واعمل مفتاح (بيبدأ بـ `sk-or-`).
2. الموديلات اللي آخرها `:free` مجانية بحد يومي صغير. لو اسم الموديل الافتراضي ما اشتغلش، اختار واحد `:free` من موقعهم واكتبه في خانة الموديل.""",
    "mistral": """**Mistral**
1. سجّل في [console.mistral.ai](https://console.mistral.ai) واعمل مفتاح من [API keys](https://console.mistral.ai/api-keys).
2. بعض الموديلات أو الاستخدامات ممكن تطلب وسيلة دفع.""",
    "gemini": """**Google Gemini** (فيه طبقة مجانية)
1. ادخل على [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) بحساب جوجل.
2. وافق على الشروط ودوس **Create API key**.
3. اختار مشروع (أو أنشئ واحد جديد) وانسخ المفتاح.
4. الطبقة المجانية محدودة السرعة، والمحادثة ممكن جوجل تستخدمها لتحسين منتجاتها. للمحادثات الخاصة فكّر في تفعيل الفوترة أو استخدم مزوّد تاني.""",
    "openai": """**OpenAI (ChatGPT)**
1. ادخل على [platform.openai.com](https://platform.openai.com) وسجّل (ده غير موقع chatgpt.com).
2. من **Billing** ضيف وسيلة دفع واشحن رصيد (أقل مبلغ حوالي 5 دولار).
3. من [API keys](https://platform.openai.com/api-keys) دوس **Create new secret key** وانسخه فورًا (مش هيظهر تاني).
4. اشتراك ChatGPT Plus **مش** بيشمل رصيد API، دول حسابين منفصلين.""",
    "anthropic": """**Anthropic (Claude)**
1. ادخل على [console.anthropic.com](https://console.anthropic.com) وسجّل.
2. من **Billing** اشحن رصيد.
3. من [API keys](https://console.anthropic.com/settings/keys) اعمل مفتاح جديد وانسخه.""",
}


# ───────────── أدوات مساعدة ─────────────

def storage_mode() -> str:
    """local = بيحفظ على جهازك تلقائيًا. session = على لينك أونلاين: مفيش حفظ على السيرفر، وبتنزّل نسخة احتياطية."""
    forced = os.environ.get("CLASSMATE_STORAGE", "")
    try:
        forced = forced or str(st.secrets.get("CLASSMATE_STORAGE", ""))
    except Exception:
        pass
    if forced in ("local", "session"):
        return forced
    try:
        host = st.context.headers.get("Host", "")
    except Exception:
        host = ""
    return "local" if host.startswith(("localhost", "127.0.0.1", "[::1]")) else "session"


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1256"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


def read_upload(uploaded) -> tuple[str, str]:
    """بيرجّع (النص, اسم مقترح للمحادثة)."""
    data, name = uploaded.getvalue(), os.path.splitext(uploaded.name)[0]
    if uploaded.name.lower().endswith(".zip"):  # تصدير واتساب "مع الوسائط" بيجي ZIP
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            files = z.namelist()
            pick = ([n for ext in (".txt", ".md", ".json") for n in files if n.lower().endswith(ext)] or [None])[0]
            if not pick:
                raise ValueError("مفيش ملف محادثة (TXT/MD) جوه الـ ZIP.")
            data = z.read(pick)
    text = decode_bytes(data)
    m = re.match(r"#\s*WhatsApp Chat Export:\s*(.+)", text.lstrip("\ufeff \n"))
    if m:
        name = m.group(1).strip()
    return text, re.sub(r"[_]+", " ", name).strip()


def get_secret(names: list[str]) -> str:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
        try:
            if st.secrets.get(n):
                return str(st.secrets.get(n))
        except Exception:
            pass
    return ""


def esc(t: str) -> str:
    return html.escape(t).replace("\n", "<br>")


_KIND_CLASS = {"امتحان/كويز": "exam", "تسليم": "deadline", "إعلان": "ann", "محاضرة/سكشن/موعد": "sched", "ملف/رابط": "file"}
_KIND_ICON = {"exam": "📝", "deadline": "📌", "ann": "📢", "sched": "🕘", "file": "📎"}


def highlight(text: str, query: str = "") -> str:
    out = esc(text)
    for tok in {t for t in re.findall(r"\w+", query) if len(t) > 1}:
        out = re.sub(f"({re.escape(html.escape(tok))})", r"<mark>\1</mark>", out, flags=re.I)
    return out


def card(ev, today=None, show_day=False, query=""):
    kind_cls = _KIND_CLASS.get(ev.kind, "")
    cls = f"card {kind_cls}"
    badges = ""
    dead = ev.status != "active"
    if dead:
        cls += " dead"
        badges += f"<span class='badge gray'>{esc(ev.note or 'قديم')}</span>"
    if show_day and ev.day:
        diff = (ev.day - today).days
        if not dead:
            cls += " past" if diff < 0 else (" soon" if diff <= 2 else "")
        t = f" · {ev.time}{'؟' if ev.time_guessed else ''}" if ev.time else ""
        hot = " hot" if (0 <= diff <= 2 and not dead) else ""
        badges += f"<span class='badge when{hot}'>{days_left_label(ev.day, today)}{t}</span>"
    if ev.source == "ai":
        badges += "<span class='badge'>🤖 AI</span>"
    if ev.needs_review and not dead:
        why = ("الساعة تقدير" if ev.time_guessed else "فيها أكتر من تاريخ" if len(ev.all_dates) > 1
               else "فيها أكتر من وقت" if len(set(ev.all_times)) > 1 else "غير مؤكد")
        badges += f"<span class='badge warn' title='{why}'>⚠️ راجعه ({why})</span>"
    icon = _KIND_ICON.get(kind_cls, "💬")
    st.markdown(
        f"<div class='{cls}'>{badges}<span class='badge'>{icon} {esc(ev.kind)}</span>"
        f"<div class='text'>{highlight(ev.msg.text, query)}</div>"
        + (f"<div class='meta'>🤖 {esc(ev.ai_title)}</div>" if ev.ai_title else "")
        + f"<div class='meta'>👤 {esc(ev.msg.sender)} · {ev.msg.when:%d/%m/%Y %H:%M}</div></div>",
        unsafe_allow_html=True,
    )




def is_mobile() -> bool:
    """تليفون؟ (من نوع المتصفح). التابلت بيتعامل كشاشة كبيرة."""
    try:
        ua = st.context.headers.get("User-Agent", "")
    except Exception:
        return False
    return bool(re.search(r"Mobi|iPhone|iPod", ua))


# ───────────── الحالة: المحادثة الحالية ─────────────

mode = storage_mode()
mobile = is_mobile()
if "pending_choice" in st.session_state:
    st.session_state["space_choice"] = st.session_state.pop("pending_choice")


def persist():
    w = st.session_state.ws_obj
    if mode == "local" and w.name and not w.meta.get("sample"):
        try:
            save_space(DATA_DIR, w)
        except OSError as exc:
            st.warning(f"مقدرتش أحفظ على الجهاز: {exc}")


def process_upload(uploaded) -> bool:
    """بيدمج الملف في المحادثة الحالية. بيرجّع True لو اتغيّر حاجة (والمنادي يعمل rerun)."""
    global ws
    if not uploaded or st.session_state.get("loaded_key") == (uploaded.name, uploaded.size):
        return False
    st.session_state.loaded_key = (uploaded.name, uploaded.size)
    try:
        text, suggested = read_upload(uploaded)
        if is_backup(text):
            other = Workspace.from_json(text)
            added, existing = ws.absorb(other)
            for k, v in other.meta.items():  # الإعدادات والتعديلات من النسخة الاحتياطية
                if k not in ("imports", "sample"):
                    ws.meta.setdefault(k, v)
            ws.name = ws.name or other.name
        else:
            parsed = parse_chat(text)
            if not parsed:
                raise ValueError("مقدرتش أقرأ رسائل من الملف. اتأكد إنه تصدير محادثة واتساب نصي.")
            if not ws.name:
                ws.name = suggested or "chat"
            added, existing = ws.merge(parsed, uploaded.name)
        ws.meta.pop("sample", None)
        st.session_state.flash = (f"اتضاف **{added}** رسالة جديدة، و{existing} كانت موجودة قبل كده."
                                  if existing else f"اتحمّل **{added}** رسالة.")
        persist()
        if mode == "local" and choice == NEW and ws.name:
            st.session_state.pending_choice = ws.name
        return True
    except Exception as exc:
        st.error(f"مقدرتش أقرأ الملف: {exc}")
        return False


def load_sample():
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        sample = parse_chat(f.read())
    w = Workspace("محادثة تجريبية", meta={"sample": True})
    w.merge(sample, "sample")
    st.session_state.ws_obj = w


with st.sidebar:
    st.markdown("## 🎓 ClassMate AI")
    if mode == "local":
        names = list_spaces(DATA_DIR)
        choice = st.selectbox("المحادثات المحفوظة", [NEW] + names, key="space_choice")
    else:
        choice = "session"
    if st.session_state.get("ws_tag") != choice:
        st.session_state.ws_tag = choice
        if mode == "local" and choice != NEW:
            st.session_state.ws_obj = load_space(DATA_DIR, choice) or Workspace(choice)
        else:
            st.session_state.ws_obj = Workspace("" if mode == "local" else "محادثتي")
    ws: Workspace = st.session_state.ws_obj
    if mode == "local" and choice == NEW:
        ws.name = st.text_input("اسم المحادثة (للحفظ)", value=ws.name, placeholder="مثلًا: دفعة 2026").strip()
    elif mode == "session":
        ws.name = st.text_input("اسم المحادثة", value=ws.name).strip() or "محادثتي"

    up_side = st.file_uploader("ارفع تصدير واتساب (TXT/ZIP/MD) أو نسخة احتياطية (JSON)", type=["txt", "zip", "md", "json"],
                               key="up_side")
    if process_upload(up_side):
        st.rerun()
    if st.button("تحميل محادثة تجريبية", use_container_width=True):
        load_sample()
        st.rerun()

mode_note = ("بيتحفظ تلقائيًا على جهازك في مجلد data." if mode == "local" else
             "على اللينك مفيش حفظ على السيرفر. نزّل النسخة الاحتياطية وارفعها المرة الجاية.")

all_msgs = ws.sorted_messages()
mask, cfg, use_ai, today, trusted = True, None, False, date.today(), set()
api_key, agree, ai_note = "", False, ""
courses = ws.meta.get("courses") or DEFAULT_COURSES
saved_theme = ws.meta.get("theme", {})

with st.sidebar:
    with st.expander("🎨 المظهر"):
        keys = list(theme.PALETTES)
        pal = st.selectbox("الثيم", keys, index=keys.index(saved_theme.get("palette", theme.DEFAULT_PALETTE))
                           if saved_theme.get("palette") in keys else 0,
                           format_func=lambda k: theme.PALETTES[k]["name"], key="palette_sel")
        custom = st.toggle("لون مميز مخصص", value=bool(saved_theme.get("accent")), key="accent_on")
        accent = st.color_picker("اللون المميز", value=saved_theme.get("accent") or theme.PALETTES[pal]["accent"],
                                 key="accent_pick") if custom else None
        new_theme = {"palette": pal, "accent": accent}
        if new_theme != saved_theme and all_msgs:
            ws.meta["theme"] = new_theme
            persist()

    if all_msgs:
        st.download_button("💾 نسخة احتياطية (JSON)", ws.to_json().encode("utf-8"),
                           file_name=f"{ws.name or 'classmate'}.classmate.json", mime="application/json",
                           use_container_width=True)
        st.caption(mode_note)
        st.divider()
        mask = st.toggle("إخفاء أرقام الموبايل", value=True)
        view_msgs = mask_messages(all_msgs) if mask else all_msgs
        senders = sorted({m.sender for m in view_msgs})
        guess = [s for s in senders if re.search(r"د\.|دكتور|dr|معيد|م\.|eng|prof|أستاذ|استاذ|leader", s, re.I)]
        saved = [s for s in ws.meta.get("trusted", []) if s in senders]
        trusted = set(st.multiselect("دكاترة / معيدين / قادة (رسائلهم أهم)", senders, default=saved or guess))
        if sorted(trusted) != sorted(ws.meta.get("trusted", [])):
            ws.meta["trusted"] = sorted(trusted)
            persist()
        last_day = all_msgs[-1].when.date()
        default_today = last_day if (date.today() - last_day).days > 30 else date.today()
        today = st.date_input("النهارده (لحساب الأيام المتبقية)", value=default_today)

        with st.expander("📚 المواد الدراسية"):
            st.caption("سطر لكل مادة: «الاسم: كلمة، كلمة». بنستخدمها لتلوين وفلترة المواعيد.")
            txt = st.text_area("المواد", value=courses_to_text(courses), height=200, label_visibility="collapsed")
            c1, c2 = st.columns(2)
            if c1.button("حفظ المواد"):
                parsed_c = parse_courses_text(txt)
                if parsed_c:
                    ws.meta["courses"] = parsed_c
                    persist()
                    st.rerun()
                else:
                    st.error("الصيغة: اسم المادة، نقطتين، كلمات مفصولة بفاصلة.")
            if c2.button("الافتراضي"):
                ws.meta.pop("courses", None)
                persist()
                st.rerun()

        with st.expander("🤖 الذكاء الاصطناعي (اختياري)"):
            prov = st.selectbox("المزوّد", list(PROVIDERS), format_func=lambda k: PROVIDERS[k]["label"], key="ai_provider")
            typed = st.text_input("مفتاح API", type="password", placeholder="الصق المفتاح هنا", key="ai_key").strip()
            guessed = guess_provider(typed) if typed else None
            eff = guessed if guessed in PROVIDERS else prov  # مفتاح Groq في خانة Gemini؟ بنصلّحها لوحدنا
            if guessed and guessed != prov:
                st.info(f"المفتاح شكله مفتاح {PROVIDERS[guessed]['label']}، فهنستخدمه تلقائيًا.")
            P = PROVIDERS[eff]
            model = st.text_input("اسم الموديل (اختياري)", value="", placeholder=P["model"], key=f"ai_model_{eff}")
            api_key = typed or get_secret(P["env"])
            st.caption(f"{P['free']} · [إزاي أجيب المفتاح؟]({P['key_url']})")
            agree = st.checkbox("أوافق إن نص المحادثة يتبعت لـ " + P["label"], key="ai_agree")
            if api_key and agree:
                cfg = LLMConfig(eff, api_key, model)
                ai_note = f"✅ جاهز: {P['label']}"
            elif api_key:
                ai_note = "⚠️ علّم على «أوافق…» عشان يشتغل."
            else:
                ai_note = "❌ لسه مفيش مفتاح."
            st.caption(ai_note)
            use_ai = st.toggle("استخدم نتائج الذكاء الاصطناعي في الجدول", value=True, disabled=not ws.ai)
            st.caption("المفتاح بيفضل في ذاكرة الجلسة بس ومش بيتحفظ في أي ملف.")
        if st.button("🗑️ مسح المحادثة دي", use_container_width=True):
            st.session_state.confirm_delete = True
        if st.session_state.get("confirm_delete"):
            st.warning("هيتمسح كل اللي اتحفظ للمحادثة دي.")
            c1, c2 = st.columns(2)
            if c1.button("أيوه امسح"):
                if mode == "local" and ws.name and choice != NEW:
                    delete_space(DATA_DIR, ws.name)
                st.session_state.pop("ws_tag", None)
                st.session_state.ws_obj = Workspace("")
                st.session_state.confirm_delete = False
                st.session_state.loaded_key = None
                st.rerun()
            if c2.button("إلغاء"):
                st.session_state.confirm_delete = False
                st.rerun()
    st.caption("المحادثة بتتعالج في ذاكرة التطبيق. ما ترفعش محادثات فيها بيانات خاصة على لينك عام.")

st.markdown(theme.build_css(pal, accent), unsafe_allow_html=True)


def H(html_str: str):
    st.markdown(html_str, unsafe_allow_html=True)


# ───────────── الشاشة الأولى (من غير محادثة) ─────────────

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

if not all_msgs:
    H(views.hero(ws.name or "", date.today(), None))
    H(views.tiles([("١", "صدّر", "المحادثة من واتساب: ⋮ ← المزيد ← تصدير المحادثة ← بدون وسائط"),
                   ("٢", "ارفع", "الملف من الشريط الجانبي (TXT أو ZIP أو MD)"),
                   ("٣", "شوف", "المواعيد والأسبوع والمواد، وكل تصدير أحدث بيتضاف للقديم")]))
    up_main = st.file_uploader("📤 ارفع تصدير واتساب (TXT/ZIP/MD) أو نسخة احتياطية (JSON)", type=["txt", "zip", "md", "json"],
                               key="up_main")
    if process_upload(up_main):
        st.rerun()
    if st.button("🚀 جرّب بمحادثة تجريبية", key="sample_main", use_container_width=True, type="primary"):
        load_sample()
        st.rerun()
    st.caption("الإعدادات والثيمات والذكاء الاصطناعي في القايمة الجانبية (☰ أو السهم ‹ فوق).")
    st.stop()


# ───────────── التحليل ─────────────

view = mask_messages(all_msgs) if mask else all_msgs
edits, done_keys, manual = ws.meta.get("edits", {}), set(ws.meta.get("done", [])), ws.meta.get("manual", [])
a = analyze(view, trusted, ai=ws.ai if (use_ai and ws.ai) else None, courses=courses, edits=edits,
            done=done_keys, manual=manual)
known = a.courses
now = datetime.now()
upcoming = [e for e in a.events if e.day >= today and e.status == "active"]
todo = [e for e in upcoming if not e.done]
nxt = todo[0] if todo else None


def toggle_done(key: str, value: bool):
    lst = set(ws.meta.get("done", []))
    (lst.add if value else lst.discard)(key)
    ws.meta["done"] = sorted(lst)
    persist()
    st.rerun()


def _done_box(ev, ctx: str):
    v = st.checkbox("✔ خلّصته", value=ev.done, key=f"done_{ctx}_{ev.msg.key}_{int(ev.done)}")
    if v != ev.done:
        toggle_done(ev.msg.key, v)


def _edit_form(ev, ctx: str):
    k = ev.msg.key
    if ev.source == "manual":
        if st.button("🗑️ احذف الموعد ده", key=f"del_{ctx}_{k}"):
            ws.meta["manual"] = [m for m in manual if f"m:{m['id']}" != k]
            persist()
            st.rerun()
        return
    ver = int(bool(edits.get(k)))
    nd = st.date_input("التاريخ", value=ev.day or today, key=f"ed_d_{ctx}_{k}_{ver}")
    nt = st.text_input("الوقت (مثلًا 14:30)", value=ev.time or "", key=f"ed_t_{ctx}_{k}_{ver}")
    hide = st.checkbox("ده مش موعد (اخفيه)", key=f"ed_h_{ctx}_{k}_{ver}")
    if st.button("حفظ", key=f"ed_s_{ctx}_{k}_{ver}", type="primary"):
        nt = nt.strip()
        if nt and not re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", nt):
            st.error("الوقت لازم يكون بالشكل 14:30")
        else:
            hh, mm = (nt.split(":") if nt else ("", ""))
            ws.meta.setdefault("edits", {})[k] = {"date": nd.isoformat(), "time": f"{int(hh):02d}:{mm}" if nt else "",
                                                  "hide": hide}
            persist()
            st.rerun()
    if edits.get(k) and st.button("إرجاع الأصل", key=f"ed_r_{ctx}_{k}_{ver}"):
        ws.meta["edits"].pop(k, None)
        persist()
        st.rerun()


def controls(ev, ctx: str):
    """✔ خلّصته + ✏️ تعديل. على الموبايل: زرار واحد بياخد عرض الشاشة (من غير أعمدة)."""
    can_done = ev.day is not None or ev.kind in ("تسليم", "امتحان/كويز")
    if mobile:
        with st.popover("⚙️ خيارات الموعد", use_container_width=True):
            if can_done:
                _done_box(ev, ctx)
            _edit_form(ev, ctx)
        return
    c1, c2, _ = st.columns([1, 1, 3])
    if can_done:
        with c1:
            _done_box(ev, ctx)
    with c2.popover("✏️ عدّل"):
        _edit_form(ev, ctx)


def show(ev, ctx: str, with_controls: bool = True, show_day: bool = True, query: str = ""):
    H(views.event_card(ev, today, show_day, query, known, now))
    if with_controls:
        controls(ev, ctx)


# ───────────── الصفحة الرئيسية ─────────────

H(views.hero(ws.name, today, nxt, known, now))
last_imp = (ws.meta.get("imports") or [None])[-1]
if last_imp and last_imp.get("file") not in ("", "sample"):
    st.caption(f"آخر تحديث: {last_imp['at'].replace('T', ' ')} · ملف «{last_imp['file']}» · +{last_imp['added']} رسالة")
H(views.tiles([("💬", len(view), "الرسائل"), ("📅", len(todo), "مواعيد جاية"), ("📢", len(a.announcements), "إعلانات"),
               ("❓", len(a.undated_tasks), "بلا ميعاد"), ("📎", len(a.files), "ملفات"),
               ("✅", sum(1 for e in a.events if e.done), "خلّصتها")]))

(tab_today, tab_week, tab_time, tab_ann, tab_files, tab_chat, tab_ai, tab_export) = st.tabs(
    ["🏠 النهارده", "🗓️ الأسبوع", "📅 المواعيد", "📢 الإعلانات", "📎 الملفات", "💬 المساعد", "🧠 استخراج AI", "⬇️ تصدير"])

with tab_today:
    tomorrow = today + timedelta(days=1)
    now_list = [e for e in upcoming if e.day <= tomorrow]
    st.markdown("### ⚡ النهارده وبكرة")
    if now_list:
        for ev in now_list:
            show(ev, "today")
    else:
        H(views.empty("مفيش مواعيد النهارده ولا بكرة 🎉"))
    later = [e for e in upcoming if e.day > tomorrow][:5]
    if later:
        st.markdown("### ⏭ بعد كده")
        for ev in later:
            show(ev, "later")
    st.markdown("### 📝 ملخص")
    if cfg:
        if st.button("لخّص بالذكاء الاصطناعي"):
            with st.spinner("بلخّص..."):
                try:
                    st.session_state.ai_summary = ai.ask(cfg, view, ai.SUMMARY_TASK)
                except LLMError as exc:
                    st.error(str(exc))
        st.markdown(st.session_state.get("ai_summary") or rule_based_summary(a, today))
    else:
        st.markdown(rule_based_summary(a, today))
        st.caption("ملخص بالقواعد. لتلخيص ذكي فعّل الذكاء الاصطناعي من الشريط الجانبي.")
    left, right = st.columns(2)
    with left:
        st.markdown("### أكتر الناس نشاطًا")
        st.bar_chart(pd.DataFrame(a.sender_counts.most_common(8), columns=["الشخص", "الرسائل"]).set_index("الشخص"))
    with right:
        st.markdown("### الرسائل في اليوم")
        daily = pd.Series(a.per_day).sort_index()
        daily.index = pd.to_datetime(daily.index)
        st.line_chart(daily)

with tab_week:
    pick_day = st.date_input("اختار أي يوم في الأسبوع اللي عايز تشوفه", value=today)
    start = views.week_start_of(pick_day)
    st.caption(f"من {start:%d/%m} لحد {start + timedelta(days=6):%d/%m/%Y}")
    H(views.week_grid(a.events, start, today))
    if not any(start <= e.day <= start + timedelta(days=6) and e.status == "active" for e in a.events):
        st.caption("مفيش مواعيد في الأسبوع ده.")
    if known:
        H(views.legend(dict(Counter(e.course for e in a.events if e.course)), known))

with tab_time:
    with st.expander("➕ أضف موعد بإيدك"):
        with st.form("add_manual", clear_on_submit=True):
            mt = st.text_input("العنوان", placeholder="مثلًا: مراجعة جماعية تفاضل")
            f1, f2, f3 = st.columns(3)
            md = f1.date_input("التاريخ", value=today)
            mh = f2.text_input("الوقت (اختياري)", placeholder="18:00")
            mk = f3.selectbox("النوع", list(KINDS), format_func=lambda k: KINDS[k])
            mc = st.selectbox("المادة", [""] + list(courses), format_func=lambda c: c or "—")
            if st.form_submit_button("إضافة", type="primary"):
                ok_t = not mh.strip() or re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", mh.strip())
                if not mt.strip():
                    st.error("اكتب عنوان.")
                elif not ok_t:
                    st.error("الوقت لازم يكون بالشكل 18:00")
                else:
                    hh = f"{int(mh.strip().split(':')[0]):02d}:{mh.strip().split(':')[1]}" if mh.strip() else ""
                    ws.meta.setdefault("manual", []).append({"id": uuid.uuid4().hex[:8], "title": mt.strip(), "date": md.isoformat(),
                                                             "time": hh, "kind": mk, "course": mc})
                    persist()
                    st.rerun()
    kinds = sorted({e.kind for e in a.events})
    with st.expander("🔍 فلاتر", expanded=not mobile):
        f1, f2 = st.columns(2)
        chosen = f1.multiselect("النوع", kinds, default=kinds)
        course_pick = f2.multiselect("المادة", known, default=known) if known else []
        g1, g2, g3 = st.columns(3)
        only_up = g1.toggle("القادم بس", value=True)
        show_old = g2.toggle("القديم/الملغي", value=False)
        hide_done = g3.toggle("إخفاء اللي خلّصته", value=False)
    shown = [e for e in a.events if e.kind in chosen and (e.day >= today or not only_up)
             and (show_old or e.status == "active") and not (hide_done and e.done)
             and (not known or not e.course or e.course in course_pick)]
    st.caption("⚠️ = راجع الميعاد (الساعة تقدير، أو فيها أكتر من تاريخ/وقت). ✏️ عدّل بيصلّح أي ميعاد وبيتحفظ.")
    if known:
        H(views.legend(dict(Counter(e.course for e in a.events if e.course)), known))
    if shown:
        per_day = Counter(e.day for e in shown)
        last_d = None
        for ev in shown[:80]:
            if ev.day != last_d:
                last_d = ev.day
                H(views.day_header(ev.day, today, per_day[ev.day]))
            show(ev, "time")
        if len(shown) > 80:
            st.caption(f"ظاهر أول 80 موعد من {len(shown)}. استخدم الفلاتر.")
    else:
        H(views.empty("مفيش مواعيد مطابقة للفلاتر."))
    if a.undated_tasks:
        with st.expander(f"تسليمات وامتحانات من غير ميعاد واضح ({len(a.undated_tasks)}) — حدّد ميعادها من ✏️ عدّل"):
            for ev in reversed(a.undated_tasks):
                show(ev, "undated", show_day=False)

with tab_ann:
    ann = sorted([e for e in a.announcements if e.source != "manual"], key=lambda e: (-e.score, -e.msg.idx))
    st.caption("مترتبة بالأهمية: رسائل الدكاترة والقادة والتغييرات والتأجيلات أولًا.")
    for ev in ann[:60]:
        show(ev, "ann", with_controls=False, show_day=False)
    if not ann:
        H(views.empty("مفيش إعلانات واضحة."))

with tab_files:
    for ev in list(reversed(a.files))[:80]:
        H(views.event_card(ev, today, False, "", known, now))
        for link in re.findall(r"https?://\S+", ev.msg.text):
            st.markdown(f"🔗 [{link[:70]}]({link})")
    if not a.files:
        H(views.empty("مفيش ملفات أو روابط."))
    st.caption("تصدير واتساب النصي بيجيب أسماء الملفات والروابط بس، مش الملفات نفسها.")

with tab_chat:
    st.markdown("### 💬 اسأل المساعد")
    st.caption("بيجاوب من جدولك ومحادثتك." + (" (ذكاء اصطناعي)" if cfg else " (مساعد محلي بدون إنترنت. فعّل الـ AI لإجابات أذكى.)"))
    hist = st.session_state.setdefault("chat_hist", [])
    if mobile:
        pick_q = st.selectbox("أسئلة سريعة", [""] + QUICK, format_func=lambda x: x or "اختار سؤال جاهز…", key="quick_pick")
        if pick_q and pick_q != st.session_state.get("quick_done"):
            st.session_state.quick_done = pick_q
            st.session_state.quick_q = pick_q
        elif not pick_q:
            st.session_state.quick_done = None
    else:
        qcols = st.columns(len(QUICK))
        for i, label in enumerate(QUICK):
            if qcols[i].button(label, key=f"quick_{i}", use_container_width=True):
                st.session_state.quick_q = label
                st.rerun()
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    q = st.session_state.pop("quick_q", None) or st.chat_input("اسأل عن المواعيد أو الإعلانات أو أي حاجة في المحادثة...")
    if q:
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("بدوّر..."):
                try:
                    answer = ai.chat(cfg, view, a, today, hist, q) if cfg else ai.local_answer(q, a, view, today)
                except LLMError as exc:
                    answer = f"⚠️ {exc}\n\n" + ai.local_answer(q, a, view, today)
            st.markdown(answer)
        hist += [{"role": "user", "content": q}, {"role": "assistant", "content": answer}]
    if hist and st.button("مسح المحادثة مع المساعد"):
        st.session_state.chat_hist = []
        st.rerun()
    with st.expander("🔎 بحث في نص الرسائل"):
        sq = st.text_input("اكتب كلمة", key="search_q")
        if sq:
            hits = search(view, sq)
            st.write(f"نتائج البحث: {len(hits)}")
            for _, m in hits:
                H(views.message_card(m.text, m.sender, m.when, sq))

with tab_ai:
    st.markdown("### 🧠 استخراج المواعيد بالذكاء الاصطناعي")
    st.write("القواعد بتشتغل دايمًا. الذكاء الاصطناعي بيقرا كل رسالة بسياقها ويفهم الجمل المعقدة والعامية والتغييرات، "
             "ونتيجته بتحل محل القواعد للرسالة دي. اللي اتحلل مرة بيتحفظ، فلما ترفع تصدير أحدث بيتحلل الجديد بس.")
    done_n = sum(1 for m in view if m.key in ws.ai)
    pend = ai.pending_indices(view, ws.ai)
    chars = sum(min(len(view[i].text), ai.MAX_MSG_CHARS) + 60 for i in pend)
    H(views.tiles([("💬", len(view), "الرسائل"), ("🤖", done_n, "اتحللت بالـ AI"), ("⏳", len(pend), "لسه")]))
    if not cfg:
        st.warning((ai_note or "❌ لسه مفيش مفتاح.") +
                   " افتح القايمة الجانبية (☰ أو السهم ‹ فوق) ← 🤖 الذكاء الاصطناعي، والصق المفتاح وعلّم على الموافقة. ولو معندكش مفتاح الخطوات تحت.")
    else:
        if st.button("🔌 اختبر الاتصال بالمفتاح"):
            with st.spinner("بجرّب..."):
                ok_conn, conn_msg = test_connection(cfg)
            (st.success if ok_conn else st.error)(conn_msg)
    if not cfg:
        pass
    elif not pend:
        st.success("كل الرسائل اتحللت. لما ترفع تصدير أحدث هتظهر الرسائل الجديدة هنا.")
    else:
        st.caption(f"هيتبعت حوالي {chars:,} حرف لـ {PROVIDERS[cfg.provider]['label']} (الموديل: {cfg.model_name}). "
                   "التكلفة غالبًا بسيطة، وراجع أسعار المزوّد.")
        limit = st.slider("أقصى عدد رسائل في المرة", 50, 600, min(300, max(50, len(pend))), step=50)
        if st.button("▶️ حلّل الرسائل الجديدة", type="primary"):
            bar = st.progress(0.0, text=f"بتصل بـ {PROVIDERS[cfg.provider]['label']}… (الحد الأقصى دقيقة ونص لكل دفعة)")
            results, errors = ai.extract_events(
                cfg, view, pend[:limit],
                on_progress=lambda i, n: bar.progress(i / n, text=f"خلصت دفعة {i} من {n}"),
                on_start=lambda i, n: bar.progress((i - 1) / n, text=f"بحلّل دفعة {i} من {n}… (ممكن ياخد لحد دقيقة)"))
            ws.ai.update(results)
            persist()
            if results:
                st.session_state.flash = f"اتحلل {len(results)} رسالة، ولقيت {sum(1 for v in results.values() if v)} حدث."
            if errors:
                st.session_state.ai_errors = errors
            st.rerun()
    for err in st.session_state.pop("ai_errors", []):
        st.error(err)
    if ws.ai and st.button("إعادة تحليل كل الرسائل من الأول"):
        ws.ai.clear()
        persist()
        st.rerun()
    st.markdown("### 🔑 إزاي أجيب مفتاح API؟")
    st.caption("المفتاح (API key) مختلف عن حسابك العادي في ChatGPT أو Gemini. اختار مزوّد واحد بس:")
    for k, guide in KEY_GUIDES.items():
        with st.expander(PROVIDERS[k]["label"]):
            st.markdown(guide)

with tab_export:
    st.markdown("### 📆 تقويم")
    st.write("نزّل المواعيد الجاية كملف `.ics` وافتحه في Google Calendar أو تقويم الموبايل.")
    st.download_button("تحميل التقويم (.ics)", events_to_ics(todo).encode("utf-8"),
                       file_name="classmate.ics", mime="text/calendar", disabled=not todo)
    st.markdown("### 📊 جدول بيانات")
    df = pd.DataFrame([{
        "النوع": e.kind, "المادة": e.course, "الموعد": e.day.isoformat() if e.day else "", "الوقت": e.time or "",
        "الحالة": {"active": "نشط", "replaced": "اتغيّر", "cancelled": "اتلغى"}[e.status], "خلّصته": "✔" if e.done else "",
        "المصدر": {"ai": "AI", "manual": "يدوي"}.get(e.source, "قواعد"), "راجعه": "⚠️" if e.needs_review else "",
        "المرسل": e.msg.sender, "تاريخ الرسالة": f"{e.msg.when:%Y-%m-%d %H:%M}" if e.msg.idx >= 0 else "", "النص": e.msg.text,
    } for e in a.tagged])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("تحميل CSV (يفتح في Excel)", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="classmate.csv", mime="text/csv")
