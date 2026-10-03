#!/usr/bin/env python3
"""주일예배 PPT(앞 화면용) → HTML 슬라이드 (2026-10-03 교장님 지시).

PPT 를 PDF 로 바꾼 파일을 읽어 장마다
  · 배경(사진·색·악보 그림) = 글자를 지운 그림 한 장
  · 글자 = 위치·크기·색 그대로 HTML 글자(고를 수 있고 선명함)
로 다시 짠다. 다른 그림에 가려 안 보이던 글자(곡 구간 표시 등)는 빼고, 보이는 글자만 올린다.
화면: 목록(아래로 넘겨 보기) · ▶ 발표(전체 화면, 방향키·밀기) · 순서 바로가기(성경암송·찬양·설교 …) · 원본 내려받기.

  python3 accomp/slides.py <PPT.pdf> 2026-09-27 [--pptx 원본.pptx]   # 그 주 공유 폴더에 ppt.html 로
"""
from __future__ import annotations
import html, json, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = Path.home() / "dev/daily-briefing/report-site"
SECTIONS = ["주일예배", "성경암송", "찬양과경배", "사도신경", "대표기도", "교회소식", "봉헌", "성경봉독", "특송", "설교", "찬양과결단", "축도", "예배를마칩니다"]


def css_color(c: int) -> str:
    return f"#{c:06x}"


def parse(pdf: Path, out: Path) -> list[dict]:
    import fitz
    from PIL import Image, ImageChops
    import io
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.jpg"): f.unlink()
    doc = fitz.open(pdf)
    slides = []
    for i, page in enumerate(doc):
        W, H = page.rect.width, page.rect.height
        full = Image.open(io.BytesIO(page.get_pixmap(dpi=72).tobytes("png"))).convert("RGB")
        spans = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0: continue
            for ln in b["lines"]:
                for s in ln["spans"]:
                    if s["text"].strip(): spans.append(s)
        # 글자를 지운 판
        for s in spans: page.add_redact_annot(fitz.Rect(s["bbox"]), fill=None)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        bare = Image.open(io.BytesIO(page.get_pixmap(dpi=72).tobytes("png"))).convert("RGB")
        bare.save(out / f"{i + 1:03d}.jpg", "JPEG", quality=80)
        diff = ImageChops.difference(full, bare).convert("L")
        texts = []
        for s in spans:
            x0, y0, x1, y1 = [round(v) for v in s["bbox"]]
            box = (max(0, x0), max(0, y0), min(full.width, x1), min(full.height, y1))
            if box[2] <= box[0] or box[3] <= box[1]: continue
            if max(diff.crop(box).getextrema()) < 40:   # 지워도 안 바뀜 = 가려져 안 보이던 글자
                continue
            texts.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "s": round(s["size"], 1),
                          "c": css_color(s["color"]), "b": "Bold" in s["font"] or bool(s["flags"] & 16), "t": s["text"]})
        texts = merge(texts, W)
        plain = " ".join(t["t"] for t in texts)
        slides.append({"n": i + 1, "w": W, "h": H, "img": f"{i + 1:03d}.jpg", "texts": texts, "plain": plain,
                       "hidden": " ".join(s["text"] for s in spans)})
    return slides


def merge(texts: list[dict], W: float) -> list[dict]:
    """같은 줄·같은 크기·같은 색 글자 조각을 한 줄로 — 낱말·문장부호 사이가 벌어지지 않게."""
    out = []
    for t in texts:
        p = out[-1] if out else None
        if (p and p["c"] == t["c"] and abs(p["s"] - t["s"]) < 1 and abs(p["y"] - t["y"]) <= max(4, t["s"] * .15)
                and 0 <= t["x"] - (p["x"] + p["w"]) <= t["s"] * 1.3):
            gap = t["x"] - (p["x"] + p["w"])
            p["t"] += (" " if gap > t["s"] * .12 and not p["t"].endswith(" ") and not t["t"].startswith(" ") else "") + t["t"]
            p["w"] = t["x"] + t["w"] - p["x"]; p["h"] = max(p["h"], t["h"]); p["b"] = p["b"] or t["b"]
        else:
            out.append(dict(t))
    for t in out:
        t["t"] = re.sub(r" {2,}", " ", t["t"]).strip()
        t["a"] = "l" if t["x"] < W * .065 else "c"   # 왼쪽 끝에서 시작하는 글(광고·사도신경)만 왼쪽 맞춤, 나머지는 원래 상자 가운데
        t["t"] = re.sub(r" ([.,)])", r"\1", re.sub(r"\( ", "(", t["t"]))
    return out


def outline(slides: list[dict], songs: list[str] | None = None) -> list[tuple[int, str]]:
    """바로가기 — 순서 표지 장과, 찬양 곡 이름(가려진 구간 표시의 첫 줄)."""
    marks, last, seen = [], "", set()
    def is_mark(x):   # 순서 이름(사도신경·대표기도 …)으로 시작하는 장 — 사도신경처럼 글이 길어도 표지로 본다
        f = re.sub(r"\s", "", x["plain"])
        return any(y in f[:40] for y in SECTIONS)
    for k, s in enumerate(slides):
        flat = re.sub(r"\s", "", s["plain"])
        sec = next((x for x in SECTIONS if x in flat[:40]), "")
        if sec and (len(flat) < 160 or sec == "사도신경" and "사도신경" in flat[:30] and last != "사도신경"):
            name = {"교회소식": "교회 소식", "성경봉독": "성경 봉독", "특송": "특송", "찬양과결단": "찬양과 결단", "예배를마칩니다": "마침"}.get(sec, sec)
            # 가사가 아직 없는 틀(2026-10-03): 곡마다 「찬양과경배」 표지 장만 있다 — 같은 표지가 또 나오면 곡 자리로 보고 곡 이름을 단다
            ph = sec in ("찬양과경배", "찬양과결단") and "Praise&Worship" in flat
            empty = k + 1 >= len(slides) or is_mark(slides[k + 1])   # 바로 다음이 또 표지 = 가사 장이 없는 자리
            if not (ph and sec in seen):
                marks.append((s["n"], name))
            seen.add(sec); last = sec
            if ph and empty and songs:
                marks.append((s["n"], "♪ " + songs.pop(0))); last = "song"
            continue
        if last in ("찬양과경배", "찬양과결단"):
            m = re.match(r"\s*1\.\s*([^/0-9]+?)(?:\s+\d+\.|$)", s["hidden"])
            nm = songs.pop(0) if songs else (m.group(1).strip()[:18] if m else "찬양")
            marks.append((s["n"], "♪ " + nm)); last = "song"
    return marks


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:#0f172a;color:#fff;font-family:'Pretendard Variable',Pretendard,'Apple SD Gothic Neo',sans-serif}}
.top{{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 12px;background:#1f2937}}
.top b{{margin-right:auto;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}}
.top a,.top button{{font:700 13px inherit;text-decoration:none;border:0;border-radius:999px;padding:7px 14px;background:#fff;color:#111;cursor:pointer;white-space:nowrap}}
.top .pr{{background:#f6c76b}}
.wrap{{display:flex}}
#toc{{position:sticky;top:46px;align-self:flex-start;width:190px;flex:0 0 190px;max-height:calc(100vh - 46px);overflow-y:auto;padding:10px 8px;background:#0b1220;font-size:13px}}
#toc a{{display:block;color:#cbd5e1;text-decoration:none;padding:5px 8px;border-radius:6px}}#toc a:hover,#toc a.on{{background:#1e293b;color:#f6c76b}}
#toc a.song{{padding-left:18px;color:#93c5fd}}
main{{flex:1;min-width:0;padding:14px;display:flex;flex-direction:column;align-items:center;gap:14px}}
.sl{{position:relative;width:min(100%,1100px);aspect-ratio:16/9;overflow:hidden;background:#000;box-shadow:0 4px 18px rgba(0,0,0,.4);border-radius:6px}}
.sl .in{{position:absolute;left:0;top:0;width:1440px;height:810px;transform-origin:0 0;background-size:100% 100%}}
.sl .tx{{position:absolute;white-space:pre;line-height:1;transform-origin:0 0}}
.sl .no{{position:absolute;right:8px;bottom:6px;font-size:11px;color:#fff;background:rgba(0,0,0,.45);border-radius:999px;padding:1px 7px;z-index:2}}
body.pr .top,body.pr #toc,body.pr .no{{display:none}}body.pr main{{padding:0;gap:0}}body.pr{{background:#000;overflow:hidden}}
body.pr .sl{{display:none;position:fixed;inset:0;margin:auto;width:min(100vw,calc(100vh*16/9));border-radius:0;box-shadow:none}}body.pr .sl.cur{{display:block}}
/* 한 장 보기(기본) — 목차를 누르면 스크롤 없이 그 장만 바로 (2026-10-03 교장님 지시) */
body.one:not(.pr) main .sl{{display:none;width:min(100%,calc((100vh - 120px)*16/9))}}body.one:not(.pr) main .sl.cur{{display:block}}
#vbar{{display:none;align-items:center;gap:10px;font-weight:700}}body.one #vbar{{display:flex}}body.pr #vbar{{display:none}}
#vbar button{{font:700 14px inherit;border:0;border-radius:999px;padding:8px 18px;background:#fff;color:#111;cursor:pointer}}
/* 발표자 보기(메인 모니터) — 청중 화면은 두 번째 모니터 창 (2026-10-03 교장님 지시) */
#pv{{display:none;position:fixed;left:190px;top:46px;right:0;bottom:0;z-index:15;background:#0b1220;padding:14px;gap:16px}}body.pv #pv{{display:flex}}
.pvl{{flex:2.3;min-width:0;display:flex;flex-direction:column}}.pvr{{flex:1;min-width:0;display:flex;flex-direction:column;gap:12px}}
.pvlab{{font-size:12px;color:#94a3b8;margin:0 0 5px}}.pvbox .sl{{width:100%;max-width:calc((100vh - 330px)*16/9)}}
/* 발표자 보기 아래 썸네일 — 지금 노래(목차 한 구간)의 장 전부, 누르면 앞 화면으로 (2026-10-03 교장님 지시) */
#pvthumbs{{flex:1;min-height:0;overflow-y:auto;display:flex;flex-wrap:wrap;align-content:flex-start;gap:8px;padding:2px}}
#pvthumbs .th{{width:170px;cursor:pointer;border:3px solid transparent;border-radius:8px;padding:1px}}#pvthumbs .th:hover{{border-color:#475569}}
#pvthumbs .th.on{{border-color:#f6c76b}}#pvthumbs .sl{{width:100%;box-shadow:none;border-radius:4px}}
.pvbox .last{{aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;background:#111827;border-radius:6px;color:#94a3b8}}
.pvinfo{{display:flex;justify-content:space-between;align-items:baseline;font-weight:800;font-size:26px}}#pvclock{{color:#f6c76b}}
.pvbtn{{display:flex;gap:8px}}.pvbtn button,.pvstop{{flex:1;font:700 15px inherit;border:0;border-radius:10px;padding:12px;cursor:pointer;background:#fff;color:#111}}
.pvstop{{flex:0 0 auto;background:#475569;color:#fff}}.pvnote{{font-size:12px;color:#94a3b8;line-height:1.5}}
#fstip{{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:30;background:rgba(0,0,0,.7);color:#fff;padding:10px 18px;border-radius:999px;font-size:16px}}
@media (max-width:760px){{#pv{{left:0}}#toc{{display:none}}.top b{{flex:1 0 100%}}main{{padding:8px}}}}
</style></head><body class="one">
<div class="top"><b>📽️ {title} · {n}장</b><button class="pr" onclick="present()">▶ 예배용</button><button id="lbtn" onclick="toggleList()">☰ 목록으로 보기</button>{dl}<a href="./">◀ 악보집으로</a></div>
<div class="wrap"><nav id="toc">{toc}</nav><main id="deck">{slides}<div id="vbar"><button onclick="view(cur-1)">◀ 이전</button><span id="vn"></span><button onclick="view(cur+1)">다음 ▶</button></div></main></div>
<div id="pv"><div class="pvl"><div class="pvlab">지금 앞 화면</div><div id="pvcur" class="pvbox"></div>
<div class="pvlab" style="margin-top:10px">이 노래·순서의 모든 장 — 누르면 앞 화면에 바로 나갑니다</div><div id="pvthumbs"></div></div>
<div class="pvr"><div class="pvlab">다음 장</div><div id="pvnext" class="pvbox"></div>
<div class="pvinfo"><span id="pvn"></span><span id="pvclock">00:00</span></div>
<div class="pvbtn"><button onclick="go(cur-1)">◀ 이전</button><button onclick="go(cur+1)">다음 ▶</button></div>
<div class="pvnote">← → 방향키·스페이스로 넘김 · 왼쪽 목차를 누르면 그 장으로 · Esc 끝내기</div>
<button class="pvstop" onclick="endPV()">■ 발표 끝내기</button></div></div>
<script>
const D={data};
const deck=document.getElementById('deck');
function fit(){{document.querySelectorAll('.sl').forEach(sl=>{{const k=sl.clientWidth/1440;sl.querySelector('.in').style.transform='scale('+k+')';}});}}
function paint(sl){{ if(sl.dataset.p) return; sl.dataset.p=1; const s=D[+sl.dataset.i]; const inn=sl.querySelector('.in');
  inn.style.backgroundImage='url(slides/'+s.img+')';
  s.texts.forEach(t=>{{const e=document.createElement('div');e.className='tx';e.textContent=t.t;
    e.style.cssText='left:'+t.x+'px;top:'+t.y+'px;font-size:'+t.s+'px;color:'+t.c+';font-weight:'+(t.b?800:500);
    inn.appendChild(e); const w=e.scrollWidth;
    if(w>t.w*1.02&&t.w>4) e.style.transform='scaleX('+(t.w/w)+')';
    else if(t.a==='c') e.style.left=(t.x+(t.w-w)/2)+'px';}}); }}
const io=new IntersectionObserver(es=>es.forEach(x=>{{if(x.isIntersecting)paint(x.target)}}),{{rootMargin:'800px'}});
document.querySelectorAll('.sl').forEach(sl=>io.observe(sl));
addEventListener('resize',fit); (document.fonts?document.fonts.ready:Promise.resolve()).then(fit); fit();
let cur=0; const all=[...document.querySelectorAll('.sl')];
function show(i){{cur=Math.max(0,Math.min(all.length-1,i)); all.forEach((s,k)=>s.classList.toggle('cur',k===cur)); paint(all[cur]); if(all[cur+1])paint(all[cur+1]); setTimeout(fit,0);}}
function presentHere(){{document.body.classList.add('pr'); const top=all.findIndex(s=>s.getBoundingClientRect().bottom>60); show(firstVisible());
  if(document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(()=>{{}});}}
function leave(){{document.body.classList.remove('pr'); all.forEach(s=>s.classList.remove('cur')); fit(); back();}}
addEventListener('keydown',e=>{{ if(!document.body.classList.contains('pr')) return;
  if(['ArrowRight','ArrowDown','PageDown',' ','Enter'].includes(e.key)){{e.preventDefault();show(cur+1)}}
  else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(e.key)){{e.preventDefault();show(cur-1)}}
  else if(e.key==='Home')show(0); else if(e.key==='End')show(all.length-1); else if(e.key==='Escape')leave(); }});
document.addEventListener('fullscreenchange',()=>{{ if(!SCREEN&&!document.fullscreenElement&&document.body.classList.contains('pr')) leave(); }});
deck.addEventListener('click',e=>{{ if(!document.body.classList.contains('pr')) return; show(cur+(e.clientX>innerWidth/2?1:-1)); }});
let x0=null; deck.addEventListener('touchstart',e=>x0=e.touches[0].clientX,{{passive:true}});
deck.addEventListener('touchend',e=>{{ if(x0===null||!document.body.classList.contains('pr'))return; const dx=e.changedTouches[0].clientX-x0; if(Math.abs(dx)>40)show(cur+(dx<0?1:-1)); x0=null; }});
document.querySelectorAll('#toc a').forEach(a=>a.onclick=ev=>{{ev.preventDefault(); const el=document.getElementById(a.getAttribute('href').slice(1)); if(document.body.classList.contains('pv')){{go(all.indexOf(el));return;}} if(ONE()){{view(all.indexOf(el));return;}} el.scrollIntoView({{behavior:'instant',block:'start'}});}});
{pvjs}
</script></body></html>"""


# 두 모니터 발표 — 메인 모니터는 발표자 보기(지금 장·다음 장·시계·목차), 두 번째 모니터는 앞 화면 창 (2026-10-03 교장님 지시)
# 같은 ppt.html 을 ?screen=1 로 연 창이 앞 화면이고, 두 창은 BroadcastChannel 로 장 번호를 주고받는다.
PVJS = r"""
const SCREEN=new URLSearchParams(location.search).has('screen');
const bc=('BroadcastChannel' in window)?new BroadcastChannel('wsppt'+location.pathname):null;
if(SCREEN){
  document.title='앞 화면 · '+document.title; document.body.classList.remove('one'); document.body.classList.add('pr');
  const _show=show; show=function(i,quiet){_show(i); if(!quiet&&bc)bc.postMessage({i:cur});};
  show(+(location.hash.slice(1)||0),true);
  if(bc){bc.onmessage=e=>{const m=e.data||{}; if(m.end){window.close();return;} if(typeof m.i==='number'&&m.i!==cur)show(m.i,true);}; bc.postMessage({hello:1});}
  const tip=document.createElement('div'); tip.id='fstip'; tip.textContent='화면을 한 번 누르면 꽉 찬 화면이 됩니다'; document.body.appendChild(tip);
  const fs=()=>{ if(document.fullscreenElement){tip.remove();return;} document.documentElement.requestFullscreen().then(()=>tip.remove()).catch(()=>{}); };
  fs(); document.addEventListener('fullscreenchange',()=>{ if(document.fullscreenElement)tip.remove(); });
  addEventListener('click',e=>{ if(!document.fullscreenElement){e.stopImmediatePropagation(); fs();} },true);
  addEventListener('keydown',e=>{ if(e.key==='Escape'){e.stopImmediatePropagation(); return;} if(!document.fullscreenElement)fs(); },true);
}
let scr=null,t0=0,tick=null;
const ONE=()=>document.body.classList.contains('one');
function view(i){ cur=Math.max(0,Math.min(all.length-1,i)); all.forEach((s,k)=>s.classList.toggle('cur',k===cur)); paint(all[cur]); if(all[cur+1])paint(all[cur+1]); fit();
  document.getElementById('vn').textContent=(cur+1)+' / '+all.length; let on=null;
  document.querySelectorAll('#toc a').forEach(a=>{ const k=all.indexOf(document.getElementById(a.getAttribute('href').slice(1))); if(k<=cur)on=a; a.classList.remove('on'); });
  if(on){on.classList.add('on'); on.scrollIntoView({block:'nearest'});} window.scrollTo(0,0); }
function back(){ if(ONE()) view(cur); else all[cur].scrollIntoView({block:'center'}); }
function toggleList(){ const b=document.getElementById('lbtn');
  if(ONE()){ document.body.classList.remove('one'); all.forEach(s=>s.classList.remove('cur')); b.textContent='▣ 한 장씩 보기'; fit(); all[cur].scrollIntoView({block:'start'}); }
  else { const i=firstVisible(); document.body.classList.add('one'); b.textContent='☰ 목록으로 보기'; view(i); } }
if(!SCREEN){ view(0);
  addEventListener('keydown',e=>{ const c=document.body.classList; if(!ONE()||c.contains('pr')||c.contains('pv')) return;
    if(['ArrowRight','ArrowDown','PageDown',' '].includes(e.key)){e.preventDefault();view(cur+1)}
    else if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){e.preventDefault();view(cur-1)}
    else if(e.key==='Home')view(0); else if(e.key==='End')view(all.length-1); });
  deck.addEventListener('touchend',e=>{ if(x0===null||!ONE()||document.body.classList.contains('pr'))return; const dx=e.changedTouches[0].clientX-x0; if(Math.abs(dx)>40)view(cur+(dx<0?1:-1)); x0=null; }); }
function firstVisible(){if(ONE())return cur; const i=all.findIndex(s=>s.getBoundingClientRect().bottom>60); return i<0?0:i;}
async function present(){
  if(SCREEN) return;
  let other=null;
  try{ if('getScreenDetails' in window){ const sd=await getScreenDetails(); other=sd.screens.find(s=>s!==sd.currentScreen)||null; } }catch(e){}
  if(!other&&window.screen.isExtended===false){ presentHere(); return; }   // 모니터가 하나뿐이면 예전처럼 이 창에서 전체 화면
  const start=firstVisible();
  const f=other?'popup,left='+other.availLeft+',top='+other.availTop+',width='+other.availWidth+',height='+other.availHeight+',fullscreen'
               :'popup,width=1280,height=720';
  scr=window.open(location.pathname+'?screen=1#'+start,'wsppt_screen',f);
  if(!scr){ alert('앞 화면 창이 막혔습니다. 주소창 오른쪽에서 팝업·창 관리를 「허용」한 뒤 ▶ 예배용을 다시 눌러 주세요.'); return; }
  if(!other) alert('앞 화면 창을 두 번째 모니터로 끌어 놓고, 그 창을 한 번 누르면 꽉 찬 화면이 됩니다.');
  enterPV(start);
}
function clock(){const s=Math.floor((Date.now()-t0)/1000); document.getElementById('pvclock').textContent=String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
function enterPV(i){ document.body.classList.add('pv'); t0=Date.now(); clearInterval(tick); tick=setInterval(clock,1000); clock(); go(i); }
function mount(id,i){ const box=document.getElementById(id); box.replaceChildren();
  if(i>=all.length){ box.innerHTML='<div class="last">마지막 장입니다</div>'; return; }
  paint(all[i]); const c=all[i].cloneNode(true); c.removeAttribute('id'); c.classList.remove('cur'); box.appendChild(c); }
function marks(){ return [...document.querySelectorAll('#toc a')].map(a=>all.indexOf(document.getElementById(a.getAttribute('href').slice(1)))).filter(k=>k>=0).sort((a,b)=>a-b); }
function songRange(i){ let s=0,e=all.length; for(const k of marks()){ if(k<=i) s=k; else { e=k; break; } } return [s,e]; }   // 목차 표시 사이 = 한 노래(순서)
let thR=null;
function thumbs(){ const [s,e]=songRange(cur), box=document.getElementById('pvthumbs');
  if(!thR||thR[0]!==s||thR[1]!==e){ box.replaceChildren();
    for(let k=s;k<e;k++){ paint(all[k]); const c=all[k].cloneNode(true); c.removeAttribute('id'); c.classList.remove('cur');
      const w=document.createElement('div'); w.className='th'; w.dataset.k=k; w.title=(k+1)+'번째 장 — 누르면 앞 화면으로'; w.appendChild(c); w.onclick=()=>go(k); box.appendChild(w); }
    thR=[s,e]; }
  box.querySelectorAll('.th').forEach(t=>t.classList.toggle('on',+t.dataset.k===cur)); fit();
  const on=box.querySelector('.th.on'); if(on) on.scrollIntoView({block:'nearest'}); }
function go(i,quiet){ cur=Math.max(0,Math.min(all.length-1,i)); mount('pvcur',cur); mount('pvnext',cur+1); thumbs(); fit();
  document.getElementById('pvn').textContent=(cur+1)+' / '+all.length;
  let on=null;
  document.querySelectorAll('#toc a').forEach(a=>{ const k=all.indexOf(document.getElementById(a.getAttribute('href').slice(1))); if(k<=cur)on=a; a.classList.remove('on'); });
  if(on){on.classList.add('on'); on.scrollIntoView({block:'nearest'});}
  if(!quiet&&bc) bc.postMessage({i:cur}); }
function endPV(){ document.body.classList.remove('pv'); clearInterval(tick); if(bc)bc.postMessage({end:1}); try{scr&&scr.close()}catch(e){} scr=null; back(); }
if(!SCREEN&&bc) bc.onmessage=e=>{ const m=e.data||{}; if(!document.body.classList.contains('pv'))return;
  if(m.hello) bc.postMessage({i:cur}); else if(typeof m.i==='number'&&m.i!==cur) go(m.i,true); };
addEventListener('keydown',e=>{ if(!document.body.classList.contains('pv')) return;
  if(['ArrowRight','ArrowDown','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();go(cur+1)}
  else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(e.key)){e.preventDefault();go(cur-1)}
  else if(e.key==='Home')go(0); else if(e.key==='End')go(all.length-1); else if(e.key==='Escape')endPV(); });
"""


def render(slides: list[dict], title: str, dl: str, songs: list[str] | None = None) -> str:
    data = [{"img": s["img"], "texts": s["texts"]} for s in slides]
    sl = "".join(f'<section class="sl" id="s{s["n"]}" data-i="{k}"><div class="in"></div><span class="no">{s["n"]}</span></section>'
                 for k, s in enumerate(slides))
    toc = "".join(f'<a href="#s{n}" class="{"song" if name.startswith("♪") else ""}">{html.escape(name)}</a>' for n, name in outline(slides, list(songs or [])))
    return PAGE.format(title=html.escape(title), n=len(slides), slides=sl, toc=toc, dl=dl,
                       data=json.dumps(data, ensure_ascii=False, separators=(",", ":")), pvjs=PVJS)


def song_titles(date: str) -> list[str]:
    """그 주 악보집 곡 순서(도입곡 → 1~N → 적용송). 없으면 악보 보관함의 「쓴 날」 기록에서."""
    try:
        d = json.loads((HERE / "data" / f"{date}.json").read_text()).get("songs", {})
        t = [x.get("title", "") for g in ("intro", "main", "apply") for x in d.get(g, [])]
        if any(t): return t
        bank = json.loads((HERE / "score_bank.json").read_text())["songs"]
        order = {"도입곡": 0, "적용송": 99}
        hits = []
        for title, rec in bank.items():
            for sc in rec["scores"].values():
                for u in sc.get("used", []):
                    if u.startswith(date):
                        lab = u.split(" ", 1)[1]
                        hits.append((order.get(lab, int(re.sub(r"\D", "", lab) or 50)), title))
        return [t for _, t in sorted(hits)]
    except Exception:
        return []


def make(pdf: Path, date: str, sid: str, pptx: Path | None = None) -> Path:
    folder = SITE / "d" / sid; folder.mkdir(parents=True, exist_ok=True)
    slides = parse(pdf, folder / "slides")
    shutil.copy(pdf, folder / "worship.pdf")
    dl = '<a href="worship.pdf" download="{0} 주일예배 PPT.pdf">⬇ PDF</a>'.format(date)
    if pptx:
        shutil.copy(pptx, folder / "worship.pptx")
        dl = f'<a href="worship.pptx" download="{date} 주일예배 PPT.pptx">⬇ PPT</a>' + dl
    title = f"{int(date[5:7])}월 {int(date[8:10])}일 주일예배 PPT"
    (folder / "ppt.html").write_text(render(slides, title, dl, song_titles(date)))
    return folder


def fetch(date: str) -> str:
    """그 주 드라이브 폴더의 「…주일예배 PPT」(.pptx)를 받아 worship_ppt/<날짜>.pptx·.pdf 로 둔다 (2026-10-03 교장님 지시).
    PDF 는 구글 슬라이드로 잠깐 바꿔 내보낸 뒤 그 임시본을 지운다. 드라이브 것이 더 새것일 때만 다시 받는다."""
    import datetime as dt, os
    sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
    import prep, weekly
    g = prep.G(prep.access_token()); fo = weekly.week_folder(g, dt.date.fromisoformat(date))
    if not fo: return "드라이브 폴더 없음"
    r = g.get(f"{prep.DRIVE}/files", q=f"'{fo['id']}' in parents and trashed=false and name contains '주일예배 PPT'",
              fields="files(id,name,mimeType,modifiedTime)", includeItemsFromAllDrives="true")
    f = next((x for x in sorted(r.get("files", []), key=lambda x: x["modifiedTime"], reverse=True)
              if x["mimeType"].endswith("presentationml.presentation")), None)
    if not f: return "주일예배 PPT 없음"
    px, pdf = HERE / "worship_ppt" / f"{date}.pptx", HERE / "worship_ppt" / f"{date}.pdf"
    mt = dt.datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")).timestamp()
    if pdf.exists() and px.exists() and px.stat().st_mtime >= mt: return "주일예배 PPT 그대로"
    px.parent.mkdir(exist_ok=True); px.write_bytes(g.download(f["id"]))
    c = g.req("POST", f"{prep.DRIVE}/files/{f['id']}/copy?supportsAllDrives=true&fields=id",
              {"name": f"_임시 변환 {f['name']}", "mimeType": "application/vnd.google-apps.presentation"}, timeout=300)
    try:
        pdf.write_bytes(g.req("GET", f"{prep.DRIVE}/files/{c['id']}/export?mimeType=application/pdf", timeout=300))
    finally:
        g.req("DELETE", f"{prep.DRIVE}/files/{c['id']}?supportsAllDrives=true")
    os.utime(px, (mt, mt))
    return f"주일예배 PPT 받음 · {f['name']}"


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    if sys.argv[1] == "fetch":
        print(fetch(sys.argv[2])); sys.exit(0)
    import publish
    a = sys.argv[1:]
    pptx = Path(a[a.index("--pptx") + 1]) if "--pptx" in a else None
    print(make(Path(a[0]), a[1], publish.sid_for(a[1]), pptx))
