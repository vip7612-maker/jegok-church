"""악보집 테마 — 예배 PPT 템플릿 디자인에 맞춘 덧입힘 CSS (2026-10-04 교장님: 9/27 악보집도 테마에 맞춰).

data/<날짜>.json 의 "theme" 값으로 고른다(없으면 원래 모양). build.py 가 기본 CSS 뒤에 붙인다.
  keynote — 예배 PPT template3(A 키노트): 표지는 짙은 남색·푸른 빛·아주 큰 글자, 안쪽 쪽은 인쇄를 생각해 흰 바탕에
            짙은 남색 머리·푸른 강조(#5b82ff)·윗선. 악보 그림은 그대로.
"""
from __future__ import annotations

NAVY, BLUE, SKY = "#05070d", "#5b82ff", "#8fb0ff"

KEYNOTE = f"""
/* ── 테마: 키노트 (template3) ── */
.cover{{background:radial-gradient(60% 75% at 72% 30%,rgba(56,92,255,.38),transparent 62%),radial-gradient(45% 55% at 10% 95%,rgba(0,190,200,.18),transparent 60%),{NAVY}}}
.cover::before{{content:'';position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);background-size:14mm 14mm;-webkit-mask-image:radial-gradient(70% 70% at 70% 35%,#000,transparent);mask-image:radial-gradient(70% 70% at 70% 35%,#000,transparent)}}
.cover svg.bg{{opacity:.28;filter:hue-rotate(185deg) saturate(.7)}}
.cover .kick{{color:{SKY};letter-spacing:.45em}}
.cover h1{{font-size:96pt;letter-spacing:-.02em}}
.cover .sub{{color:rgba(255,255,255,.72);font-weight:300}}
.cover .rule{{background:{BLUE}}}
.cover .date{{border-color:{BLUE}}}.cover .date small{{color:{SKY}}}
.cover .ch{{color:rgba(255,255,255,.5)}}
.page:not(:has(.cover))::before{{content:'';position:absolute;left:0;right:0;top:0;height:1.6mm;z-index:4;background:linear-gradient(90deg,{NAVY} 0,#1d3bd1 70%,{SKY})}}
.tag{{background:{NAVY};color:{SKY}}}
.rs-h{{border-bottom-color:{NAVY}}}.rs-h .kick{{color:{BLUE}}}.rs-h h2{{color:{NAVY};letter-spacing:-.01em}}
.rs-h .range{{background:{NAVY};color:#fff}}
.rt th b{{color:{NAVY}}}.rt th.now{{background:{NAVY}}}.rt th.now b{{color:#fff}}.rt td.now{{background:#eef2ff}}
.sup-h b,.notice b{{color:{NAVY}}}
.textpage h2,.creed h2{{color:{NAVY};letter-spacing:-.02em}}
.sm-head{{background:#eef2ff;border-left-color:{BLUE}}}.sm-head b{{color:{NAVY}}}
.sermon-head{{border-bottom-color:{NAVY}}}
.vn{{color:{BLUE}}}
.slot .badge{{background:{NAVY};color:#fff}}.shead .stt{{color:{NAVY}}}
.slot.empty{{border-color:#a5b4fc;color:{BLUE}}}
"""

THEMES = {"keynote": KEYNOTE}


def css(d: dict) -> str:
    return THEMES.get((d or {}).get("theme") or "", "")
