#!/usr/bin/env python3
"""반주자·싱어용 악보 — data/<날짜>.json → out/<날짜>.html (2026-10-03 교장님 지시).

쪽마다 구획(slot)이 있어 말로 고치거나 악보를 주시면 그 자리에 넣는다.
  python3 accomp/build.py 2026-09-27            # 만들기
  python3 accomp/build.py 2026-09-27 --open     # 만들고 열기
  python3 accomp/build.py 2026-10-04 --share    # 게시: …/jegok_worship_20261004 + 모음 …/jegok_worship + 노션 (publish.py)

쪽 종류(type): cover 표지 · roster 섬김표 · recite 암송 · sermon_text 설교본문 · sermon_summary 설교요약
              · creed 사도신경 · scores 악보(왼쪽 L / 오른쪽 R 두 칸)
악보 칸: {"side": "L", "title": "곡 제목", "img": "scores/<날짜>/파일.png"} — img 가 비면 빈 구획으로 보인다.
"""
from __future__ import annotations
import base64, html, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIND = {"cover": "표지", "roster": "섬김표", "recite": "암송", "sermon_text": "설교본문",
        "sermon_summary": "설교요약", "creed": "사도신경", "scores": "악보"}
ROLE_COLOR = {"인도자": "#e5e7eb", "메인KB": "#fde047", "세컨KB": "#fde047", "드럼": "#fde047",
              "단상싱어": "#fdba74", "회중싱어": "#bbf7d0", "방송실": "#67e8f9", "촬영": "#67e8f9", "지원팀": "#e5e7eb"}

CSS = """
@page{size:297mm 210mm;margin:0}
*{box-sizing:border-box}
body{margin:0;background:#d9dce1;font-family:'Pretendard Variable',Pretendard,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;color:#111}
.bar{position:sticky;top:0;z-index:9;display:flex;gap:8px;align-items:center;padding:8px 14px;background:#1f2937;color:#fff;font-size:13px}
.bar b{margin-right:auto}
.bar button{font:inherit;font-weight:700;border:0;border-radius:999px;padding:7px 14px;cursor:pointer;background:#fff;color:#111}
.pages{display:flex;flex-direction:column;align-items:center;gap:14px;padding:16px 0 40px}
.page{width:297mm;height:210mm;background:#fff;position:relative;overflow:hidden;box-shadow:0 4px 18px rgba(0,0,0,.18)}
.tag{position:absolute;top:2mm;right:3mm;z-index:5;font-size:9pt;font-weight:800;color:#fff;background:#2563eb;border-radius:999px;padding:.6mm 2.6mm}
.half{position:absolute;top:0;bottom:0;width:50%}
.half.L{left:0}.half.R{left:50%}
.divider{position:absolute;left:50%;top:2mm;bottom:2mm;border-left:1px solid #9ca3af}
/* 표지 — 새벽빛 그라데이션 + 흐르는 오선 (2026-10-03 새 디자인) */
.cover{position:absolute;inset:0;color:#fff;background:radial-gradient(120% 90% at 82% 8%,#f6c76b33 0,#f6c76b00 45%),linear-gradient(160deg,#0b1430 0%,#172a5e 48%,#2b2f6e 100%)}
.cover svg.bg{position:absolute;inset:0;width:100%;height:100%}
.cover .in{position:absolute;left:24mm;top:30mm;right:24mm;bottom:22mm;display:flex;flex-direction:column}
.cover .kick{font-size:11pt;letter-spacing:.42em;color:#f6c76b;font-weight:700}
.cover h1{margin:7mm 0 0;font-size:76pt;line-height:1;font-weight:900;letter-spacing:.12em}
.cover .sub{margin:7mm 0 0;font-size:24pt;font-weight:500;color:#dbe4ff;letter-spacing:.06em}
.cover .rule{width:34mm;height:1.2mm;border-radius:1mm;background:#f6c76b;margin:10mm 0 0}
.cover .foot{margin-top:auto;display:flex;align-items:flex-end;justify-content:space-between}
.cover .date{font-size:22pt;font-weight:800;letter-spacing:.08em;border:1.2px solid #f6c76b;color:#fff;border-radius:999px;padding:2.6mm 8mm}
.cover .date small{font-size:14pt;font-weight:600;color:#f6c76b;margin-left:3mm;letter-spacing:0}
.cover .ch{font-size:13pt;color:#b9c4e8;letter-spacing:.2em;text-align:right;line-height:1.6}
.cover .ch b{display:block;font-size:17pt;color:#fff;letter-spacing:.3em}
/* 섬김표 — roster.json (2026-10-03 새 디자인) */
.rs{position:absolute;inset:0;padding:8mm 10mm 7mm;display:flex;flex-direction:column}
.rs-h{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #0b1430;padding-bottom:2.5mm}
.rs-h .kick{font-size:8pt;letter-spacing:.35em;color:#b8860b;font-weight:800}
.rs-h h2{margin:1mm 0 0;font-size:24pt;font-weight:900;letter-spacing:.04em;color:#0b1430}
.rs-h .range{font-size:13pt;font-weight:800;color:#0b1430;background:#f6c76b;border-radius:999px;padding:1.2mm 5mm}
.rt{width:100%;border-collapse:separate;border-spacing:0;margin-top:3mm;table-layout:fixed}
.rt th{font-size:12pt;padding:1.6mm 0;color:#475569;text-align:center}
.rt th b{display:block;font-size:15pt;color:#0b1430}
.rt th i{display:block;font-style:normal;font-size:8pt;color:#fff;background:#dc2626;border-radius:999px;width:max-content;margin:.6mm auto 0;padding:.2mm 2.4mm}
.rt th.now{background:#0b1430;border-radius:3mm 3mm 0 0}.rt th.now b{color:#fff}
.rt td{text-align:center;padding:1mm .8mm;border-bottom:1px solid #e5e7eb;vertical-align:middle}
.rt tr.gs td{border-top:2px solid #cbd5e1}
.rt td.grp{color:#fff;font-weight:800;font-size:10pt;letter-spacing:.05em;border-radius:2mm;border-bottom:0;border-right:2mm solid #fff;line-height:1.3}
.rt td.role{font-weight:800;font-size:13pt;text-align:left;padding-left:2.5mm}
.rt td.now{background:#fff7e0}
.nm{display:inline-block;width:16.5mm;text-align:center;font-size:12pt;font-weight:600;border:1px solid #e2e8f0;border-radius:1.6mm;height:7mm;line-height:6.6mm;padding:0;white-space:nowrap;letter-spacing:-.02em}
.nm.empty{visibility:hidden}
.nm.chg{background:#7c3aed;border-color:#7c3aed;color:#fff;font-weight:800}
.nm.wide{width:34.2mm}
.q1{display:flex;justify-content:center}
.rr{display:flex;align-items:center;gap:4mm}.lg{font-size:9pt;color:#64748b;display:flex;align-items:center;gap:1.5mm}.lg .nm{width:auto;padding:0 2mm;height:5.5mm;line-height:5.2mm;font-size:9pt}
.q4{display:grid;grid-template-columns:repeat(2,16.5mm);gap:1mm 1.2mm;justify-content:center}
.none{color:#cbd5e1}
.sup{margin-top:auto;border:1.5px dashed #94a3b8;border-radius:3mm;padding:2.4mm 4mm;display:flex;gap:5mm;align-items:center}
.sup-h b{display:block;font-size:15pt;color:#0b1430}.sup-h span{font-size:8.5pt;color:#64748b}
.sup-n{display:flex;flex-wrap:wrap;gap:1mm 1.2mm}.sup-n .nm{background:#f1f5f9}
/* 글 쪽 */
.textpage{padding:8mm 10mm;height:100%;display:flex;flex-direction:column}
.textpage h2{margin:0 0 4mm;font-size:22pt}
.textpage .body{flex:1;min-height:0;overflow:hidden;line-height:1.45}
.red{color:#dc2626;font-style:normal}
.verses{line-height:1.75}
.sm-head{background:#e8edf8;border-left:2mm solid #1e3a8a;border-radius:2mm;padding:2.6mm 4mm;margin-bottom:4mm;flex:0 0 auto}.sm-head b{display:block;font-size:21pt;color:#0b1430}.sm-head span{font-size:14pt;color:#334155;font-weight:600}
.creed{padding:9mm 14mm}.creed h2{font-size:32pt;margin-bottom:6mm}.creed .body{white-space:nowrap;line-height:1.62;font-weight:600;letter-spacing:-.01em}
.vn{color:#1e3a8a;margin-right:1.5mm}
.sermon-head{display:flex;gap:6mm;align-items:baseline}
.sermon-head{border-bottom:2px solid #1e3a8a;padding-bottom:2mm;margin-bottom:4mm}.sermon-head h2{margin:0;font-size:24pt}.sermon-head .ref{font-size:22pt;font-weight:800}.sermon-head .tt{font-size:22pt;font-weight:800;color:#1e3a8a;margin-left:auto}
.col{position:absolute;top:0;bottom:0;width:50%;padding:7mm 9mm}
.col .body{height:100%;overflow:hidden;line-height:1.5}
/* 악보 칸 */
.slot{position:absolute;inset:2mm;display:flex;flex-direction:column}
.slot img{width:100%;flex:1;min-height:0;object-fit:contain;object-position:top center}
.slot.empty{border:2px dashed #93c5fd;border-radius:3mm;align-items:center;justify-content:center;color:#3b82f6;background:#f8fbff}
.slot.empty b{font-size:16pt}.slot.empty span{font-size:10pt;margin-top:2mm;color:#64748b}
.slot .badge{position:static;align-self:flex-start;flex:0 0 auto;margin-bottom:1.5mm;min-width:11mm;text-align:center;font-size:13pt;font-weight:900;color:#fff;background:#1e3a8a;border-radius:2mm;padding:.8mm 3.5mm}
.slot.empty .badge{position:absolute;left:0;top:0}
.slot .st{position:absolute;left:0;bottom:0;font-size:8pt;color:#fff;background:rgba(37,99,235,.85);padding:.5mm 2mm;border-radius:0 2mm 0 0}
@media print{
  body{background:#fff}.bar,.tag,.slot .st{display:none}
.slot.empty .badge{position:absolute;left:0;top:0}
.slot .st{display:none}
  .pages{display:block;padding:0}.page{box-shadow:none;break-after:page}
  .slot.empty{border:0;background:none}.slot.empty b,.slot.empty span:not(.badge){display:none}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}

/* 슬라이드 보기 · 발표 (2026-10-03) */
.bar .on{background:#f6c76b}
body.sv{overflow:hidden;background:#e5e7eb}
body.sv #sv .page,body.pr #sv .page{zoom:1}
body.sv .pages{display:none}
#sv{display:none}
body.sv #sv,body.pr #sv{display:flex;position:fixed;inset:44px 0 0 0}
#rail{width:210px;flex:0 0 210px;overflow-y:auto;background:#f8fafc;border-right:1px solid #d1d5db;padding:10px 12px 40px}
.th{position:relative;display:flex;gap:6px;margin-bottom:10px;cursor:pointer}
.th .n{font-size:12px;color:#64748b;width:16px;text-align:right;padding-top:2px}
.th .box{width:168px;height:118.8px;overflow:hidden;border-radius:4px;border:2px solid transparent;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.15)}
.th.cur .box{border-color:#2563eb}
.th .box .page{transform-origin:0 0;box-shadow:none}
#stage{flex:1;position:relative;overflow:hidden;display:flex;align-items:center;justify-content:center}
#stage .page{transform-origin:center center;flex:0 0 auto}
#hint{position:absolute;right:14px;bottom:10px;font-size:12px;color:#64748b}
body.pr{background:#000}
body.pr .bar,body.pr #rail,body.pr #hint{display:none}
body.pr #sv{inset:0;background:#000}
body.pr #stage .page{box-shadow:none}
body.pr .tag,body.sv #stage .tag{display:none}
#pn{position:absolute;left:50%;bottom:8px;transform:translateX(-50%);font-size:12px;color:#9ca3af;display:none}
body.pr #pn{display:block}
@media print{#sv{display:none!important}body.sv .pages,body.pr .pages{display:block!important}}
@media screen and (max-width:1150px){.page{zoom:calc(100vw / 1150px)}}
"""

VIEW = r"""
// 슬라이드 보기(왼쪽 작은 쪽 목록 + 오른쪽 큰 쪽) · 발표(전체 화면) — ←→ ↑↓ 스페이스 PgUp/PgDn, Esc 나가기
(function(){
  const pages=[...document.querySelectorAll('.pages > .page')];
  const rail=document.getElementById('rail'), stage=document.getElementById('stage'), pn=document.getElementById('pn');
  const PW=pages[0].offsetWidth, PH=pages[0].offsetHeight;
  let cur=0, built=false, big=null;
  function build(){
    if(built) return; built=true;
    pages.forEach((p,i)=>{
      const t=document.createElement('div'); t.className='th'; t.innerHTML='<span class="n">'+(i+1)+'</span><div class="box"></div>';
      const c=p.cloneNode(true); c.removeAttribute('id'); c.style.transform='scale('+(168/PW)+')';
      t.querySelector('.box').appendChild(c); t.onclick=()=>go(i); rail.appendChild(t);
    });
  }
  function fit(){
    if(!big) return;
    const r=stage.getBoundingClientRect(), pad=document.body.classList.contains('pr')?0:40;
    big.style.transform='scale('+Math.min((r.width-pad)/PW,(r.height-pad)/PH)+')';
  }
  function go(i){
    cur=Math.max(0,Math.min(pages.length-1,i));
    stage.querySelectorAll('.page').forEach(x=>x.remove());
    big=pages[cur].cloneNode(true); big.removeAttribute('id'); stage.prepend(big); fit();
    rail.querySelectorAll('.th').forEach((t,k)=>t.classList.toggle('cur',k===cur));
    const th=rail.children[cur]; if(th) th.scrollIntoView({block:'nearest'});
    pn.textContent=(cur+1)+' / '+pages.length;
  }
  function mode(m){
    document.body.classList.remove('sv','pr');
    document.querySelectorAll('.bar [data-mode]').forEach(b=>b.classList.toggle('on',b.dataset.mode===m));
    if(m==='doc'){ if(document.fullscreenElement) document.exitFullscreen(); return; }
    build(); document.body.classList.add(m);
    const bar=document.querySelector('.bar'); document.getElementById('sv').style.top=(m==='pr'?0:Math.max(0,bar.getBoundingClientRect().bottom))+'px';
    if(m==='pr' && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(()=>{});
    go(cur); setTimeout(fit,60);
  }
  window.wsMode=mode;
  document.addEventListener('keydown',e=>{
    const on=document.body.classList.contains('sv')||document.body.classList.contains('pr');
    if(!on) return;
    if(['ArrowRight','ArrowDown','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();go(cur+1)}
    else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(e.key)){e.preventDefault();go(cur-1)}
    else if(e.key==='Home') go(0); else if(e.key==='End') go(pages.length-1);
    else if(e.key==='Escape') mode(document.body.classList.contains('pr')?'sv':'doc');
  });
  stage.addEventListener('click',e=>{ if(!document.body.classList.contains('pr')) return;
    go(cur+(e.clientX>innerWidth/2?1:-1)); });
  let x0=null; stage.addEventListener('touchstart',e=>x0=e.touches[0].clientX,{passive:true});
  stage.addEventListener('touchend',e=>{ if(x0===null) return; const dx=e.changedTouches[0].clientX-x0; if(Math.abs(dx)>40) go(cur+(dx<0?1:-1)); x0=null; });
  document.addEventListener('fullscreenchange',()=>{ if(!document.fullscreenElement && document.body.classList.contains('pr')) mode('sv'); });
  addEventListener('resize',fit);
  const start=()=>{ if(location.hash==='#slides') mode('sv'); else if(location.hash==='#present') mode('pr'); };
  (document.fonts?document.fonts.ready:Promise.resolve()).then(start);
})();
"""

FIT = """
// 글이 칸을 넘치면 글자를 줄인다 — 웹글꼴이 늦게 오면 한 번 더
function wsFit(){document.querySelectorAll('.pages .body').forEach(b=>{let s=parseFloat(b.dataset.max||16);b.style.fontSize=s+'pt';
  while((b.scrollHeight>b.clientHeight+1||b.scrollWidth>b.clientWidth+1)&&s>6){s-=.25;b.style.fontSize=s+'pt'}})}
wsFit(); if(document.fonts) document.fonts.ready.then(wsFit);
"""


def img_src(rel: str) -> str:
    p = HERE / rel
    return f"data:image/{p.suffix[1:].replace('jpg', 'jpeg')};base64," + base64.b64encode(p.read_bytes()).decode()


ROSTER = HERE / "roster.json"
WEEKS_SHOWN = 6
GROUP_COLOR = {"인도·세션": ("#1e3a8a", "#eef2ff"), "싱어": ("#b45309", "#fff4e5"), "미디어": ("#0e7490", "#e6f7fa")}


def roster_html(date: str) -> str:
    """섬김표 — roster.json 하나로 관리(주보마다 따로 두지 않음). 이번 주부터 6주, 지원팀은 날짜와 상관없는 명단."""
    import datetime as _dt
    R = json.loads(ROSTER.read_text())
    start = _dt.date.fromisoformat(date)
    days = [start + _dt.timedelta(weeks=k) for k in range(WEEKS_SHOWN)]
    head = "".join(f'<th class="{"now" if k == 0 else ""}"><b>{x.month}.{x.day}</b>{"<i>이번 주</i>" if k == 0 else ""}</th>' for k, x in enumerate(days))
    rows = []
    for g in R["groups"]:
        c, soft = GROUP_COLOR.get(g["name"], ("#334155", "#f1f5f9"))
        for n, role in enumerate(g["roles"]):
            gc = f'<td class="grp" rowspan="{len(g["roles"])}" style="background:{c}">{g["name"].replace("·", "·<br>")}</td>' if n == 0 else ""
            cells = []
            for k, x in enumerate(days):
                names = R["weeks"].get(x.isoformat(), {}).get(role, [])
                # 한 칸 = 이름 자리 4개(2×2), 폭은 모두 같게 — 빈 자리는 비워 둔다 (2026-10-03 교장님 지시)
                slots = (names + [""] * 4)[:max(4, len(names))]
                base = R.get("defaults", {}).get(role)   # 평소 사람과 다르면 색을 바꿔 눈에 띄게 (2026-10-03 교장님 지시)
                chip = lambda v: (f'<span class="nm chg">{html.escape(v)}</span>' if base and v not in base
                                  else f'<span class="nm" style="background:{soft};border-color:{c}33">{html.escape(v)}</span>')
                if g.get("single"):   # 인도·세션: 한 줄, 두 칸을 합친 긴 칸 하나 (2026-10-03 교장님 지시)
                    v = ", ".join(names)
                    inner = (f'<span class="nm wide chg">{html.escape(v)}</span>' if v and base and any(n not in base for n in names)
                             else f'<span class="nm wide" style="background:{soft};border-color:{c}33">{html.escape(v)}</span>' if v
                             else '<span class="nm wide empty"></span>')
                    cells.append(f'<td class="{"now" if k == 0 else ""}"><div class="q1">{inner}</div></td>')
                    continue
                inner = "".join(chip(v) if v else '<span class="nm empty"></span>' for v in slots)
                cells.append(f'<td class="{"now" if k == 0 else ""}"><div class="q4">{inner}</div></td>')
            rows.append(f'<tr class="{"gs" if n == 0 else ""}">{gc}<td class="role" style="color:{c}">{role}</td>{"".join(cells)}</tr>')
    sup = "".join(f'<span class="nm">{html.escape(v)}</span>' for v in R.get("support", []))
    return (f'<div class="rs"><div class="rs-h"><div><span class="kick">WORSHIP TEAM ROSTER</span><h2>예배팀 섬김표</h2></div>'
            f'<div class="rr"><span class="lg"><span class="nm chg">이름</span> 평소와 바뀐 사람</span><span class="range">{days[0].month}.{days[0].day} ~ {days[-1].month}.{days[-1].day} · {WEEKS_SHOWN}주</span></div></div>'
            f'<table class="rt"><colgroup><col style="width:19mm"><col style="width:27mm">{"<col>" * WEEKS_SHOWN}</colgroup>'
            f'<tr><th></th><th></th>{head}</tr>{"".join(rows)}</table>'
            f'<div class="sup"><div class="sup-h"><b>지원팀</b><span>{len(R.get("support", []))}명</span></div><div class="sup-n">{sup}</div></div></div>')


def cover_html(p: dict) -> str:
    """표지: 짙은 남색 새벽빛 + 오른쪽 위 금빛 번짐 + 아래로 흐르는 금빛 오선과 음표."""
    import datetime as _dt
    y, m, d = (int(x) for x in p["date"].replace(" ", "").split("."))
    wd = "월화수목금토주"[_dt.date(y, m, d).weekday()]
    staff = "".join(f'<path d="M-20 {560+i*16} C 260 {470+i*16}, 520 {650+i*16}, 820 {560+i*16} S 1180 {470+i*16}, 1440 {540+i*16}" '
                    f'fill="none" stroke="#f6c76b" stroke-opacity="{.16+.05*i}" stroke-width="1.6"/>' for i in range(5))
    def on_staff(x, line):   # 오선 곡선 위의 y — 음표 머리가 줄·칸에 정확히 앉게
        y0 = 560 + line * 8
        segs = [((-20, y0), (260, y0 - 90), (520, y0 + 90), (820, y0)), ((820, y0), (1120, y0 - 90), (1180, y0 - 90), (1440, y0 - 20))]
        for P in segs:
            if P[0][0] <= x <= P[3][0]:
                lo, hi = 0.0, 1.0
                for _ in range(40):
                    t = (lo + hi) / 2
                    bx = sum(c * P[k][0] for k, c in enumerate(((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)))
                    lo, hi = (t, hi) if bx < x else (lo, t)
                return sum(c * P[k][1] for k, c in enumerate(((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)))
    notes = "".join(f'<g fill="#f6c76b" fill-opacity=".7"><ellipse cx="{x}" cy="{on_staff(x, ln):.1f}" rx="10" ry="7" transform="rotate(-20 {x} {on_staff(x, ln):.1f})"/>'
                    f'<rect x="{x+8}" y="{on_staff(x, ln)-58:.1f}" width="2.4" height="58"/></g>' for x, ln in ((640, 6), (720, 4), (800, 3), (960, 5), (1060, 7), (1160, 4)))
    rays = "".join(f'<path d="M1180 -40 L {700+i*110} 820 L {760+i*110} 820 Z" fill="#ffffff" fill-opacity=".025"/>' for i in range(5))
    cross = '<g stroke="#f6c76b" stroke-opacity=".5" stroke-width="3" stroke-linecap="round"><line x1="1262" y1="92" x2="1262" y2="190"/><line x1="1230" y1="124" x2="1294" y2="124"/></g>'
    bg = f'<svg class="bg" viewBox="0 0 1403 992" preserveAspectRatio="xMidYMid slice">{rays}{staff}{notes}{cross}</svg>'
    return (f'<div class="cover">{bg}<div class="in"><span class="kick">SUNDAY WORSHIP · SCORE BOOK</span>'
            f'<h1>{p["title"].replace(" ", "")}</h1><p class="sub">{p["sub"]}</p><span class="rule"></span>'
            f'<div class="foot"><span class="date">{y}. {m:02d}. {d:02d}<small>{wd + ('일' if wd == '주' else '요일')}</small></span>'
            f'<span class="ch"><b>{p.get("church", "제곡교회")}</b>{p.get("team", "예배팀")}</span></div></div></div>')


def page_html(n: int, p: dict, date: str) -> str:
    t = p["type"]; tag = f'<span class="tag">{n}쪽 · {KIND[t]}</span>'
    if t == "cover":
        inner = cover_html(p)
    elif t == "roster":
        inner = roster_html(date)
    elif t in ("recite", "creed"):
        mx = 60 if t == "creed" else 14
        inner = f'<div class="textpage{' creed' if t == 'creed' else ''}"><h2>{p["heading"]}</h2><div class="body" data-max="{mx}">{p["body"]}</div></div>'
    elif t == "sermon_text":
        inner = (f'<div class="textpage"><div class="sermon-head"><h2>설교본문:</h2><span class="ref">{p["ref"]}</span>'
                 f'<span class="tt">{p["title"]}</span></div><div class="body verses" data-max="18">{p["body"]}</div></div>')
    elif t == "sermon_summary":
        head = (f'<div class="sm-head"><b>{html.escape(p["title"])}</b><span>{html.escape(p.get("ref", ""))}</span></div>' if p.get("title") else "")
        inner = (f'<div class="col" style="left:0;display:flex;flex-direction:column">{head}<div class="body" data-max="20" style="flex:1;min-height:0;height:auto">{p["left"]}</div></div><div class="divider"></div>'
                 f'<div class="col" style="left:50%"><div class="body" data-max="20">{p["right"]}</div></div>')
    else:  # scores — 칸마다 배지(도입곡 · 1 · 2 … · 적용송)
        by = {s["side"]: s for s in p.get("slots", [])}
        halves = []
        for side in ("L", "R"):
            s = by.get(side) or {}
            badge = f'<span class="badge">{html.escape(s["label"])}</span>' if s.get("label") else ""
            where = f'{n}쪽 {"왼쪽" if side == "L" else "오른쪽"}'
            if s.get("img"):
                halves.append(f'<div class="half {side}"><div class="slot">{badge}<img src="{img_src(s["img"])}" alt="{html.escape(s.get("title", ""))}">'
                              f'<span class="st">{where} · {html.escape(s.get("title") or "제목 미정")}</span></div></div>')
            else:
                halves.append(f'<div class="half {side}"><div class="slot empty">{badge}<b>악보 자리</b><span>{where}{" · " + html.escape(s["label"]) if s.get("label") else ""} — 악보를 주시면 여기에 넣습니다</span></div></div>')
        inner = "".join(halves) + '<div class="divider"></div>'
    return f'<section class="page" id="p{n}">{tag}{inner}</section>'


GROUP = {"intro": "도입곡", "main": "", "apply": "적용송"}


def expand(d: dict) -> list[dict]:
    """{"type":"songs","group":"intro|main|apply"} 를 악보 쪽(두 곡씩)으로 펼친다.
    본곡(main)은 1, 2, 3 … 번호. 곡 수가 홀수면 다음 번호 빈 자리를 오른쪽에 남겨 둔다."""
    out = []
    for p in d["pages"]:
        if p["type"] != "songs":
            out.append(p); continue
        g = p["group"]; songs = d.get("songs", {}).get(g, [])
        lab = lambda i: str(i + 1) if g == "main" else (GROUP[g] if len(songs) <= 1 else f"{GROUP[g]} {i + 1}")
        slots = [dict(s, label=lab(i)) for i, s in enumerate(songs)]
        if len(slots) % 2 or not slots:
            slots.append({"label": lab(len(slots)) if g == "main" else f"{GROUP[g]} 추가 자리", "img": ""})
        for k in range(0, len(slots), 2):
            out.append({"type": "scores", "slots": [dict(x, side=sd) for x, sd in zip(slots[k:k + 2], "LR")]})
    return out


def build(date: str) -> Path:
    d = json.loads((HERE / "data" / f"{date}.json").read_text())
    d["pages"] = expand(d)
    st = next((p for p in d["pages"] if p["type"] == "sermon_text"), {})
    for p in d["pages"]:
        if p["type"] == "sermon_summary":
            p.setdefault("title", st.get("title", "")); p.setdefault("ref", st.get("ref", ""))
    pages = "".join(page_html(i, p, date) for i, p in enumerate(d["pages"], 1))
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(d["title"])}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>{CSS}</style></head><body>
<div class="bar"><b>🎹 {html.escape(d["title"])} · {len(d["pages"])}쪽</b><button data-mode="doc" class="on" onclick="wsMode('doc')">문서 보기</button><button data-mode="sv" onclick="wsMode('sv')">🖼 슬라이드 보기</button><button data-mode="pr" onclick="wsMode('pr')">▶ 발표</button><button onclick="print()">PDF로 저장</button></div>
<main class="pages">{pages}</main><div id="sv"><aside id="rail"></aside><div id="stage"><span id="hint">← → 방향키로 넘김 · Esc 나가기</span><span id="pn"></span></div></div><script data-share>{FIT}</script><script data-share>{VIEW}</script></body></html>"""
    out = HERE / "out" / f"{date}.html"; out.parent.mkdir(exist_ok=True); out.write_text(doc)
    return out


if __name__ == "__main__":
    o = build(sys.argv[1])
    print(o)
    if "--open" in sys.argv: subprocess.run(["open", o])
    if "--share" in sys.argv:
        import urllib.request, publish
        pretty = publish.prepare(sys.argv[1])   # jegok_worship_YYYYMMDD · 모음 쪽 · 노션 — 배포 전에
        body = json.dumps({"key": f"/accomp/{sys.argv[1]}", "title": o.stem + " 반주자·싱어용 악보", "html": o.read_text()}).encode()
        req = urllib.request.Request("http://127.0.0.1:8765/share", data=body, headers={"Content-Type": "application/json"})
        json.load(urllib.request.urlopen(req, timeout=180))
        print(pretty)
