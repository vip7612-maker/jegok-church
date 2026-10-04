#!/usr/bin/env python3
"""예배 PPT 새 디자인 템플릿 만들기 (2026-10-04 교장님: 구글 슬라이드 느낌을 벗어나 큰 국제 행사처럼, 가운데 정렬).

  A 키노트      → template3   짙은 남색·은은한 푸른 빛·아주 큰 고딕 글자·순서 번호 외곽선
  B 그랜드 스테이지 → template4   따뜻한 검정·금빛 빛줄기·이중 테두리·명조 제목
  C 라이트 에디토리얼 → template5   상아빛 바탕·짙은 초록 띠·큰 활자

template1 의 PPT 틀(장 순서·글자 역할)을 그대로 두고, 배경 그림을 새로 그리고(크롬) 글자 자리·크기·색만 새 디자인으로 바꾼다.
그래서 ppt_tpl.py(주보에서 맡은 분·봉독·설교·소식 채우기)·곡 장·＋ 장 넣기는 그대로 돈다.

  python3 accomp/tpl_design.py A 3     # template3 만들기(있으면 PPT 틀만 다시)
"""
from __future__ import annotations

import copy, io, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = HERE / "templates"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1440, 810            # 글자 좌표계(슬라이드 1440×810) — 배경 그림은 1920×1080
CX = W / 2

# 순서 표지 → 번호·종류
ORDER = {"주일예배": ("cover", ""), "성경암송": ("div", "01"), "찬양과경배": ("div", "02"), "사도신경": ("div", "03"),
         "대표기도": ("div", "04"), "교회소식": ("div", "05"), "봉헌": ("div", "06"), "성경봉독": ("div", "07"),
         "특송": ("div", "08"), "설교": ("div", "09"), "찬양과결단": ("div", "10"), "축도": ("div", "11"), "예배를마칩니다": ("end", "")}
ROMAN = {"01": "I", "02": "II", "03": "III", "04": "IV", "05": "V", "06": "VI", "07": "VII", "08": "VIII", "09": "IX", "10": "X", "11": "XI"}

FONT = ('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;900&family=Cormorant+Garamond:ital,wght@0,500;1,500&display=swap">')
SERIF = "font-family:'Noto Serif KR',serif"
CORM = "font-family:'Cormorant Garamond',serif;font-style:italic"

# ── 디자인별 배경(1920×1080 HTML) ──────────────────────────────────────────
A_BASE = """.s{background:#05070d}
.glow{position:absolute;inset:0;background:radial-gradient(55% 60% at 50% 38%,rgba(56,92,255,.30),transparent 62%),radial-gradient(40% 45% at 85% 95%,rgba(0,190,200,.14),transparent 60%),radial-gradient(35% 40% at 10% 90%,rgba(120,80,255,.12),transparent 60%)}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:120px 120px;mask-image:radial-gradient(70% 65% at 50% 42%,#000,transparent)}
.foot{position:absolute;left:0;right:0;bottom:70px;text-align:center;font:600 22px 'Pretendard Variable';letter-spacing:.42em;color:rgba(255,255,255,.38)}
.num{position:absolute;left:0;right:0;top:40px;text-align:center;font:900 560px/1 'Pretendard Variable';letter-spacing:-.04em;color:transparent;-webkit-text-stroke:2px rgba(143,176,255,.16)}
.bar{position:absolute;left:50%;width:90px;margin-left:-45px;height:4px;border-radius:4px;background:#5b82ff}
.sub{position:absolute;left:0;right:0;text-align:center;font-family:'Pretendard Variable'}"""
B_BASE = """.s{background:#0d0a07}
.rays{position:absolute;inset:0;background:conic-gradient(from 180deg at 50% -12%,transparent 0deg,rgba(255,196,110,.10) 8deg,transparent 16deg,rgba(255,196,110,.07) 26deg,transparent 34deg,rgba(255,196,110,.09) 330deg,transparent 340deg,rgba(255,196,110,.06) 350deg,transparent 360deg)}
.vig{position:absolute;inset:0;background:radial-gradient(70% 80% at 50% 45%,transparent 40%,rgba(0,0,0,.78))}
.frame{position:absolute;inset:52px;border:1.5px solid rgba(214,170,95,.45)}.frame:after{content:'';position:absolute;inset:14px;border:1px solid rgba(214,170,95,.18)}
.foot{position:absolute;left:0;right:0;bottom:92px;text-align:center;font:500 22px 'Pretendard Variable';letter-spacing:.44em;color:rgba(244,234,216,.5)}
.no{position:absolute;left:0;right:0;top:118px;text-align:center;font:500 54px 'Cormorant Garamond';color:#d6aa5f}
.line{position:absolute;left:50%;width:420px;margin-left:-210px;height:1px;background:linear-gradient(90deg,transparent,#d6aa5f,transparent)}
.sub{position:absolute;left:0;right:0;text-align:center}"""
C_BASE = """.s{background:#f4efe6}
.band{position:absolute;left:0;right:0;top:0;height:270px;background:#16352d}
.num{position:absolute;left:96px;top:34px;font:900 210px/1 'Pretendard Variable';color:#e8c47a;letter-spacing:-.05em}
.foot{position:absolute;left:0;right:0;bottom:70px;text-align:center;font:700 22px 'Pretendard Variable';letter-spacing:.4em;color:rgba(20,35,30,.45)}
.bar{position:absolute;left:50%;width:90px;margin-left:-45px;height:6px;background:#e8a33c}
.sub{position:absolute;left:0;right:0;text-align:center;font-family:'Pretendard Variable'}"""

def bg_html(style: str, kind: str, no: str = "") -> str:
    if style == "A":
        css, body = A_BASE, '<div class="glow"></div><div class="grid"></div>'
        if kind == "div": body += f'<div class="num">{no}</div><div class="foot">JEGOK CHURCH · SUNDAY WORSHIP</div>'
        elif kind == "cover":
            body += ('<div class="sub" style="top:560px;font-size:44px;font-weight:300;color:rgba(255,255,255,.78)">Sunday Worship</div>'
                     '<div class="sub" style="top:625px;font-size:28px;color:rgba(255,255,255,.42);letter-spacing:.06em">Воскресное богослужение</div>'
                     '<div class="bar" style="top:700px"></div>')
        elif kind == "end": body += '<div class="foot">JEGOK CHURCH · SUNDAY WORSHIP</div>'
        elif kind == "content": body = '<div class="glow" style="opacity:.55"></div>'
    elif style == "B":
        css, body = B_BASE, '<div class="rays"></div><div class="vig"></div><div class="frame"></div>'
        if kind == "div": body += f'<div class="no">— {ROMAN.get(no, no)} —</div><div class="foot">JEGOK CHURCH · SUNDAY WORSHIP</div>'
        elif kind == "cover":
            body += ('<div class="line" style="top:560px"></div>'
                     '<div class="sub" style="top:588px;font:italic 500 44px \'Cormorant Garamond\';color:#d6aa5f;letter-spacing:.06em">Sunday Worship</div>'
                     '<div class="sub" style="top:650px;font:500 26px \'Pretendard Variable\';color:rgba(244,234,216,.5);letter-spacing:.1em">Воскресное богослужение</div>')
        elif kind == "end": body += '<div class="line" style="top:560px"></div><div class="foot">JEGOK CHURCH</div>'
        elif kind == "content": body = '<div class="rays" style="opacity:.5"></div><div class="vig"></div><div class="frame" style="opacity:.6"></div>'
    else:
        css, body = C_BASE, '<div class="band"></div>'
        if kind == "div": body += f'<div class="num">{no}</div><div class="foot">JEGOK CHURCH · SUNDAY WORSHIP</div>'
        elif kind == "cover":
            body += ('<div class="sub" style="top:600px;font-size:44px;font-weight:300;color:#14231e">Sunday Worship</div>'
                     '<div class="sub" style="top:664px;font-size:28px;color:rgba(20,35,30,.5)">Воскресное богослужение</div>'
                     '<div class="bar" style="top:735px"></div>')
        elif kind == "end": body += '<div class="foot">JEGOK CHURCH</div>'
        elif kind == "content": body = '<div style="position:absolute;inset:0;background:#16352d"></div><div style="position:absolute;inset:40px;border:1px solid rgba(232,196,122,.25);border-radius:6px"></div>'
    return (f'<!doctype html><html><head><meta charset="utf-8">{FONT}<style>*{{margin:0;padding:0;box-sizing:border-box}}'
            f'html,body{{width:1920px;height:1080px;overflow:hidden}}.s{{position:relative;width:1920px;height:1080px;overflow:hidden}}{css}</style></head>'
            f'<body><div class="s">{body}</div></body></html>')


def render(htmls: dict[str, str], out: Path) -> None:
    """{이름: html} → out/<이름>.jpg (1920×1080)."""
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        for name, h in htmls.items():
            f = Path(tmp) / f"{name}.html"; f.write_text(h); png = Path(tmp) / f"{name}.png"
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,1080",
                            "--virtual-time-budget=8000", f"--screenshot={png}", f.as_uri()], capture_output=True, timeout=120)
            Image.open(png).convert("RGB").save(out / f"{name}.jpg", "JPEG", quality=88)


# ── 디자인별 글자 모양 ──────────────────────────────────────────────────────
STYLE = {
    "A": dict(eyebrow=("#8fb0ff", 22, True, "letter-spacing:.32em"), title=("#ffffff", 150, True, "letter-spacing:-.03em"),
              main=("#ffffff", 50, True, ""), small=("#8fb0ff", 34, True, ""), body=("#c9d3ea", 30, False, ""),
              ref="#8fb0ff", cover_title=190, top=168, title_y=205),
    "B": dict(eyebrow=("#d6aa5f", 36, False, CORM + ";letter-spacing:.04em"), title=("#f4ead8", 128, True, SERIF + ";letter-spacing:.06em"),
              main=("#f4ead8", 48, True, SERIF), small=("#d6aa5f", 34, False, ""), body=("#e9dcc4", 30, False, SERIF),
              ref="#d6aa5f", cover_title=170, top=150, title_y=225),
    "C": dict(eyebrow=("#e8c47a", 24, True, "letter-spacing:.32em"), title=("#14231e", 138, True, "letter-spacing:-.04em"),
              main=("#16352d", 50, True, ""), small=("#c47a1e", 34, True, ""), body=("#2d3b36", 30, False, ""),
              ref="#e8c47a", cover_title=180, top=118, title_y=235),
}


def tw(text: str, size: float) -> float:
    w = 0.0
    for ch in text:
        w += size * (0.32 if ch == " " else 0.62 if ord(ch) < 0x1100 else 0.98)
    return w


def item(text: str, y: float, look: tuple, s: float | None = None) -> dict:
    c, size, bold, css = look; size = s or size
    w = min(W - 60, tw(text, size) * 1.15 + 60)
    d = {"x": round(CX - w / 2, 1), "y": round(y, 1), "w": round(w, 1), "h": round(size, 1), "s": float(size), "c": c, "b": bold, "t": text, "a": "c"}
    if css: d["css"] = css
    return d


def restyle(slide: dict, style: str, kind: str, key: str) -> list[dict]:
    st = STYLE[style]; texts = slide["texts"]
    en = next((t for t in texts if t["s"] < 30 and re.search(r"[A-Za-z]", t["t"]) and not re.search(r"[가-힣]", t["t"])), None)
    title = next((t for t in texts if t["s"] >= 100), None)
    main = next((t for t in texts if 40 <= t["s"] < 100 and t["c"] != "#efe6dd"), None)
    small = next((t for t in texts if 20 <= t["s"] < 40 and t["y"] > 520 and t is not en and key in ("설교", "성경봉독")), None)
    rest = [t for t in texts if t not in (en, title, main, small)]
    out = []
    if kind == "cover":        # 제곡교회 / 주일예배 / “주 안에서…” / 날짜
        church = next((t for t in texts if t["t"].strip() == "제곡교회"), None)
        quote = next((t for t in texts if "“" in t["t"] or "”" in t["t"]), None)
        date = next((t for t in texts if re.search(r"\d{4}년", t["t"])), None)
        if style == "B":
            if church: out.append(item("제곡교회", st["top"] - 10, st["eyebrow"], 40))
        else:                                          # 한 줄로(겹치지 않게)
            out.append(item("JEGOK CHURCH · 제곡교회", st["top"] - (20 if style == "A" else 10), st["eyebrow"]))
        out.append(item(title["t"] if title else "주일예배", st["title_y"] - 20, st["title"], st["cover_title"]))
        if quote: out.append(item(quote["t"].strip(), 585 if style == "C" else 560, st["main"], 38))
        if date: out.append(item(date["t"].strip(), 690, st["body"], 24))
        return out
    if kind == "end":
        out.append(item(title["t"] if title else "예배를 마칩니다", 250, st["title"], 112))
        y = 430
        for t in ([main] if main else []) + rest:
            if not t["t"].strip(): continue
            out.append(item(t["t"].strip(), y, st["main"] if t is main or t["s"] >= 40 else st["body"], 40 if t["s"] >= 40 else 30)); y += 56
        return out
    # 순서 표지
    if en: out.append(item(en["t"], st["top"], st["eyebrow"]))
    out.append(item(title["t"] if title else key, st["title_y"], st["title"]))
    y = 430
    if main:
        out.append(item(main["t"], y, st["main"])); y += 80
    body = [t for t in rest if t["t"].strip()]
    bs = 24 if len(body) > 5 else 30 if len(body) > 2 else 32
    step = bs * 1.6
    if body and not main: y = 420 if len(body) <= 5 else 380
    for t in body:
        out.append(item(t["t"].strip(), y, st["body"], bs)); y += step
    if small:
        out.append(item(small["t"], max(y + 10, 540), st["small"], 36 if key == "성경봉독" else 34))
    return out


def build(style: str, n: int) -> Path:
    src = T / "template1"; dst = T / f"template{n}"
    if not dst.exists():
        shutil.copytree(src, dst)
    ppt = dst / "ppt"
    T1 = json.loads((src / "ppt" / "slides.json").read_text())
    for f in ppt.glob("*.jpg"): f.unlink()
    S = copy.deepcopy(T1["slides"])
    htmls: dict[str, str] = {}
    for s in S:
        title = next((t for t in s["texts"] if t["s"] >= 100), None)
        key = re.sub(r"\s", "", title["t"]) if title else ""
        kind, no = ORDER.get(key, ("content", ""))
        if kind == "content":
            name = "k_content"
            if style == "A" or style == "B" or style == "C":
                for t in s["texts"]:                   # 암송·봉독 장 첫 줄(장절)만 강조색
                    if t["s"] >= 62 and t["c"] == "#ffffff": t["c"] = STYLE[style]["ref"]
        else:
            name = f"k_{kind}{no}"
            s["texts"] = restyle(s, style, kind, key)
        htmls.setdefault(name, bg_html(style, kind, no))
        s["img"] = f"{name}.jpg"
        s["plain"] = " ".join(t["t"] for t in s["texts"])
        s["hidden"] = ""
    render(htmls, ppt)
    T2 = {"source": f"tpl_design {style}", "bg": {"verse_bg": "k_content.jpg", "news_bg": "k_content.jpg"}, "slides": S}
    (ppt / "slides.json").write_text(json.dumps(T2, ensure_ascii=False, indent=1))
    return dst


if __name__ == "__main__":
    style, n = sys.argv[1].upper(), int(sys.argv[2])
    print(build(style, n), "배경", len(list((T / f"template{n}" / "ppt").glob("*.jpg"))), "장")
