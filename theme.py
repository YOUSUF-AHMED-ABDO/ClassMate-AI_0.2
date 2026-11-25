"""نظام الألوان: كل الألوان في مكان واحد. غيّر لوحة أو أضف واحدة هنا بس."""
from __future__ import annotations

# كل لوحة: bg/bg2 خلفية، surface أسطح شفافة، accent/accent2 لونين التمييز
PALETTES = {
    "midnight": {"name": "منتصف الليل", "bg": "#080d1c", "bg2": "#101a36", "panel": "#0f172c",
                 "text": "#eaf0ff", "muted": "#8e9bb8", "accent": "#6ea8ff", "accent2": "#9b87ff"},
    "ocean":    {"name": "المحيط", "bg": "#05131a", "bg2": "#0a2832", "panel": "#0a1d25",
                 "text": "#e6fbff", "muted": "#8bb0b8", "accent": "#2dd4bf", "accent2": "#38bdf8"},
    "emerald":  {"name": "الزمرد", "bg": "#06130d", "bg2": "#0c2a1b", "panel": "#0a1d14",
                 "text": "#e9fff3", "muted": "#8fb5a0", "accent": "#34d399", "accent2": "#a3e635"},
    "sunset":   {"name": "الغروب", "bg": "#150a12", "bg2": "#2a1220", "panel": "#1d1019",
                 "text": "#fff0ea", "muted": "#b99a98", "accent": "#fb923c", "accent2": "#f472b6"},
    "violet":   {"name": "البنفسج", "bg": "#0e0920", "bg2": "#211545", "panel": "#171031",
                 "text": "#f3edff", "muted": "#a89cc8", "accent": "#a78bfa", "accent2": "#f0abfc"},
}
DEFAULT_PALETTE = "midnight"

KIND = {"exam": "#f87171", "deadline": "#fb923c", "ann": "#facc15", "sched": "#60a5fa", "file": "#4ade80"}
COURSE_COLORS = ["#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#fb7185", "#2dd4bf", "#f97316", "#84cc16", "#22d3ee"]


def rgba(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def course_color(name: str, known: list[str] | None = None) -> str:
    """لون ثابت لكل مادة (حسب ترتيبها لو معروف، وإلا حسب الاسم)."""
    if known and name in known:
        return COURSE_COLORS[known.index(name) % len(COURSE_COLORS)]
    return COURSE_COLORS[sum(map(ord, name)) % len(COURSE_COLORS)]


def build_css(key: str = DEFAULT_PALETTE, accent: str | None = None) -> str:
    p = dict(PALETTES.get(key, PALETTES[DEFAULT_PALETTE]))
    if accent:
        p["accent"] = accent
    A, A2 = p["accent"], p["accent2"]
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
:root {{
  --bg:{p['bg']}; --bg2:{p['bg2']}; --panel:{p['panel']}; --text:{p['text']}; --muted:{p['muted']};
  --accent:{A}; --accent2:{A2};
  --surface:rgba(255,255,255,.045); --surface2:rgba(255,255,255,.075); --border:rgba(255,255,255,.10);
  --exam:{KIND['exam']}; --deadline:{KIND['deadline']}; --ann:{KIND['ann']}; --sched:{KIND['sched']}; --file:{KIND['file']};
}}
html, body, .stApp, [data-testid="stSidebar"], button, input, textarea {{font-family:'Cairo','Segoe UI',Tahoma,sans-serif !important}}
.stApp {{color:var(--text);
  background:radial-gradient(900px 520px at 92% -8%, {rgba(A, .20)}, transparent 62%),
             radial-gradient(760px 460px at -6% 8%, {rgba(A2, .14)}, transparent 58%), var(--bg)}}
[data-testid="stHeader"] {{background:transparent}}
#MainMenu, footer {{visibility:hidden}}
/* الاتجاه من اليمين لليسار على المحتوى بس، مش على هيكل Streamlit: عشان القايمة الجانبية تتخبّى صح على الموبايل */
[data-testid="stSidebar"] {{background:linear-gradient(180deg,var(--panel),var(--bg)); border-right:1px solid var(--border)}}
[data-testid="stSidebar"][aria-expanded="false"] {{visibility:hidden}}
[data-testid="stSidebarContent"], [data-testid="stSidebarUserContent"], .block-container {{direction:rtl; text-align:right}}
.block-container {{max-width:1180px; padding-top:1.4rem}}
h1,h2,h3 {{letter-spacing:0}}

/* عناصر Streamlit */
.stTabs [data-baseweb="tab-list"] {{gap:4px; border-bottom:1px solid var(--border); flex-wrap:wrap}}
.stTabs [data-baseweb="tab"] {{border-radius:12px 12px 0 0; padding:8px 14px; color:var(--muted); font-weight:700}}
.stTabs [aria-selected="true"] {{color:var(--text); background:{rgba(A, .13)}}}
.stTabs [data-baseweb="tab-highlight"] {{background:var(--accent); height:3px}}
.stButton > button, .stDownloadButton > button {{border-radius:12px; border:1px solid var(--border); background:var(--surface); color:var(--text); font-weight:600}}
.stButton > button:hover, .stDownloadButton > button:hover {{border-color:var(--accent); color:var(--text); background:{rgba(A, .12)}}}
.stButton > button[kind="primary"] {{background:linear-gradient(135deg,{A},{A2}); border:0; color:#0b1020; font-weight:800}}
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"], textarea {{background:var(--surface) !important; border-radius:12px !important; border-color:var(--border) !important}}
[data-testid="stExpander"] {{border:1px solid var(--border); border-radius:16px; background:var(--surface)}}
[data-testid="stMetric"] {{background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:12px 16px}}
[data-testid="stChatMessage"] {{background:var(--surface); border:1px solid var(--border); border-radius:16px}}

/* الهيرو */
.cm-hero {{display:grid; grid-template-columns:1.05fr 1fr; gap:16px; margin-bottom:16px}}
.cm-greet {{padding:26px 28px; border-radius:24px; border:1px solid {rgba(A, .35)};
  background:linear-gradient(135deg,{rgba(A, .22)},{rgba(A2, .10)} 60%,transparent)}}
.cm-greet h1 {{margin:0 0 4px; font-size:2.05rem; font-weight:800}}
.cm-greet .cm-sub {{color:var(--muted); margin:0 0 14px}}
.cm-date {{display:inline-block; padding:5px 14px; border-radius:999px; background:var(--surface2); border:1px solid var(--border); font-weight:700; font-size:.92rem}}
.cm-next {{padding:22px 26px; border-radius:24px; background:var(--surface); border:1px solid var(--border); position:relative; overflow:hidden}}
.cm-next::before {{content:""; position:absolute; inset:0 0 auto 0; height:4px; background:linear-gradient(90deg,{A},{A2})}}
.cm-next .cm-lbl {{color:var(--muted); font-size:.85rem; font-weight:700}}
.cm-eta {{font-size:2.5rem; font-weight:800; line-height:1.25; margin:2px 0 6px;
  background:linear-gradient(135deg,{A},{A2}); -webkit-background-clip:text; background-clip:text; color:transparent}}
.cm-next .cm-nt {{font-size:1.08rem; font-weight:700; margin-bottom:10px; line-height:1.7}}

/* بطاقات الأرقام */
.cm-tiles {{display:grid; grid-template-columns:repeat(auto-fit,minmax(135px,1fr)); gap:12px; margin:6px 0 16px}}
.cm-tile {{padding:14px 16px; border-radius:18px; background:var(--surface); border:1px solid var(--border)}}
.cm-tile .n {{font-size:1.9rem; font-weight:800; line-height:1.2}}
.cm-tile .l {{color:var(--muted); font-size:.85rem; font-weight:600}}
.cm-tile .i {{font-size:1.15rem}}

/* كارت الحدث */
.cm-card {{--c:#64748b; padding:14px 18px; margin-bottom:10px; border-radius:18px; background:var(--surface);
  border:1px solid var(--border); border-inline-start:5px solid var(--c); transition:transform .12s, box-shadow .12s, background .12s}}
.cm-card:hover {{transform:translateY(-2px); background:var(--surface2); box-shadow:0 8px 22px rgba(0,0,0,.32)}}
.cm-card.exam {{--c:var(--exam)}} .cm-card.deadline {{--c:var(--deadline)}} .cm-card.ann {{--c:var(--ann)}}
.cm-card.sched {{--c:var(--sched)}} .cm-card.file {{--c:var(--file)}}
.cm-card.soon {{box-shadow:0 0 0 1px {rgba(A, .45)}, 0 8px 24px {rgba(A, .14)}}}
.cm-card.past {{opacity:.5}}
.cm-card.dead {{opacity:.5}} .cm-card.dead .cm-body, .cm-card.dead .cm-title {{text-decoration:line-through}}
.cm-card.done {{opacity:.55}} .cm-card.done .cm-title, .cm-card.done .cm-body {{text-decoration:line-through}}
.cm-row {{display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px}}
.cm-chip {{display:inline-flex; align-items:center; gap:5px; padding:2px 11px; border-radius:999px; font-size:.78rem; font-weight:700;
  background:var(--surface2); border:1px solid var(--border); white-space:nowrap}}
.cm-chip.when {{background:{rgba(A, .20)}; border-color:{rgba(A, .45)}}}
.cm-chip.hot {{background:rgba(248,113,113,.2); border-color:rgba(248,113,113,.5)}}
.cm-chip.warn {{background:rgba(250,204,21,.16); border-color:rgba(250,204,21,.45); color:#fde68a}}
.cm-chip.ok {{background:rgba(74,222,128,.16); border-color:rgba(74,222,128,.45); color:#bbf7d0}}
.cm-chip.course i {{width:9px; height:9px; border-radius:50%; background:var(--cc,#888); display:inline-block}}
.cm-title {{font-weight:800; font-size:1.08rem; margin:2px 0 4px; line-height:1.6}}
.cm-body {{line-height:1.85; font-size:1rem}}
.cm-card .cm-sm {{color:var(--muted); font-size:.9rem; line-height:1.8}}
.cm-meta {{color:var(--muted); font-size:.8rem; margin-top:8px}}
.cm-card details summary {{cursor:pointer; color:var(--accent); font-weight:700; font-size:.85rem}}
.cm-day {{display:flex; align-items:center; gap:12px; margin:22px 0 10px; font-weight:800; font-size:1.1rem}}
.cm-day::after {{content:""; flex:1; height:1px; background:var(--border)}}
.cm-day .cnt {{color:var(--muted); font-size:.82rem; font-weight:600}}
.cm-legend {{display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 14px}}
.cm-empty {{padding:26px; text-align:center; color:var(--muted); border:1px dashed var(--border); border-radius:18px}}

/* الأسبوع */
.cm-weekwrap {{overflow-x:auto; padding-bottom:6px}}
.cm-week {{display:grid; grid-template-columns:repeat(7,minmax(128px,1fr)); gap:10px; min-width:920px}}
.cm-col {{border-radius:18px; background:var(--surface); border:1px solid var(--border); padding:10px; min-height:190px}}
.cm-col.today {{border-color:{rgba(A, .75)}; background:{rgba(A, .09)}}}
.cm-col .h {{display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px}}
.cm-col .h b {{font-size:.95rem}} .cm-col .h span {{color:var(--muted); font-size:.8rem}}
.cm-pill {{--c:#64748b; padding:6px 9px; margin-bottom:6px; border-radius:11px; font-size:.78rem; line-height:1.5;
  background:{rgba('#ffffff', .05)}; border-inline-start:3px solid var(--c)}}
.cm-pill.exam {{--c:var(--exam)}} .cm-pill.deadline {{--c:var(--deadline)}} .cm-pill.ann {{--c:var(--ann)}} .cm-pill.sched {{--c:var(--sched)}}
.cm-pill b {{display:block; color:var(--text)}} .cm-pill span {{color:var(--muted)}}
.cm-pill.done {{opacity:.45; text-decoration:line-through}}
.cm-more {{color:var(--muted); font-size:.75rem; text-align:center}}
mark {{background:#facc15; color:#111; border-radius:4px; padding:0 3px}}
/* منع أي خروج عن عرض الشاشة */
html, body, .stApp {{overflow-x:hidden}}
.cm-card, .cm-title, .cm-body, .cm-sm, .cm-pill, .cm-nt, .cm-chip {{overflow-wrap:anywhere; word-break:break-word}}
.cm-chip {{white-space:normal}}
a {{overflow-wrap:anywhere}}

/* تابلت وموبايل */
@media (max-width:820px) {{
  .cm-hero {{grid-template-columns:1fr}}
  .cm-next {{order:-1}}
  .block-container {{padding:.8rem .7rem 4rem}}
}}
@media (max-width:640px) {{
  .cm-greet {{padding:16px 18px; border-radius:20px}}
  .cm-greet h1 {{font-size:1.5rem}}
  .cm-greet .cm-sub {{margin-bottom:8px}}
  .cm-next {{padding:16px 18px; border-radius:20px}}
  .cm-eta {{font-size:2rem}}
  .cm-next .cm-nt {{font-size:1rem}}
  .cm-tiles {{grid-template-columns:repeat(3,1fr); gap:8px}}
  .cm-tile {{padding:10px 10px; border-radius:14px}}
  .cm-tile .n {{font-size:1.35rem}} .cm-tile .l {{font-size:.72rem}} .cm-tile .i {{font-size:1rem}}
  .cm-card {{padding:12px 14px; border-radius:16px}}
  .cm-card:hover {{transform:none}}
  .cm-body {{font-size:.98rem; line-height:1.8}}
  .cm-title {{font-size:1rem}}
  .cm-chip {{font-size:.74rem; padding:2px 9px}}
  .cm-day {{font-size:1rem; margin:16px 0 8px}}
  /* الأسبوع: أيام فوق بعض بدل 7 أعمدة، والأيام الفاضية مخفية */
  .cm-weekwrap {{overflow:visible}}
  .cm-week {{grid-template-columns:1fr; min-width:0; gap:8px}}
  .cm-col {{min-height:0; padding:10px 12px}}
  .cm-col.empty {{display:none}}
  .cm-pill {{font-size:.82rem}}
  /* التابات: شريط بيتسحب أفقيًا بدل ما يتلف سطور */
  .stTabs [data-baseweb="tab-list"] {{flex-wrap:nowrap; overflow-x:auto; scrollbar-width:none}}
  .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {{display:none}}
  .stTabs [data-baseweb="tab"] {{padding:8px 11px; white-space:nowrap; flex:0 0 auto}}
  /* أهداف لمس مريحة */
  .stButton > button, .stDownloadButton > button {{min-height:46px}}
  .stCheckbox label, .stToggle label {{min-height:40px}}
  [data-testid="stMetric"] {{padding:8px 10px}}
  [data-baseweb="input"] input, textarea {{font-size:16px !important}}  /* يمنع زوم iOS */
  h3 {{font-size:1.2rem !important}}
}}
</style>
"""


def streamlit_config(key: str = DEFAULT_PALETTE) -> str:
    """محتوى .streamlit/config.toml عشان عناصر Streamlit نفسها تتماشى مع اللوحة."""
    p = PALETTES.get(key, PALETTES[DEFAULT_PALETTE])
    return (f'[theme]\nbase = "dark"\nprimaryColor = "{p["accent"]}"\nbackgroundColor = "{p["bg"]}"\n'
            f'secondaryBackgroundColor = "{p["panel"]}"\ntextColor = "{p["text"]}"\nfont = "sans serif"\n')
