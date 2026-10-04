"""예배 주간 쪽(악보 · PPT · 주보 · 🔒 준비) 공통 상단 메뉴 — 2단 고정 (2026-10-03 교장님: 쪽마다 상단이 달라 어수선하다)

  1단  ⛪ 제곡교회 예배 · 10월 4일   [악보] [PPT] [주보] [🔒 준비]  [⋯]     ← 어느 쪽에서나 똑같다
  2단  그 탭의 하위 메뉴 ……………………………………  [⬇ 내려받기 ▾]          ← 지금 쪽에 맞는 것만

docsave 공유본에 붙던 주황 [HWPX·PDF·링크 복사] 줄은 data-wsnav 가 있으면 붙지 않고, 「내려받기 ▾」 안으로 들어간다.
옛 `.bar` 자리를 그대로 쓰므로(class="bar wsnav") 악보집의 보기 전환·준비 탭 스크립트는 손대지 않아도 된다.
"""
from __future__ import annotations

import html as H

BASE = "https://report-site-kohl.vercel.app"

CSS = """
.wsnav{position:sticky;top:0;z-index:40;display:block!important;padding:0!important;background:#1f2937;color:#fff;font:14px 'Pretendard Variable',Pretendard,'Noto Sans KR',system-ui,sans-serif;word-break:keep-all}
.wsnav .r1{display:flex;align-items:center;gap:6px;padding:7px 12px;min-height:48px}
.wsnav .ttl{font-weight:800;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;color:#fff;text-decoration:none}
.wsnav .tabs{display:flex;gap:4px;flex:0 0 auto}
.wsnav .tick{flex:1;min-width:0;text-align:center;font-weight:900;font-size:15px;color:#fde047;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 10px}
.wsnav .tick:empty{visibility:hidden}
.wsnav .tick b{display:inline-block;background:#dc2626;color:#fff;border-radius:6px;padding:2px 8px;margin-right:8px;font-size:12px;vertical-align:1px}
.wsnav .tick.blink{animation:wstick 0.9s steps(2,jump-none) 4}
@keyframes wstick{0%{opacity:1}50%{opacity:.12}100%{opacity:1}}
.wsnav .tab{width:auto;font:700 14px inherit;border:0;border-radius:999px;padding:7px 15px;background:none;color:#e2e8f0;text-decoration:none;cursor:pointer;white-space:nowrap}
.wsnav .tab:hover{background:#334155}
.wsnav .tab.cur{background:#f6c76b;color:#412402}
body.prep .wsnav .tab.cur:not([data-mode]){background:none;color:#e2e8f0}
body.prep .wsnav .tab[data-mode=prep]{background:#f6c76b;color:#412402}
.wsnav .r2{display:flex;align-items:center;gap:4px;padding:5px 12px;background:#334155;min-height:40px;flex-wrap:wrap}
.wsnav .sub{width:auto;font:600 13px inherit;border:0;border-radius:7px;padding:6px 12px;background:none;color:#e2e8f0;text-decoration:none;cursor:pointer;white-space:nowrap}
.wsnav .sub:hover{background:#475569}
.wsnav .sub.on{background:#475569;color:#fff;box-shadow:inset 0 -2px 0 #f6c76b}
.wsnav .r2 input{font:14px inherit;border:0;border-radius:999px;padding:6px 14px;width:min(280px,46vw);margin:0 4px}
.wsnav .note{font-size:12.5px;color:#cbd5e1;padding:0 6px}
.wsnav details{position:relative}
.wsnav summary{list-style:none;cursor:pointer}.wsnav summary::-webkit-details-marker{display:none}
.wsnav .dl>summary{font:700 13px inherit;border-radius:7px;padding:6px 12px;background:#e8a33c;color:#412402;white-space:nowrap}
.wsnav .wk{font:800 14px inherit;color:#f6c76b;text-decoration:none;padding:7px 12px;margin-right:6px;border:1px solid #475569;border-radius:999px;white-space:nowrap}
.wsnav .wk:hover{background:#334155}
.wsnav .lib .menu{right:auto;left:0;min-width:170px}.wsnav .menu a.on{background:#fef3c7;font-weight:800}
.wsnav summary.tab{display:inline-block}
.wsnav .menu{position:absolute;right:0;top:calc(100% + 6px);z-index:50;min-width:190px;background:#fff;color:#111;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.25);padding:4px;display:flex;flex-direction:column}
.wsnav .menu a,.wsnav .menu button{font:600 14px inherit;text-align:left;border:0;background:none;color:#111;padding:10px 12px;border-radius:7px;text-decoration:none;cursor:pointer}
.wsnav .menu a:hover,.wsnav .menu button:hover{background:#f1f5f9}
.wsnav .push{margin-left:auto}
.wsnav .msg{font-size:12.5px;color:#fde68a}.wsnav .msg:empty{display:none}
@media (max-width:640px){
  .wsnav .r1{flex-wrap:wrap;gap:5px;padding:6px 8px}
  .wsnav .ttl{flex:1 0 auto;font-size:13px}.wsnav .tick{flex:1 1 100%;order:1;font-size:13px;padding:2px 0}.wsnav .tick:empty{display:none}
  .wsnav .tabs{flex:1 0 100%;display:grid;grid-template-columns:1.6fr repeat(4,1fr);gap:4px}
  .wsnav .wk{margin:0;padding:7px 4px;font-size:12.5px;text-align:center}
  .wsnav .lib summary.tab{display:block}.wsnav .lib .menu{left:auto;right:0}
  .wsnav .tab{padding:7px 2px;font-size:13px;text-align:center}
  .wsnav .r2{padding:4px 8px}.wsnav .r2 input{flex:1 0 100%;order:9;margin:4px 0 2px;width:auto}.wsnav .sub{padding:6px 9px;font-size:12.5px}
}
@media print{.wsnav{display:none!important}}
"""

JS = r"""
(function(){
  // 열린 메뉴(내려받기·더보기)는 바깥을 누르면 닫는다
  // 메뉴 높이를 --navh 로 알려 준다(목차·옆 칸이 메뉴 바로 아래 붙도록)
  const nh=()=>{ const n=document.querySelector('.wsnav'); if(n) document.documentElement.style.setProperty('--navh',n.offsetHeight+'px'); };
  nh(); addEventListener('resize',nh); addEventListener('load',nh);
  document.addEventListener('click',e=>{ document.querySelectorAll('.wsnav details[open]').forEach(d=>{ if(!d.contains(e.target)) d.open=false; }); });
  // 📢 예배팀 소통 전광판 — 체크 안 한 메시지를 하나씩 깜빡이며 번갈아 (2026-10-04 교장님). 5초마다 새로 불러온다
  (function(){ const r1=document.querySelector('.wsnav .r1'), box=document.querySelector('.wsnav .tick'); if(!r1||!box) return;
    let msgs=[], k=0;
    const day=()=>r1.dataset.date||((location.pathname.match(/jegok_worship_(\d{4})(\d{2})(\d{2})/)||[]).slice(1).join('-'));
    function show(){ if(!msgs.length){ box.textContent=''; return; } k%=msgs.length; const m=msgs[k];
      box.innerHTML='<b>📢 '+(k+1)+'/'+msgs.length+'</b>'; box.appendChild(document.createTextNode(m.text)); box.title=m.text;
      box.classList.remove('blink'); void box.offsetWidth; box.classList.add('blink'); k++; }
    async function load(){ const d=day(); if(!d) return; try{ const r=await fetch('/api/worship?chat='+d,{cache:'no-store'}); if(!r.ok) return;
        const j=await r.json(); const was=msgs.map(x=>x.id).join(); msgs=j; if(was!==msgs.map(x=>x.id).join()){ k=Math.max(0,msgs.length-1); show(); }
        window.dispatchEvent(new CustomEvent('wschat',{detail:msgs})); }catch(e){} }
    window.wsChatReload=load; load(); setInterval(load,5000); setInterval(show,5000);
  })();
  window.wsCopyLink=function(btn){ const u=location.href.split('#')[0], m=document.querySelector('.wsnav .msg');
    const ok=()=>{ if(m){ m.textContent='링크가 복사되었습니다'; setTimeout(()=>m.textContent='',2500);} const d=btn.closest('details'); if(d) d.open=false; };
    if(navigator.clipboard) navigator.clipboard.writeText(u).then(ok,()=>prompt('이 주소를 복사하세요',u)); else prompt('이 주소를 복사하세요',u); };
})();
"""


def label(date: str) -> str:
    return f"{int(date[5:7])}월 {int(date[8:10])}일"


def r1(cur: str, when: str, date: str | None = None, prep_js: bool = False, day: str | None = None) -> str:
    """1단: 🏠 제곡교회 예배 플랫폼 ……… [10월 4일 주일예배] [악보] [PPT] [자료실 ▾ 주보·악보와 PPT] [🔒 준비] (2026-10-03 교장님)"""
    root = f"{BASE}/jegok_worship_{date.replace('-', '')}/" if date else "./"
    def tab(key, name, href):
        return f'<a class="tab{" cur" if key == cur else ""}" href="{href}">{name}</a>'
    prep = ('<button class="tab" data-mode="prep" onclick="wsPrep()">🔒 준비</button>' if prep_js
            else f'<a class="tab" href="{root}#prep">🔒 준비</a>')
    lib = (f'<details class="lib"><summary class="tab{" cur" if cur in ("jubo", "song") else ""}">자료실 ▾</summary><div class="menu">'
           f'<a href="{root}jubo.html"{" class=on" if cur == "jubo" else ""}>📰 주보</a>'
           f'<a href="{BASE}/jegok_worship/song.html"{" class=on" if cur == "song" else ""}>🎼 악보와 PPT</a></div></details>')
    day = day or date
    return (f'<div class="r1"{f" data-date={chr(34)}{day}{chr(34)}" if day else ""}><a class="ttl" href="{BASE}/jegok_worship">🏠 제곡교회 예배 플랫폼</a>'
            f'<div class="tick" aria-live="polite" title="예배팀 소통 메시지 — PPT 왼쪽 채팅에서 체크하면 사라집니다"></div>'
            f'<nav class="tabs"><a class="wk" href="{root}">{H.escape(when)} 주일예배</a>'
            f'{tab("score", "악보", root)}{tab("ppt", "PPT", root + "ppt.html")}{lib}{prep}</nav></div>')


def nav(cur: str, when: str, sub: str = "", dl: list[tuple[str, str]] | None = None,
        date: str | None = None, prep_js: bool = False, day: str | None = None) -> str:
    """cur: 'score'|'ppt'|'jubo'|'song' · when: '10월 4일' · sub: 2단 왼쪽(하위 메뉴) HTML · dl: [(이름, href 또는 'js:함수()')]
    date 를 주면 탭 주소를 절대 주소로(주보처럼 다른 폴더에 사는 쪽), 없으면 같은 폴더 상대 주소.
    prep_js: 악보집 안에서는 🔒 준비를 같은 쪽 안에서 연다(wsPrep)."""
    items = []
    for name, href in (dl or []):
        if href.startswith("js:"):
            items.append(f'<button type="button" onclick="{H.escape(href[3:])}">{name}</button>')
        else:
            items.append(f'<a href="{H.escape(href)}" download>{name}</a>')
    items.append('<button type="button" onclick="wsCopyLink(this)">🔗 링크 복사</button>')
    return (f'<header class="bar wsnav" data-wsnav>{r1(cur, when, date, prep_js, day)}'
            f'<div class="r2">{sub}<span class="msg" aria-live="polite"></span>'
            f'<details class="dl push"><summary>⬇ 내려받기 ▾</summary><div class="menu">{"".join(items)}</div></details></div></header>')
