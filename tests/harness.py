"""تشغيل app.py كامل بنسخة مقلّدة من Streamlit (من غير متصفح) عشان نمسك أي خطأ تشغيل.
python tests/harness.py"""
import os, re, runpy, sys, tempfile, types, json
from datetime import date, datetime
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class StopApp(BaseException): ...   # زي Streamlit: مش Exception عادي
class RerunApp(BaseException): ...


class SS(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)
    def __setattr__(self, k, v): self[k] = v


class CM:
    """context manager + أي دالة تتطلب عليه ترجع Mock (للأعمدة/التابات)."""
    def __init__(self, st): self.st = st
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name):
        return getattr(self.st, name)


def make_st(state):
    st = types.ModuleType("streamlit")
    st.session_state = state
    st.log = {"markdown": [], "errors": [], "success": [], "warnings": [], "captions": [], "buttons_seen": [], "dataframes": 0,
              "downloads": []}
    H = state["_hooks"]
    cm = lambda *a, **k: CM(st)

    def key_or(label, key): return key or label

    def md(body, *a, **k): st.log["markdown"].append(str(body))
    def caption(body, *a, **k): st.log["captions"].append(str(body))
    st.markdown, st.caption, st.write = md, caption, md
    st.header = st.subheader = st.title = md
    st.info = md
    st.error = lambda b, *a, **k: st.log["errors"].append(str(b))
    st.success = lambda b, *a, **k: st.log["success"].append(str(b))
    st.warning = lambda b, *a, **k: st.log["warnings"].append(str(b))
    st.set_page_config = lambda *a, **k: None
    st.divider = lambda *a, **k: None
    st.metric = st.bar_chart = st.line_chart = lambda *a, **k: None
    st.dataframe = lambda *a, **k: st.log.__setitem__("dataframes", st.log["dataframes"] + 1)

    def stop(): raise StopApp()
    def rerun(): raise RerunApp()
    st.stop, st.rerun = stop, rerun

    def button(label, *a, key=None, **k):
        st.log["buttons_seen"].append(label)
        kk = key_or(label, key)
        return (kk in H["buttons"] or label in H["buttons"]
                or any(str(kk).startswith(p) for p in H.get("button_prefixes", ())))
    st.button = button
    def download_button(label, data, *a, **k):
        st.log["downloads"].append((label, len(data)))
        return False
    st.download_button = download_button
    st.form_submit_button = lambda label, *a, **k: label in H["buttons"]
    def file_uploader(*a, **k): return H.get("upload")
    st.file_uploader = file_uploader

    def selectbox(label, options, index=0, format_func=None, key=None, **k):
        options = list(options)
        if key and key in state: return state[key]
        if key in H["values"]: return H["values"][key]
        return options[index] if options else None
    st.selectbox = selectbox
    def text_input(label, value="", key=None, **k):
        for p, v in H.get("value_prefix", {}).items():
            if key and key.startswith(p): return v
        if key in H["values"]: return H["values"][key]
        return H["values"].get(label, state.get(key, value))
    st.text_input = text_input
    def text_area(label, value="", key=None, **k): return H["values"].get(key, value)
    st.text_area = text_area
    def multiselect(label, options, default=None, **k): return list(default or [])
    st.multiselect = multiselect
    def toggle(label, value=False, key=None, **k): return H["values"].get(key or label, value)
    st.toggle = toggle
    def checkbox(label, value=False, key=None, **k):
        if key and any(key.startswith(p) for p in H["checks"]): return not value
        return H["values"].get(key, value)
    st.checkbox = checkbox
    def date_input(label, value=None, key=None, **k):
        if label.startswith("النهارده") and "today" in H["values"]: return H["values"]["today"]
        return value
    st.date_input = date_input
    st.color_picker = lambda label, value="#000000", **k: H["values"].get("accent_pick", value)
    st.slider = lambda label, mn, mx, value=None, **k: value
    st.chat_input = lambda *a, **k: H.pop("chat", None) if "chat" in H else None
    st.progress = lambda *a, **k: MagicMock()

    def columns(spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [CM(st) for _ in range(n)]
    st.columns = columns
    st.tabs = lambda labels: [CM(st) for _ in labels]
    st.sidebar = CM(st)
    for n in ("expander", "form", "chat_message", "spinner"):
        setattr(st, n, cm)
    st.log["popovers"] = []
    def popover(label, *a, **k):
        st.log["popovers"].append(label)
        return CM(st)
    st.popover = popover
    st.secrets = {}
    st.context = types.SimpleNamespace(headers={"Host": "localhost:8501", "User-Agent": H.get("ua", "Mozilla/5.0 (Windows NT 10.0)")})
    return st


def run_app(state, max_reruns=6):
    """بيشغّل app.py ويكرر لو حصل rerun، زي Streamlit بالظبط."""
    for i in range(max_reruns + 1):
        st = make_st(state)
        sys.modules["streamlit"] = st
        for m in ("app",):
            sys.modules.pop(m, None)
        try:
            runpy.run_path(os.path.join(ROOT, "app.py"), run_name="__main__")
            return st, "done", i
        except StopApp:
            return st, "stopped", i
        except RerunApp:
            state["_hooks"]["buttons"] = set()   # الزر اتداس مرة واحدة
            state["_hooks"]["button_prefixes"] = ()
            state["_hooks"]["checks"] = set()
            state["_hooks"].pop("chat", None)
            state["_hooks"]["upload"] = state["_hooks"].get("upload")
            continue
    raise RuntimeError("rerun loop")


def new_state():
    return SS({"_hooks": {"buttons": set(), "checks": set(), "values": {}, "upload": None}})


class Upload:
    def __init__(self, name, data): self.name, self._d, self.size = name, data, len(data)
    def getvalue(self): return self._d


ok = True
def check(name, cond, extra=""):
    global ok
    print(("✅" if cond else "❌"), name, str(extra)[:110])
    ok &= bool(cond)


def html_of(st): return "\n".join(st.log["markdown"])


if __name__ == "__main__":
    tmp = tempfile.mkdtemp()
    os.environ["CLASSMATE_DATA_DIR"] = tmp
    os.environ.pop("CLASSMATE_STORAGE", None)
    chat_txt = open("/tmp/cs/chat.txt", "rb").read() if os.path.exists("/tmp/cs/chat.txt") else None

    # 1) شاشة البداية
    s = new_state()
    st, how, n = run_app(s)
    check("شاشة البداية بتشتغل وبتقف", how == "stopped" and "cm-hero" in html_of(st) and not st.log["errors"], how)
    check("الثيم اتحقن", "--accent" in html_of(st))

    # 2) المحادثة التجريبية
    s["_hooks"]["buttons"] = {"تحميل محادثة تجريبية"}
    st, how, n = run_app(s)
    h = html_of(st)
    check("التجريبية: الصفحة كاملة", how == "done" and not st.log["errors"], (how, st.log["errors"]))
    check("التجريبية: كروت ومواعيد", "cm-card" in h and "cm-week" in h and "cm-tiles" in h)

    # 3) رفع محادثة حقيقية (محلي: بيتحفظ)
    if chat_txt:
        s = new_state(); s["_hooks"]["upload"] = Upload("Computer_science_level_1__2026_.txt", chat_txt)
        s["_hooks"]["values"]["new_name"] = ""
        st, how, n = run_app(s)
        h = html_of(st)
        check("رفع حقيقي: خلص من غير أخطاء", how == "done" and not st.log["errors"], (how, st.log["errors"]))
        check("اتحفظ على القرص", any(f.endswith(".json") for f in os.listdir(tmp)), os.listdir(tmp))
        check("فيه مواعيد ومواد", "cm-card" in h and "حقوق الإنسان" in h)
        check("أرقام الموبايل متخبية", "81836532" not in h and "عضو ••" in h)
        check("flash للرفع", any("اتحمّل" in x for x in st.log["success"]), st.log["success"])

        # رفع نفس الملف تاني من جلسة جديدة (محادثة محفوظة): مفيش جديد
        s2 = new_state(); s2["_hooks"]["upload"] = Upload("again.txt", chat_txt)
        s2["space_choice"] = os.listdir(tmp)[0][:-5]
        st, how, n = run_app(s2)
        check("رفع نفس الملف: 0 جديد", any("اتضاف **0**" in x for x in st.log["success"]), st.log["success"])

        # 4) تفاعلات: خلّصته + سؤال المساعد + موعد يدوي
        s["_hooks"]["upload"] = None
        s["_hooks"]["checks"] = {"done_today_", "done_later_"}
        st, how, n = run_app(s)
        ws = s["ws_obj"]
        check("تشيك لست اتحفظ", bool(ws.meta.get("done")) or "done_today_" not in "".join(st.log["buttons_seen"]), ws.meta.get("done"))
        s["_hooks"]["buttons"] = {"إيه التسليمات؟"}
        st, how, n = run_app(s)
        check("سؤال سريع للمساعد", how == "done" and not st.log["errors"])
        s["_hooks"]["chat"] = "فين قاعة 17؟"
        st, how, n = run_app(s)
        h = html_of(st)
        check("شات: جواب محلي", len(s.get("chat_hist", [])) >= 2 and "قاعه" in h, len(s.get("chat_hist", [])))

    if chat_txt:
        import ai, core
        s["_hooks"]["values"]["today"] = date(2026, 10, 27)
        s["_hooks"]["buttons"], s["_hooks"]["checks"] = set(), {"done_today_", "done_later_"}
        st, how, n = run_app(s)
        ws = s["ws_obj"]
        check("تشيك لست: اتحفظ", bool(ws.meta.get("done")), ws.meta.get("done"))
        check("تشيك لست: ظهر في الصفحة", "cm-card" in html_of(st) and "خلّصته" in html_of(st))
        s["_hooks"]["checks"] = set()

        # تعديل يدوي لموعد
        s["_hooks"]["button_prefixes"] = ("ed_s_time_",)
        s["_hooks"]["value_prefix"] = {"ed_t_time_": "21:15"}
        st, how, n = run_app(s)
        s["_hooks"]["button_prefixes"] = (); s["_hooks"]["value_prefix"] = {}
        ed = s["ws_obj"].meta.get("edits", {})
        check("تعديل يدوي اتحفظ", bool(ed) and all(v["time"] == "21:15" for v in ed.values()), list(ed.values())[:1])
        st, how, n = run_app(s)
        check("التعديل ظاهر (✏️ معدّل + 21:15)", "✏️ معدّل" in html_of(st) and "21:15" in html_of(st))

        # موعد يدوي
        s["_hooks"]["values"].update({"العنوان": "مراجعة جماعية تفاضل", "الوقت (اختياري)": "18:00"})
        s["_hooks"]["buttons"] = {"إضافة"}
        st, how, n = run_app(s)
        s["_hooks"]["buttons"] = set()
        man = s["ws_obj"].meta.get("manual", [])
        check("موعد يدوي اتضاف", len(man) == 1 and man[0]["time"] == "18:00", man)
        st, how, n = run_app(s)
        check("الموعد اليدوي ظاهر", "✍️ يدوي" in html_of(st) and "مراجعة جماعية" in html_of(st))
        s["_hooks"]["values"].pop("العنوان")

        # الذكاء الاصطناعي: استخراج + شات (بردود وهمية)
        os.environ["GEMINI_API_KEY"] = "AIza-test"
        s["_hooks"]["values"]["ai_provider"] = "gemini"
        s["_hooks"]["values"]["ai_agree"] = True
        def fake(cfg, system, user, json_mode=False, **kw):
            if "<chat>" in user:  # شات
                return "الكويز يوم الأحد (من الـ AI)."
            for line in user.splitlines():
                if "(context)" not in line and "كويز" in line:
                    i = int(line.split()[0][1:])
                    return json.dumps({"events": [{"id": i, "kind": "exam", "title": "كويز تجريبي", "date": "2026-11-02",
                                                    "time": "10:00", "status": "new", "replaces": [], "confidence": 0.9}]})
            return json.dumps({"events": []})
        orig_extract = ai.extract_events
        ai.extract_events = lambda cfg, msgs, todo, on_progress=None, on_start=None: orig_extract(cfg, msgs, todo, on_progress, complete_fn=fake, on_start=on_start)
        ai.complete = fake
        s["_hooks"]["buttons"] = {"▶️ حلّل الرسائل الجديدة"}
        st, how, n = run_app(s)
        s["_hooks"]["buttons"] = set()
        check("استخراج AI: النتايج اتحفظت", len(s["ws_obj"].ai) > 100 and any(s["ws_obj"].ai.values()), len(s["ws_obj"].ai))
        st, how, n = run_app(s)
        check("استخراج AI: ظاهر في الجدول", "🤖 AI" in html_of(st) and "كويز تجريبي" in html_of(st))
        s["_hooks"]["chat"] = "الكويز امتى؟"
        st, how, n = run_app(s)
        check("شات AI", any("من الـ AI" in m["content"] for m in s.get("chat_hist", [])), s.get("chat_hist", [])[-1:])
        os.environ.pop("GEMINI_API_KEY")
        ai.extract_events = orig_extract

        # لو الـ AI رجّع خطأ (مفتاح غلط): الشات يرجع للمحلي
        import llm
        def boom(*a, **k): raise llm.LLMError("المفتاح غلط")
        os.environ["GEMINI_API_KEY"] = "bad"; ai.complete = boom
        s["_hooks"]["chat"] = "إيه التسليمات؟"
        st, how, n = run_app(s)
        check("شات: خطأ AI بيرجع للمحلي", "المفتاح غلط" in s["chat_hist"][-1]["content"] and "التسليمات" in s["chat_hist"][-1]["content"])
        os.environ.pop("GEMINI_API_KEY")

        # باليتات الألوان كلها بتتحقن من غير مشاكل
        for pk in __import__("theme").PALETTES:
            s["_hooks"]["values"]["palette_sel"] = pk
            st, how, n = run_app(s)
            check(f"ثيم {pk}", how == "done" and not st.log["errors"])

    # 5) وضع الجلسة (لينك أونلاين): مفيش حفظ على القرص
    os.environ["CLASSMATE_STORAGE"] = "session"
    tmp2 = tempfile.mkdtemp(); os.environ["CLASSMATE_DATA_DIR"] = tmp2
    s3 = new_state(); s3["_hooks"]["buttons"] = {"تحميل محادثة تجريبية"}
    st, how, n = run_app(s3)
    s3["_hooks"]["upload"] = Upload("x.txt", chat_txt or b"")
    st, how, n = run_app(s3)
    check("وضع الجلسة: مفيش ملفات على القرص", os.listdir(tmp2) == [], os.listdir(tmp2))
    check("وضع الجلسة: نسخة احتياطية متاحة", any("نسخة احتياطية" in d[0] for d in st.log["downloads"]), st.log["downloads"])


    # 6) الموبايل: نفس الرحلة كلها بـ User-Agent بتاع أيفون
    if chat_txt:
        IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
        os.environ["CLASSMATE_STORAGE"] = "local"; os.environ["CLASSMATE_DATA_DIR"] = tempfile.mkdtemp()
        m = new_state(); m["_hooks"]["ua"] = IPHONE
        st, how, n = run_app(m)
        mh = html_of(st)
        check("موبايل: الشاشة الأولى فيها رفع في الصفحة الرئيسية", how == "stopped" and "🚀 جرّب بمحادثة تجريبية" in st.log["buttons_seen"])
        m["_hooks"]["upload"] = Upload("chat.txt", chat_txt)
        st, how, n = run_app(m)
        check("موبايل: الرفع من الصفحة الرئيسية", how == "done" and not st.log["errors"] and "cm-card" in html_of(st), st.log["errors"])
        m["_hooks"]["upload"] = None
        m["_hooks"]["values"]["today"] = date(2026, 10, 27)
        st, how, n = run_app(m)
        seen = st.log["buttons_seen"]
        check("موبايل: زرار الخيارات الواحد بدل الأعمدة", "⚙️ خيارات الموعد" in st.log["popovers"] and "✏️ عدّل" not in st.log["popovers"], set(st.log["popovers"]))
        check("موبايل: مفيش أزرار تنقل الأسبوع القديمة", "◀ الأسبوع اللي فات" not in seen and "الأسبوع الجاي ▶" not in seen, seen[:6])
        check("موبايل: مفيش أزرار الأسئلة السريعة (بقت قايمة)", "إيه التسليمات؟" not in seen)
        m["_hooks"]["values"]["quick_pick"] = "إيه التسليمات؟"
        st, how, n = run_app(m)
        check("موبايل: سؤال سريع من القايمة", any("التسليمات" in x["content"] for x in m.get("chat_hist", [])), m.get("chat_hist", [])[-1:])
        m["_hooks"]["checks"] = {"done_today_", "done_later_", "done_time_"}
        st, how, n = run_app(m)
        check("موبايل: تشيك لست", bool(m["ws_obj"].meta.get("done")))
        m["_hooks"]["button_prefixes"] = ("ed_s_time_",); m["_hooks"]["value_prefix"] = {"ed_t_time_": "20:45"}
        st, how, n = run_app(m)
        check("موبايل: تعديل يدوي", bool(m["ws_obj"].meta.get("edits")))
        st, how, n = run_app(m)
        check("موبايل: الصفحة سليمة بعد التفاعلات", how == "done" and not st.log["errors"])
        MOBILE_STATE = m


    # 7) المفتاح: اكتشاف المزوّد تلقائيًا + رسائل الحالة + زرار الاختبار
    import llm as _llm
    os.environ["CLASSMATE_STORAGE"] = "session"
    for _k in ("GEMINI_API_KEY", "GROQ_API_KEY"): os.environ.pop(_k, None)
    a1 = new_state(); a1["_hooks"]["buttons"] = {"تحميل محادثة تجريبية"}
    run_app(a1)
    st, how, n = run_app(a1)
    check("من غير مفتاح: رسالة واضحة", any("لسه مفيش مفتاح" in c for c in st.log["captions"]), st.log["captions"][-2:])
    a1["_hooks"]["values"]["ai_key"] = "gsk_testkey123"
    a1["_hooks"]["values"]["ai_provider"] = "gemini"        # الخانة على Gemini بس المفتاح بتاع Groq
    st, how, n = run_app(a1)
    check("مفتاح بدون موافقة: يطلب الموافقة", any("أوافق" in c and "⚠️" in c for c in st.log["captions"]), st.log["captions"][-2:])
    a1["_hooks"]["values"]["ai_agree"] = True
    seen = {}
    def fake_complete(cfg, system, user, json_mode=False, **kw):
        seen["provider"], seen["model"] = cfg.provider, cfg.model_name
        return "OK"
    _llm.complete = fake_complete
    a1["_hooks"]["buttons"] = {"🔌 اختبر الاتصال بالمفتاح"}
    st, how, n = run_app(a1)
    check("اكتشاف Groq تلقائيًا من شكل المفتاح", seen.get("provider") == "groq" and seen.get("model") == "openai/gpt-oss-120b", seen)
    check("زرار الاختبار: رسالة نجاح", any("شغّال" in x for x in st.log["success"]), st.log["success"][-1:])
    def bad_complete(cfg, *a, **k): raise _llm.LLMError("المفتاح (API key) غلط (Invalid API Key)")
    _llm.complete = bad_complete
    a1["_hooks"]["buttons"] = {"🔌 اختبر الاتصال بالمفتاح"}
    st, how, n = run_app(a1)
    check("زرار الاختبار: السبب الحقيقي للخطأ بيظهر", any("Invalid API Key" in x for x in st.log["errors"]), st.log["errors"][-1:])

    print("\nALL OK" if ok else "\nFAILED")
    raise SystemExit(0 if ok else 1)
