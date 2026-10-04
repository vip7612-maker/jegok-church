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
SECTIONS = ["주일예배", "성경암송", "찬양과경배", "사도신경", "대표기도", "교회소식", "봉헌", "성경봉독", "특송", "선교보고", "설교", "찬양과결단", "축도", "예배를마칩니다"]


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
            name = {"교회소식": "교회 소식", "성경봉독": "성경 봉독", "특송": "특송", "선교보고": "선교 보고", "찬양과결단": "찬양과 결단", "예배를마칩니다": "마침"}.get(sec, sec)
            # 가사가 아직 없는 틀(2026-10-03): 곡마다 「찬양과경배」 표지 장만 있다 — 같은 표지가 또 나오면 곡 자리로 보고 곡 이름을 단다
            ph = sec in ("찬양과경배", "찬양과결단") and "Praise&Worship" in flat
            empty = k + 1 >= len(slides) or is_mark(slides[k + 1])   # 바로 다음이 또 표지 = 가사 장이 없는 자리
            if ph and sec in seen and not empty and songs:          # 곡마다 다시 나오는 「찬양과경배」 표지 = 다음 곡의 시작(목차도 그 곡으로)
                marks.append((s["n"], "♪ " + songs.pop(0))); last = "song"; continue
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
#toc{{position:sticky;top:var(--navh,88px);align-self:flex-start;width:190px;flex:0 0 190px;max-height:calc(100vh - var(--navh,88px));overflow-y:auto;padding:10px 8px;background:#0b1220;font-size:13px}}
#toc a{{display:block;color:#cbd5e1;text-decoration:none;padding:5px 8px;border-radius:6px}}#toc a:hover,#toc a.on{{background:#1e293b;color:#f6c76b}}
#toc a.song{{padding-left:18px;color:#93c5fd}}#toc a:focus,#toc a:focus-visible{{outline:none!important}}#toc a.on{{background:rgba(246,199,107,.16);color:#f6c76b;box-shadow:inset 4px 0 #f6c76b;font-weight:700}}
main{{flex:1;min-width:0;padding:14px;display:flex;flex-direction:column;align-items:center;gap:14px}}
.sl{{position:relative;width:min(100%,1100px);aspect-ratio:16/9;overflow:hidden;background:#000;box-shadow:0 4px 18px rgba(0,0,0,.4);border-radius:6px}}
.sl .in{{position:absolute;left:0;top:0;width:1440px;height:810px;transform-origin:0 0;background-size:100% 100%}}
.sl .tx{{position:absolute;white-space:pre;line-height:1;transform-origin:0 0}}
.sl .no{{position:absolute;right:8px;bottom:6px;font-size:11px;color:#fff;background:rgba(0,0,0,.45);border-radius:999px;padding:1px 7px;z-index:2}}
body.pr .top,body.pr .wsnav,body.pv .wsnav,body.pr #toc,body.pr .no{{display:none}}/* 앞 화면(두 번째 모니터)·전체 화면 발표엔 상단 메뉴 두 줄을 절대 안 보이게 — wsnav 의 display:block!important 를 이긴다 (2026-10-04 교장님) */body.pr .wsnav,body.pr header.wsnav,body.pr [data-wsnav]{{display:none!important}}body.pr #deck,body.pr main{{margin:0!important;padding:0!important}}body.pr main{{padding:0;gap:0}}body.pr{{background:#000;overflow:hidden}}
body.pr .sl{{display:none;position:fixed;inset:0;margin:auto;width:min(100vw,calc(100vh*16/9));border-radius:0;box-shadow:none}}body.pr .sl.cur{{display:block}}
/* 한 장 보기(기본) — 목차를 누르면 스크롤 없이 그 장만 바로 (2026-10-03 교장님 지시) */
body.one:not(.pr) main .sl{{display:none;width:min(100%,calc((100vh - var(--navh,88px) - 80px)*16/9))}}body.one:not(.pr) main .sl.cur{{display:block}}
#vbar{{display:none;align-items:center;gap:10px;font-weight:700}}body.one #vbar{{display:flex}}body.pr #vbar{{display:none}}
#vbar button{{font:700 14px inherit;border:0;border-radius:999px;padding:8px 18px;background:#fff;color:#111;cursor:pointer}}
/* 발표자 보기(메인 모니터) — 청중 화면은 두 번째 모니터 창 (2026-10-03 교장님 지시) */
#pv{{display:none;position:fixed;left:190px;top:var(--navh,88px);right:0;bottom:0;z-index:15;background:#0b1220;padding:14px;gap:12px 16px;
  grid-template-columns:min(70%,calc((var(--pvtop,520px) - 26px)*16/9)) minmax(0,1fr);grid-template-rows:var(--pvtop,520px) 14px minmax(0,1fr)}}body.pv #pv{{display:grid}}
.pvl{{grid-row:1;min-width:0;min-height:0;display:flex;flex-direction:column}}.pvr{{grid-row:1;min-width:0;min-height:0;overflow:hidden;display:flex;flex-direction:column;gap:12px}}#pvsplit{{grid-row:2;grid-column:1/-1;cursor:row-resize;display:flex;align-items:center;justify-content:center;touch-action:none}}#pvsplit::before{{content:'';width:120px;height:6px;border-radius:99px;background:#475569}}#pvsplit:hover::before,#pvsplit.on::before{{background:#f6c76b}}
/* 썸네일 줄은 아래 전체 폭 — 오른쪽 「발표 끝내기」 아래 빈 곳까지 쓴다 (2026-10-03 교장님 지시) */
.pvt{{grid-row:3;grid-column:1/-1;min-height:0;display:flex;flex-direction:column}}
.pvlab{{font-size:12px;color:#94a3b8;margin:0 0 5px}}.pvl .pvbox .sl{{width:100%}}.pvr .pvbox .sl{{width:100%;max-width:max(120px,calc((var(--pvtop,520px) - 225px)*16/9))}}.pvr{{container-type:size}}@container (max-height:430px){{.pvnote{{display:none}}}}
/* 발표자 보기 아래 썸네일 — 지금 노래(목차 한 구간)의 장 전부, 누르면 앞 화면으로 (2026-10-03 교장님 지시) */
#pvthumbs{{flex:1;min-height:0;overflow-y:auto;display:flex;flex-wrap:wrap;align-content:flex-start;gap:8px;padding:2px}}
#pvthumbs .th{{width:285px;cursor:pointer;border:3px solid transparent;border-radius:8px;padding:1px}}#pvthumbs .th:hover{{border-color:#475569}}
#pvthumbs .th.on{{border-color:#f6c76b}}#toc a.peek{{outline:2px dashed #93c5fd;outline-offset:-2px;color:#93c5fd}}#pvtlab b{{color:#93c5fd}}.pvback{{margin-left:8px;font:700 12px inherit;border:0;border-radius:999px;padding:4px 10px;background:#fff;color:#111;cursor:pointer}}#pvthumbs .sl{{width:100%;box-shadow:none;border-radius:4px}}
.pvbox .last{{aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;background:#111827;border-radius:6px;color:#94a3b8}}
.pvinfo{{display:flex;justify-content:space-between;align-items:baseline;font-weight:800;font-size:26px}}#pvclock{{color:#f6c76b}}
.pvbtn{{display:flex;gap:8px}}.pvbtn button,.pvstop{{flex:1;font:700 15px inherit;border:0;border-radius:10px;padding:12px;cursor:pointer;background:#fff;color:#111}}
.pvstop{{flex:0 0 auto;background:#475569;color:#fff}}.pvnote{{font-size:12px;color:#94a3b8;line-height:1.5}}
#fstip{{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:30;background:rgba(0,0,0,.7);color:#fff;padding:10px 18px;border-radius:999px;font-size:16px}}
@media (max-width:760px){{#pv{{left:0}}#toc{{display:none}}.top b{{flex:1 0 100%}}main{{padding:8px}}}}
{navcss}</style></head><body class="one">
{nav}
<div class="wrap"><nav id="toc">{toc}</nav><main id="deck">{slides}<div id="vbar"><button onclick="view(cur-1)">◀ 이전</button><span id="vn"></span><button onclick="view(cur+1)">다음 ▶</button></div></main></div>
<div id="pv"><div class="pvl"><div class="pvlab">지금 앞 화면</div><div id="pvcur" class="pvbox"></div></div>
<div class="pvr"><div class="pvlab">다음 장</div><div id="pvnext" class="pvbox"></div>
<div class="pvinfo"><span id="pvn"></span><span id="pvclock">00:00</span></div>
<div class="pvbtn"><button onclick="go(cur-1)">◀ 이전</button><button onclick="go(cur+1)">다음 ▶</button></div>
<div class="pvnote">← → 방향키·스페이스로 넘김 · 왼쪽 목차를 누르면 그 장으로 · Esc 끝내기</div>
<button class="pvstop" onclick="endPV()">■ 발표 끝내기</button></div>
<div id="pvsplit" title="끌어서 위·아래 크기 조절 (두 번 누르면 처음대로)"></div><div class="pvt"><div class="pvlab" id="pvtlab">이 노래·순서의 모든 장 — 누르면 앞 화면에 바로 나갑니다</div><div id="pvthumbs"></div></div></div>
<script>
const D={data};
const deck=document.getElementById('deck');
function fit(){{document.querySelectorAll('.sl').forEach(sl=>{{const k=sl.clientWidth/1440;sl.querySelector('.in').style.transform='scale('+k+')';}});}}
// 글자 폭은 늘 보이는 측정 칸에서 잰다 — 발표 중 숨겨 둔 다음 장을 미리 그릴 때 폭이 0 으로 재어져
// 가운데 정렬 자막이 칸 가운데에서 시작해 잘리던 문제(2026-10-03 교장님 화면)
const MZ=document.createElement('div'); MZ.style.cssText='position:absolute;left:-99999px;top:0;visibility:hidden;white-space:pre;line-height:1'; document.body.appendChild(MZ);
function measure(t){{ MZ.style.fontSize=t.s+'px'; MZ.style.fontWeight=t.b?800:500; MZ.textContent=t.t; return MZ.scrollWidth; }}
function paint(sl){{ if(sl.dataset.p) return; sl.dataset.p=1; const s=D[+sl.dataset.i]; const inn=sl.querySelector('.in');
  inn.style.backgroundImage='url(slides/'+s.img+')';
  let dy=0;   // 이어 붙인 문단이 PDF 보다 줄이 줄면, 그 아래 왼쪽 맞춤 글을 그만큼 올린다(빈 줄이 남지 않게)
  s.texts.forEach(t=>{{const e=document.createElement('div');e.className='tx';e.textContent=t.t;
    e.style.cssText='left:'+t.x+'px;top:'+(t.y-(t.a==='l'?dy:0))+'px;font-size:'+t.s+'px;color:'+t.c+';font-weight:'+(t.b?800:500)
      +(t.bg?';background:'+t.bg+';padding:5px 12px;border-radius:8px;line-height:1.15':'');   // 작은 단추(봉독대표·회중봉독 …)
    if(t.wrap){{ e.style.width=t.w+'px'; e.style.whiteSpace='normal'; e.style.wordBreak='keep-all'; e.style.lineHeight=(t.lh||1.2); inn.appendChild(e);   // 원본 한 문단 = 칸 폭에서 저절로 줄바꿈
      MZ.style.cssText+=';width:'+t.w+'px;white-space:normal;word-break:keep-all;line-height:'+(t.lh||1.2); MZ.style.fontSize=t.s+'px'; MZ.style.fontWeight=t.b?800:500; MZ.textContent=t.t;
      const lines=Math.round(MZ.offsetHeight/(t.s*(t.lh||1.2))), was=Math.round(t.h/(t.s*(t.lh||1.2)));
      dy+=Math.max(0,was-lines)*t.s*(t.lh||1.2); MZ.style.cssText='position:absolute;left:-99999px;top:0;visibility:hidden;white-space:pre;line-height:1'; return; }}
    inn.appendChild(e); const w=measure(t);
    if(w>t.w&&t.w>4) e.style.transform='scaleX('+(t.w/w)+')';
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
document.querySelectorAll('#toc a:not(.bgm)').forEach(a=>a.onclick=ev=>{{ev.preventDefault(); a.blur(); if(window.bgmClose) bgmClose(); const el=document.getElementById(a.getAttribute('href').slice(1)); if(document.body.classList.contains('pv')){{peek(all.indexOf(el),a);return;}} if(ONE()){{view(all.indexOf(el));return;}} el.scrollIntoView({{behavior:'instant',block:'start'}});}});
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
  if(bc){bc.onmessage=e=>{const m=e.data||{}; if(m.end){window.close();return;}
    if(m.bgm){bgmFS(m.bgm);return;} if(m.bgmStop){bgmFS(null);return;}
    if(typeof m.i==='number'){ bgmFS(null); if(m.i!==cur)show(m.i,true); }}; bc.postMessage({hello:1});}
  const tip=document.createElement('div'); tip.id='fstip'; tip.textContent='화면을 한 번 누르면 꽉 찬 화면이 됩니다'; document.body.appendChild(tip);
  const fs=()=>{ if(document.fullscreenElement){tip.remove();return;} document.documentElement.requestFullscreen().then(()=>tip.remove()).catch(()=>{}); };
  fs(); document.addEventListener('fullscreenchange',()=>{ if(document.fullscreenElement)tip.remove(); });
  addEventListener('click',e=>{ if(!document.fullscreenElement){e.stopImmediatePropagation(); fs();} },true);
  addEventListener('keydown',e=>{ if(e.key==='Escape'){e.stopImmediatePropagation(); return;} if(!document.fullscreenElement)fs(); },true);
}
let scr=null,t0=0,tick=null;
// 발표자 보기 위(지금·다음 장) / 아래(미리 보기) 크기 — 가운데 막대를 끌어 위아래로 조절, 이 기기에 기억 (2026-10-04 교장님)
(function(){ const pv=document.getElementById('pv'), sp=document.getElementById('pvsplit'); if(!pv||!sp) return;
  const set=h=>{ if(h==null){ pv.style.removeProperty('--pvtop'); } else pv.style.setProperty('--pvtop',h+'px'); if(typeof fit==='function') fit(); };
  let saved=0; try{ saved=+localStorage.getItem('ws_pvtop')||0; }catch(e){}
  window.pvSize=()=>{ const nh=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--navh'))||88;
    const room=innerHeight-nh-28-14; set(Math.max(300,saved>0?Math.min(saved,room-140):Math.round(room*0.6))); };
  let drag=null;
  sp.addEventListener('pointerdown',e=>{ drag={y:e.clientY,h:pv.querySelector('.pvl').getBoundingClientRect().height}; sp.classList.add('on'); sp.setPointerCapture(e.pointerId); e.preventDefault(); });
  sp.addEventListener('pointermove',e=>{ if(!drag) return; const max=pv.clientHeight-160; set(Math.round(Math.max(300,Math.min(max,drag.h+e.clientY-drag.y)))); });
  sp.addEventListener('pointerup',()=>{ if(!drag) return; drag=null; sp.classList.remove('on'); saved=parseInt(pv.style.getPropertyValue('--pvtop'))||0; try{ localStorage.setItem('ws_pvtop',saved); }catch(e){} });
  sp.addEventListener('dblclick',()=>{ saved=0; try{ localStorage.removeItem('ws_pvtop'); }catch(e){} pvSize(); });
  addEventListener('resize',()=>{ if(document.body.classList.contains('pv')) pvSize(); });
})();
// BGM 을 앞 화면(두 번째 모니터)에서 꽉 차게 — 발표자 화면에서 고르면 BroadcastChannel 로 영상 번호가 온다 (2026-10-03 교장님)
function bgmFS(id){ let o=document.getElementById('bgmfs'); if(!id){ if(o)o.remove(); return; }
  if(!o){ o=document.createElement('div'); o.id='bgmfs'; o.style.cssText='position:fixed;inset:0;z-index:9999;background:#000'; document.body.appendChild(o); }
  o.innerHTML='<iframe src="https://www.youtube-nocookie.com/embed/'+id+'?autoplay=1&rel=0&modestbranding=1&playsinline=1" style="width:100%;height:100%;border:0" allow="autoplay; encrypted-media; fullscreen"></iframe>'; }
const ONE=()=>document.body.classList.contains('one');
function view(i){ cur=Math.max(0,Math.min(all.length-1,i)); all.forEach((s,k)=>s.classList.toggle('cur',k===cur)); paint(all[cur]); if(all[cur+1])paint(all[cur+1]); fit();
  document.getElementById('vn').textContent=(cur+1)+' / '+all.length; let on=null;
  document.querySelectorAll('#toc a').forEach(a=>{ const k=all.indexOf(document.getElementById(a.getAttribute('href').slice(1))); if(k>=0&&k<=cur)on=a; a.classList.remove('on'); });
  if(on){on.classList.add('on'); on.scrollIntoView({block:'nearest'});} window.scrollTo(0,0); }
function back(){ if(ONE()) view(cur); else all[cur].scrollIntoView({block:'center'}); }
function toggleList(){ const b=document.getElementById('lbtn');
  if(ONE()){ document.body.classList.remove('one'); all.forEach(s=>s.classList.remove('cur')); fit(); all[cur].scrollIntoView({block:'start'}); }
  else { const i=firstVisible(); document.body.classList.add('one'); view(i); }
  document.getElementById('b-one').classList.toggle('on',ONE()); if(b) b.classList.toggle('on',!ONE()); }
function wsView(one){ if(one!==ONE()) toggleList(); }
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
function enterPV(i){ document.body.classList.add('pv'); if(window.pvSize) pvSize(); t0=Date.now(); clearInterval(tick); tick=setInterval(clock,1000); clock(); go(i); }
function mount(id,i){ const box=document.getElementById(id); box.replaceChildren();
  if(i>=all.length){ box.innerHTML='<div class="last">마지막 장입니다</div>'; return; }
  paint(all[i]); const c=all[i].cloneNode(true); c.removeAttribute('id'); c.classList.remove('cur'); box.appendChild(c); }
function marks(){ return [...document.querySelectorAll('#toc a')].map(a=>all.indexOf(document.getElementById(a.getAttribute('href').slice(1)))).filter(k=>k>=0).sort((a,b)=>a-b); }
function songRange(i){ let s=0,e=all.length; for(const k of marks()){ if(k<=i) s=k; else { e=k; break; } } return [s,e]; }   // 목차 표시 사이 = 한 노래(순서)
let thR=null;
// 발표 중 목차를 누르면 그 순서의 장들만 아래에 펼쳐 미리 본다 — 앞 화면은 장(썸네일)을 눌러야 넘어간다 (2026-10-04 교장님: 다음 곡 준비)
let peekAt=null;
function peek(k,a){ if(k<0) return; peekAt=k; thumbs(k); document.querySelectorAll('#toc a').forEach(x=>x.classList.toggle('peek',x===a&&!x.classList.contains('on')));
  const [s]=songRange(k), lab=document.getElementById('pvtlab'); const same=songRange(cur)[0]===s;
  lab.innerHTML=same?'이 노래·순서의 모든 장 — 누르면 앞 화면에 바로 나갑니다'
    :'👀 미리 보기: <b>'+(a?a.textContent:'')+'</b> — 앞 화면은 그대로입니다. 장을 눌러야 넘어갑니다 <button class="pvback" onclick="unpeek()">↩ 지금 순서로</button>';
  document.getElementById('pvthumbs').scrollTop=0; }
function unpeek(){ peekAt=null; document.querySelectorAll('#toc a.peek').forEach(x=>x.classList.remove('peek')); document.getElementById('pvtlab').textContent='이 노래·순서의 모든 장 — 누르면 앞 화면에 바로 나갑니다'; thumbs(); }
function thumbs(at){ const [s,e]=songRange(at==null?cur:at), box=document.getElementById('pvthumbs');
  if(!thR||thR[0]!==s||thR[1]!==e){ box.replaceChildren();
    for(let k=s;k<e;k++){ paint(all[k]); const c=all[k].cloneNode(true); c.removeAttribute('id'); c.classList.remove('cur');
      const w=document.createElement('div'); w.className='th'; w.dataset.k=k; w.title=(k+1)+'번째 장 — 누르면 앞 화면으로'; w.appendChild(c); w.onclick=()=>go(k); box.appendChild(w); }
    thR=[s,e]; }
  box.querySelectorAll('.th').forEach(t=>t.classList.toggle('on',+t.dataset.k===cur)); fit();
  const on=box.querySelector('.th.on'); if(on) on.scrollIntoView({block:'nearest'}); }
function go(i,quiet){ const fe=document.activeElement; if(fe&&fe.closest&&fe.closest('#toc')) fe.blur();   // 목차 초점 테두리가 지난 항목에 남지 않게
  cur=Math.max(0,Math.min(all.length-1,i)); mount('pvcur',cur); mount('pvnext',cur+1); if(peekAt!==null) unpeek(); else thumbs(); fit();
  document.getElementById('pvn').textContent=(cur+1)+' / '+all.length;
  let on=null;
  document.querySelectorAll('#toc a').forEach(a=>{ const k=all.indexOf(document.getElementById(a.getAttribute('href').slice(1))); if(k>=0&&k<=cur)on=a; a.classList.remove('on'); });
  if(on){on.classList.add('on'); on.scrollIntoView({block:'nearest'});}
  if(!quiet&&bc) bc.postMessage({i:cur}); }
function endPV(){ document.body.classList.remove('pv'); clearInterval(tick); if(bc)bc.postMessage({end:1}); try{scr&&scr.close()}catch(e){} scr=null; back(); }
if(!SCREEN&&bc) bc.onmessage=e=>{ const m=e.data||{}; if(!document.body.classList.contains('pv'))return;
  if(m.hello) bc.postMessage({i:cur}); else if(typeof m.i==='number'&&m.i!==cur) go(m.i,true); };
addEventListener('keydown',e=>{ if(!document.body.classList.contains('pv')) return;
  if(['ArrowRight','ArrowDown','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();go(cur+1)}
  else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(e.key)){e.preventDefault();go(cur-1)}
  else if(e.key==='Home')go(0); else if(e.key==='End')go(all.length-1); else if(e.key==='Escape')endPV(); });

// ── 교회 소식 급히 고치기 (2026-10-04 교장님) ─────────────────────────────
// 「교회 소식」 표지 다음부터 「봉헌」 표지 앞까지가 소식 장. ✏️ 를 누르면 줄마다 고칠 수 있고,
// 저장하면 앞 화면(두 번째 모니터)에도 바로 바뀌고 서버에 남아 새로 열어도 유지된다.
const NEWS=(()=>{ const T=i=>D[i].texts.map(t=>t.t).join(' '); let s=-1,e=-1;
  for(let i=0;i<D.length;i++){ const t=T(i).replace(/\s/g,''); if(s<0&&/교회소식|Announcements/.test(t)) s=i; else if(s>=0&&/^(Offering|봉헌)|Offering봉헌/.test(t)){ e=i; break; } }
  const r=[]; if(s>=0) for(let i=s+1;i<(e<0?Math.min(D.length,s+8):e);i++) r.push(i); return r; })();
// 순서 장(대표기도·봉헌·성경봉독·특송·설교·선교보고…) — 맡은 사람 이름이 현장에서 바뀌면 그 자리에서 고친다 (2026-10-04 교장님)
const ROLE=D.map((s,i)=>i).filter(i=>{ const t=D[i].texts.map(x=>x.t).join(' ');
  return D[i].texts.length<=8 && /^(Prayer|Offering|Scripture\s*Reading|Special\s*Praise|Sermon|Mission\s*Report|Benediction|대표\s*기도|봉\s*헌|성경\s*봉독|특\s*송|설\s*교|선교\s*보고)/.test(t.trim()); });
const EDIT=[...new Set([...NEWS,...ROLE])];
// 대표기도·봉헌·특송은 맡은 분 이름 칸만 고친다(제목·안내 문구는 그대로) — 2026-10-04 교장님
const NAMEONLY=i=>/^(Prayer|Offering|Special\s*Praise|대표\s*기도|봉\s*헌|특\s*송)/.test(D[i].texts.map(x=>x.t).join(' ').trim());
const ISNAME=t=>t.s>=40&&t.s<100;
const ORIG=D.map(s=>s.texts.map(t=>t.t).join('\n'));
function repaint(i){ const sl=all[i]; if(!sl) return; sl.querySelectorAll('.in .tx').forEach(x=>x.remove()); delete sl.dataset.p; paint(sl);
  if(document.body.classList.contains('pv')){ thR=null; go(cur,true); } fit(); }
function applyNews(i,texts){ if(!D[i]) return; texts.forEach((t,j)=>{ if(D[i].texts[j]) D[i].texts[j].t=t; }); repaint(i); }
if(bc){ const prev=bc.onmessage; bc.onmessage=e=>{ const m=e.data||{}; if(m.news){ applyNews(m.news.i,m.news.texts); return; } if(prev) prev(e); }; }
fetch('/api/worship?news='+NDATE,{cache:'no-store'}).then(r=>r.json()).then(rows=>{ (rows||[]).forEach(r=>{ if(r.orig===ORIG[r.i]) applyNews(r.i,r.texts); }); }).catch(()=>{});
if(!SCREEN&&EDIT.length){
  const st=document.createElement('style'); st.textContent=`#nbtn{position:fixed;right:18px;bottom:18px;z-index:60;display:none;font:800 16px 'Pretendard Variable',sans-serif;border:0;border-radius:999px;padding:12px 20px;background:#f6c76b;color:#3b2a06;box-shadow:0 4px 16px rgba(0,0,0,.4);cursor:pointer}
#nbox{position:fixed;inset:0;z-index:70;display:none;background:rgba(0,0,0,.6);align-items:center;justify-content:center}
#nbox .p{background:#fff;color:#111;border-radius:14px;width:min(860px,94vw);max-height:90vh;overflow:auto;padding:18px 20px;font:15px 'Pretendard Variable',sans-serif}
#nbox h3{margin:0 0 6px}#nbox .h{color:#64748b;font-size:13px;margin-bottom:10px}
#nbox textarea{width:100%;box-sizing:border-box;font:16px 'Pretendard Variable',sans-serif;border:1px solid #cbd5e1;border-radius:8px;padding:8px;margin:4px 0;resize:vertical}
#nbox .b{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}#nbox .b button{font:700 15px inherit;border:0;border-radius:999px;padding:10px 18px;cursor:pointer}
#nbox .ok{background:#1f2937;color:#fff}#nbox .no{background:#e2e8f0}#nbox .m{font-size:13px;color:#b45309;margin-right:auto;align-self:center}`;
  document.head.appendChild(st);
  const btn=document.createElement('button'); btn.id='nbtn'; btn.textContent='✏️ 교회 소식 수정'; document.body.appendChild(btn);
  const box=document.createElement('div'); box.id='nbox'; box.innerHTML='<div class="p"><h3>✏️ 교회 소식 수정</h3><div class="h"></div><div class="f"></div><div class="b"><span class="m"></span><button class="no">닫기</button><button class="ok">저장 — 앞 화면에 바로 반영</button></div></div>'; document.body.appendChild(box);
  const here=()=>document.body.classList.contains('pv')||ONE()?cur:firstVisible();
  const sync=()=>{ const h=here(); btn.style.display=EDIT.includes(h)?'block':'none'; btn.textContent=NEWS.includes(h)?'✏️ 교회 소식 수정':NAMEONLY(h)?'✏️ 이름 수정':'✏️ 이름·내용 수정'; };
  const _go=go; go=function(i,q){ _go(i,q); sync(); }; const _view=view; view=function(i){ _view(i); sync(); };
  addEventListener('scroll',()=>{ if(!ONE()) sync(); },{passive:true}); setInterval(sync,800); sync();
  let ei=-1;
  btn.onclick=()=>{ ei=here(); const f=box.querySelector('.f'); f.replaceChildren();
    const only=!NEWS.includes(ei)&&NAMEONLY(ei); box.querySelector('h3').textContent=NEWS.includes(ei)?'✏️ 교회 소식 수정':only?'✏️ 맡은 분 이름 수정 (오늘만)':'✏️ 이름·내용 수정 (오늘만)'; box.querySelector('.h').textContent=(ei+1)+'번째 장 · 줄마다 고친 뒤 저장하세요 (이번 주 PPT 에만 반영, 주보는 그대로)';
    D[ei].texts.forEach((t,j)=>{ if(only&&!ISNAME(t)) return; const a=document.createElement('textarea'); a.dataset.j=j; a.value=t.t; a.rows=Math.max(1,Math.ceil(t.t.length/48)); if(only) a.placeholder='맡은 분 이름 (예: 홍길동 장로)'; f.appendChild(a); });
    box.querySelector('.m').textContent=''; box.style.display='flex'; };
  box.addEventListener('keydown',e=>e.stopPropagation(),true);
  box.querySelector('.no').onclick=()=>{ box.style.display='none'; };
  box.querySelector('.ok').onclick=()=>{ const texts=D[ei].texts.map(t=>t.t); box.querySelectorAll('textarea').forEach(a=>{ texts[+a.dataset.j]=a.value; }); const m=box.querySelector('.m');
    applyNews(ei,texts); if(bc) bc.postMessage({news:{i:ei,texts}});
    m.textContent='저장 중…';
    fetch('/api/worship',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'news',date:NDATE,key:NKEY,i:ei,orig:ORIG[ei],texts})})
      .then(r=>r.json()).then(j=>{ if(j.ok){ m.textContent='✅ 저장했습니다'; setTimeout(()=>{box.style.display='none';},700); } else m.textContent='화면엔 바꿨지만 저장 실패: '+(j.error||''); })
      .catch(()=>{ m.textContent='화면엔 바꿨지만 저장 실패 — 인터넷 연결을 확인해 주세요'; }); };
}
"""


# ── BGM — 예배를 마친 뒤 성도의 교제 때 틀 신나는 CCM (2026-10-03 교장님) ─────────────────
# ppt.html 을 만들 때 유튜브에서 찾아 퍼가기(임베드)가 되는 것만 5개. 같은 주는 out/bgm/<날짜>.json 에 두어 다시 만들어도 그대로.
BGM_Q = ["신나는 CCM 찬양 모음", "기쁨의 찬양 CCM 플레이리스트", "경쾌한 CCM 찬양 연속듣기", "밝은 CCM 예배찬양 플레이리스트",
         "신나는 찬양 메들리", "드라이브 CCM 찬양 플레이리스트", "업비트 CCM 찬양 모음"]


def bgm(date: str, n: int = 5) -> list[dict]:
    import datetime as dt, subprocess
    f = HERE / "out" / "bgm" / f"{date}.json"
    if f.exists(): return json.loads(f.read_text())
    wk = dt.date.fromisoformat(date).isocalendar()[1]
    seen, out, extra = set(), [], []
    for q in (BGM_Q[wk % len(BGM_Q)], BGM_Q[(wk + 3) % len(BGM_Q)]):
        try:
            r = subprocess.run(["yt-dlp", "--no-warnings", "--skip-download", "--print",
                                "%(id)s\t%(title)s\t%(duration)s\t%(playable_in_embed)s\t%(channel)s", f"ytsearch8:{q}"],
                               capture_output=True, text=True, timeout=180)
        except Exception:
            continue
        for ln in r.stdout.splitlines():
            p = ln.split("\t")
            if len(p) < 5 or p[0] in seen or p[3] != "True" or not p[2].isdigit() or int(p[2]) < 180: continue
            if re.search(r"(?i)shorts|MR|반주|inst", p[1]): continue
            seen.add(p[0]); v = {"id": p[0], "title": p[1], "sec": int(p[2]), "ch": p[4]}
            (out if v["ch"] not in {x["ch"] for x in out} else extra).append(v)      # 채널이 겹치지 않게 먼저
    out = (out + extra)[:n]
    if out:
        f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def bgm_html(items: list[dict]) -> str:
    if not items: return ""
    tm = lambda s: f"{s // 3600}시간 {s % 3600 // 60}분" if s >= 3600 else f"{s // 60}분"
    cards = "".join(f'<button class="bgmc" data-id="{html.escape(v["id"])}"><img src="https://i.ytimg.com/vi/{html.escape(v["id"])}/mqdefault.jpg" alt="" loading="lazy">'
                    f'<span>{html.escape(v["title"])}</span><small>{html.escape(v["ch"])} · {tm(v["sec"])}</small></button>' for v in items)
    return ('<div id="bgmbox"><div class="bgmh"><b>🎵 BGM · 성도의 교제를 위한 찬양</b><span id="bgmnow"></span><button class="bgmx" onclick="bgmClose()">닫기 (음악은 계속)</button></div>'
            '<div id="bgmmode"></div><div id="bgmplay"></div><div class="bgml">' + cards + '</div><p class="bgmnote">누르면 그 영상이 나옵니다 · 다른 순서로 가도 음악은 계속 · ■ 멈춤은 영상에서</p></div>'
            """<script>
function bgmOpen(){ bgmMode(); document.body.classList.add('bgm'); document.querySelectorAll('#toc a').forEach(a=>a.classList.toggle('on',a.classList.contains('bgm'))); }
function bgmScreen(){ return typeof scr!=='undefined' && scr && !scr.closed && typeof bc!=='undefined' && bc; }
function bgmStop(){ if(bgmScreen()) bc.postMessage({bgmStop:1}); document.getElementById('bgmplay').innerHTML=''; document.getElementById('bgmnow').textContent=''; document.querySelectorAll('.bgmc').forEach(x=>x.classList.remove('on')); }
function bgmMode(){ const m=document.getElementById('bgmmode'); if(!m) return; const on=bgmScreen();
  m.innerHTML=on?'📺 앞 화면이 열려 있습니다 — 고르면 두 번째 모니터에서 전체 화면으로 나옵니다'
               :'앞 화면이 열려 있지 않아 이 화면에서 나옵니다 <button class="bgmx" onclick="bgmOpenScreen()">📺 앞 화면 열기</button>'; }
async function bgmOpenScreen(){ if(typeof present==='function'){ await present(); bgmOpen(); } }
function bgmClose(){ document.body.classList.remove('bgm'); const b=document.querySelector('#toc a.bgm'); if(b) b.classList.remove('on'); }
addEventListener('DOMContentLoaded',()=>{
  const t=document.querySelector('#toc a.bgm'); if(t) t.onclick=e=>{ e.preventDefault(); t.blur(); bgmOpen(); };
  document.querySelector('#bgmbox .bgml').onclick=e=>{ const c=e.target.closest('.bgmc'); if(!c) return;
    document.querySelectorAll('.bgmc').forEach(x=>x.classList.toggle('on',x===c));
    const name=c.querySelector('span').textContent.slice(0,40), P=document.getElementById('bgmplay');
    if(bgmScreen()){ bc.postMessage({bgm:c.dataset.id}); P.innerHTML='<div class="bgmon">📺 앞 화면(두 번째 모니터)에서 전체 화면으로 재생 중 <button class="bgmx" onclick="bgmStop()">■ 앞 화면 멈춤</button></div>';
      document.getElementById('bgmnow').textContent='앞 화면 재생: '+name; return; }
    P.innerHTML='<iframe src="https://www.youtube-nocookie.com/embed/'+c.dataset.id+'?autoplay=1&rel=0" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>';
    document.getElementById('bgmnow').textContent='이 화면 재생: '+name; };
  bgmMode();
});
</script>""")


BGM_CSS = """
#bgmbox{display:none;position:fixed;top:var(--navh,88px);left:190px;right:0;bottom:0;z-index:25;background:#0f172a;overflow:auto;padding:16px 20px}
body.bgm #bgmbox{display:block}body.pv #bgmbox{z-index:60;left:0}body.pr #bgmbox{display:none!important}
.bgmh{display:flex;align-items:center;gap:12px;margin-bottom:12px}.bgmh b{font-size:18px}#bgmnow{flex:1;color:#f6c76b;font-size:13px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.bgmx{font:700 13px inherit;border:0;border-radius:999px;padding:7px 14px;background:#fff;color:#111;cursor:pointer}
#bgmmode{color:#cbd5e1;font-size:13.5px;margin:-4px 0 12px}#bgmmode .bgmx{margin-left:8px}
.bgmon{display:flex;align-items:center;gap:12px;justify-content:center;background:#1e293b;border:1px solid #f6c76b;border-radius:10px;padding:18px;margin:0 auto 14px;max-width:960px;font-weight:700;color:#f6c76b}
#bgmplay iframe{width:min(100%,960px);aspect-ratio:16/9;border:0;border-radius:10px;display:block;margin:0 auto 14px;background:#000}
.bgml{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.bgmc{display:flex;flex-direction:column;gap:6px;text-align:left;border:2px solid transparent;border-radius:10px;background:#1e293b;color:#e2e8f0;padding:6px;cursor:pointer;font:600 13.5px inherit}
.bgmc:hover{border-color:#475569}.bgmc.on{border-color:#f6c76b}.bgmc img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:6px}
.bgmc span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.bgmc small{color:#94a3b8;font-weight:400}
.bgmnote{color:#94a3b8;font-size:12.5px}#toc a.bgm{margin-top:8px;border-top:1px solid #1e293b;color:#f6c76b}
@media (max-width:760px){#bgmbox{left:0}}
"""

# ── 💬 예배팀 소통 — PPT 왼쪽 목차 아래 채팅. 체크 안 한 메시지는 상단 메뉴 전광판에서 깜빡이며 번갈아 (2026-10-04 교장님) ──
CHAT_HTML = ('<div id="chat"><div class="chh">💬 예배팀 소통</div>'
             '<div class="chin"><textarea id="chtx" rows="2" placeholder="메시지 쓰기 (Enter 발송 · Shift+Enter 줄바꿈)"></textarea>'
             '<button type="button" id="chgo">챗발송</button></div><div id="chlist"></div></div>')

CHAT_CSS = """
#chat{margin-top:10px;border-top:1px solid #1e293b;padding-top:10px}
#chat .chh{font-weight:800;color:#e2e8f0;padding:0 4px 6px}
#chat .chin{display:flex;flex-direction:column;gap:6px}
#chtx{width:100%;box-sizing:border-box;resize:vertical;min-height:52px;font:14px 'Pretendard Variable',sans-serif;border:1px solid #334155;border-radius:8px;background:#0f172a;color:#fff;padding:7px 8px}
#chgo{font:800 14px 'Pretendard Variable',sans-serif;border:0;border-radius:8px;padding:8px;background:#f6c76b;color:#3b2a06;cursor:pointer}
#chlist{margin-top:8px;max-height:186px;overflow-y:auto;display:flex;flex-direction:column;gap:6px}
#chlist .cm{display:flex;gap:7px;align-items:flex-start;background:#1e293b;border-radius:8px;padding:7px 8px;font-size:13.5px;line-height:1.35;color:#f1f5f9;word-break:keep-all;overflow-wrap:anywhere}
#chlist .cm input{margin:2px 0 0;width:18px;height:18px;flex:0 0 auto;cursor:pointer;accent-color:#16a34a}
#chlist .cm small{display:block;color:#94a3b8;font-size:11px;margin-top:2px}
#chlist .none{color:#64748b;font-size:12.5px;padding:2px 4px}
body.pr #chat{display:none}
"""

CHAT_JS = r"""
(function(){
  const send=async()=>{ const ta=document.getElementById('chtx'), t=ta.value.trim(); if(!t) return;
    const b=document.getElementById('chgo'); b.disabled=true; b.textContent='보내는 중…';
    try{ const r=await fetch('/api/worship',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'chat',date:NDATE,key:NKEY,text:t})});
      const j=await r.json(); if(j.ok){ ta.value=''; if(window.wsChatReload) wsChatReload(); } else alert('발송 실패: '+(j.error||'')); }
    catch(e){ alert('발송 실패 — 인터넷 연결을 확인해 주세요'); }
    b.disabled=false; b.textContent='챗발송'; };
  const hm=s=>{ try{ return new Date(s).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Seoul'}); }catch(e){ return ''; } };
  function draw(list){ const box=document.getElementById('chlist'); if(!box) return;
    const atEnd=box.scrollTop+box.clientHeight>=box.scrollHeight-4;
    box.replaceChildren();
    if(!list.length){ const n=document.createElement('div'); n.className='none'; n.textContent='확인할 메시지가 없습니다'; box.appendChild(n); return; }
    list.forEach(m=>{ const row=document.createElement('label'); row.className='cm';
      const cb=document.createElement('input'); cb.type='checkbox'; cb.title='확인 — 누르면 사라집니다';
      cb.onchange=async()=>{ row.style.opacity=.35; try{ await fetch('/api/worship',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'chatdone',date:NDATE,key:NKEY,id:m.id})}); }catch(e){} if(window.wsChatReload) wsChatReload(); };
      const tx=document.createElement('div'); tx.textContent=m.text; const t=document.createElement('small'); t.textContent=hm(m.at); tx.appendChild(t);
      row.append(cb,tx); box.appendChild(row); });
    if(atEnd||box.dataset.n!==String(list.length)) box.scrollTop=box.scrollHeight; box.dataset.n=list.length; }
  addEventListener('wschat',e=>draw(e.detail||[]));
  addEventListener('DOMContentLoaded',()=>{ const ta=document.getElementById('chtx'), b=document.getElementById('chgo'); if(!ta) return;
    b.onclick=send;
    ta.addEventListener('keydown',e=>{ e.stopPropagation(); if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){ e.preventDefault(); send(); } });
    ta.addEventListener('keyup',e=>e.stopPropagation()); });
})();
"""


def _news_globals(date: str | None) -> str:
    """교회 소식 고치기 저장 열쇠(그 주 날짜로) — api/worship.js 의 news 와 같은 계산."""
    import hmac, hashlib
    sec = next((ln.split("=", 1)[1].strip() for ln in (Path.home() / "dev/daily-briefing/.env").read_text().splitlines() if ln.startswith("JUBO_SECRET=")), "")
    key = hmac.new(sec.encode(), f"news:{date}".encode(), hashlib.sha256).hexdigest()[:32] if sec and date else ""
    return f"const NDATE='{date or ''}',NKEY='{key}';\n"


def render(slides: list[dict], title: str, dl: str, songs: list[str] | None = None, date: str | None = None) -> str:
    data = [{"img": s["img"], "texts": s["texts"]} for s in slides]
    sl = "".join(f'<section class="sl" id="s{s["n"]}" data-i="{k}"><div class="in"></div><span class="no">{s["n"]}</span></section>'
                 for k, s in enumerate(slides))
    toc = "".join(f'<a href="#s{n}" class="{"song" if name.startswith("♪") else ""}">{html.escape(name)}</a>' for n, name in outline(slides, list(songs or [])))
    import re as _re, wsnav                      # 공통 상단 메뉴 (2026-10-03 교장님: 쪽마다 상단 통일)
    m = _re.search(r"\d+월 \d+일", title)
    dls = [(("📊 PPT 받기" if h.endswith(".pptx") else "📕 PDF 받기"), h) for h in _re.findall(r'href="([^"]+)"', dl or "")]
    note = "" if dls else _re.sub(r"<[^>]+>", "", dl or "")
    sub = ('<button class="sub on" id="b-one" onclick="wsView(true)">▣ 한 장씩</button>'
           '<button class="sub" id="lbtn" onclick="wsView(false)">☰ 목록</button>'
           '<button class="sub" onclick="present()">▶ 예배용(두 화면)</button>'
           + (f'<span class="note">{html.escape(note)}</span>' if note.strip() else ""))
    if not date and m:                            # 날짜를 안 받았으면 제목(「10월 11일」)에서
        import datetime as dt
        mo, da = map(int, re.findall(r"\d+", m.group(0))); date = f"{dt.date.today().year}-{mo:02d}-{da:02d}"
    items = bgm(date) if date else []
    if items:
        toc += '<a href="#bgm" class="bgm">🎵 BGM</a>'
        sub += '<button class="sub" onclick="bgmOpen()">🎵 BGM</button>'
    toc += CHAT_HTML                              # 💬 예배팀 소통(목차 아래) — 2026-10-04 교장님
    nav = wsnav.nav("ppt", m.group(0) if m else title, sub, dls, day=date) + f"<script>{wsnav.JS}</script>" + bgm_html(items) + f"<script>{CHAT_JS}</script>"
    return PAGE.format(title=html.escape(title), n=len(slides), slides=sl, toc=toc, dl=dl, nav=nav, navcss=wsnav.CSS + BGM_CSS + CHAT_CSS,
                       data=json.dumps(data, ensure_ascii=False, separators=(",", ":")), pvjs=_news_globals(date) + PVJS)


def rewrap(slides: list[dict], pptx: Path | None) -> list[dict]:
    """PDF 는 줄마다 끊겨 있다 — 원본 PPT 의 한 문단이 여러 줄로 꺾인 것은 다시 한 덩어리로 이어,
    화면 글꼴 폭에 맞춰 자연스럽게 줄이 바뀌게 한다(2026-10-03 교장님: 오른쪽 여백이 남지 않게, 교회소식·봉독 본문).
    왼쪽 맞춤 글만. 이어 붙인 줄들이 원본 문단과 글자 그대로 같을 때만 합친다."""
    if not pptx or not Path(pptx).exists(): return slides
    from pptx import Presentation
    prs = Presentation(str(pptx))
    src = [x for x in prs.slides if not any(sh.name.startswith("songppt|") for sh in x.shapes)]   # PDF 는 곡 장을 뺀 사본에서 나온다
    flat = lambda t: re.sub(r"\s", "", t)
    for k, sl in enumerate(slides):
        if k >= len(src): break
        paras = [flat("".join(r.text for r in pa.runs)) for sh in src[k].shapes if sh.has_text_frame
                 for pa in sh.text_frame.paragraphs]
        paras = [x for x in paras if x]
        out, i, T = [], 0, sl["texts"]
        while i < len(T):
            t = dict(T[i]); j = i
            if t.get("a") == "l":
                acc = flat(t["t"])
                while (j + 1 < len(T) and T[j + 1].get("a") == "l" and abs(T[j + 1]["x"] - t["x"]) < 6 and abs(T[j + 1]["s"] - t["s"]) < 1
                       and acc not in paras and any(p.startswith(acc + flat(T[j + 1]["t"])) for p in paras)):
                    j += 1; acc += flat(T[j]["t"])
                if j > i and acc in paras:
                    seg = T[i:j + 1]
                    t["t"] = " ".join(x["t"].strip() for x in seg)
                    t["b"] = any(x["b"] for x in seg)
                    t["lh"] = round((seg[-1]["y"] - seg[0]["y"]) / (len(seg) - 1) / t["s"], 2)
                    t["w"] = max(max(x["w"] for x in seg), sl["w"] - 2 * t["x"])     # 칸 폭(좌우 같은 여백)까지
                    t["h"] = seg[-1]["y"] + seg[-1]["h"] - t["y"]
                    t["wrap"] = 1
                else:
                    j = i
            out.append(t); i = j + 1
        sl["texts"] = out
        sl["plain"] = " ".join(x["t"] for x in out)
    return slides


def add_song_frames(slides: list[dict], date: str, out: Path) -> list[dict]:
    """예배 PPT 에 가사 슬라이드가 아직 없을 때 — 찬양과경배·찬양과결단 표지 바로 뒤에 곡마다 틀 한 장(곡 제목 + 악보)을 끼운다
    (2026-10-03 교장님 지시: 9/27 예배 PPT 처럼 곡마다 자리가 있게). 표지 뒤에 이미 가사 장이 있으면 손대지 않는다."""
    from PIL import Image
    try:
        d = json.loads((HERE / "data" / f"{date}.json").read_text()).get("songs", {})
    except Exception:
        return slides
    songs = [(lab, x) for g, name in (("intro", "도입곡"), ("main", ""), ("apply", "적용송"))
             for i, x in enumerate(d.get(g, [])) for lab in [name or str(i + 1)]]
    flat = lambda s: re.sub(r"\s", "", s["plain"])[:40]
    is_div = lambda s: ("찬양과경배" in flat(s) or "찬양과결단" in flat(s)) and len(re.sub(r"\s", "", s["plain"])) < 160
    is_sec = lambda s: any(x in flat(s) for x in SECTIONS)   # 다음 장이 곧바로 다른 순서 표지 = 가사 장 없음
    divs = [k for k, s in enumerate(slides) if is_div(s)]
    empty = [k for k in divs if k + 1 >= len(slides) or is_sec(slides[k + 1])]
    if not songs or len(empty) < len(divs):   # 가사 장이 이미 들어 있는 PPT
        return slides
    W, H = int(slides[0]["w"]), int(slides[0]["h"])
    for f in out.glob("song_*.jpg"): f.unlink()
    res, si = [], 0
    for k, s in enumerate(slides):
        res.append(s)
        if k in divs and si < len(songs):
            lab, x = songs[si]; si += 1
            got = song_slides(x.get("title", ""), si, W, H, out)       # 곡별 PPT DB 에 있으면 그 곡의 장을 모두
            if got:
                res += got; continue
            name = f"frame_{si:02d}.jpg"
            cv = Image.new("RGB", (W, H), "white")
            if x.get("img") and (HERE / x["img"]).exists():
                im = Image.open(HERE / x["img"]).convert("RGB")
                bw, bh = W - 80, H - 130
                r = min(bw / im.width, bh / im.height); im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
                cv.paste(im, ((W - im.width) // 2, 110 + (bh - im.height) // 2))
            cv.save(out / name, "JPEG", quality=85)
            title = ("♬ " + (lab + ". " if lab.isdigit() else lab + " · ") + (x.get("title") or "곡 미정"))
            texts = [{"x": 40, "y": 30, "w": W - 80, "h": 60, "s": 48, "c": "#6b5444", "b": True, "t": title, "a": "c"}]
            if not x.get("img"):
                texts.append({"x": 40, "y": H // 2, "w": W - 80, "h": 40, "s": 32, "c": "#9ca3af", "b": False, "t": "악보·가사 준비 중", "a": "c"})
            res.append({"n": 0, "w": W, "h": H, "img": name, "texts": texts, "plain": x.get("title", ""), "hidden": x.get("title", "")})
    for n, s in enumerate(res, 1): s["n"] = n
    return res


def song_slides(title: str, si: int, W: int, H: int, out: Path) -> list[dict]:
    """곡별 PPT DB(songppt/db)에서 곡을 찾아 예배 PPT 장으로 — 악보 그림 + 자막 바탕(검정)은 그림에, 자막 글은 글자로
    (2026-10-03 교장님 지시: 콘티 순서대로 찬양 자리에 곡 PPT 를 자동으로)."""
    import base64, io
    from PIL import Image, ImageDraw
    sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
    try:
        import songppt, store
        t = store.song_find(title)                                # 곡별 PPT 는 예배 DB + 그림 창고에서
        song = store.song_load(t) if t else None
        if not song: return []
    except Exception:
        return []
    CW, CH = 1920, 1080; kx, ky = W / CW, H / CH
    res = []
    for j, sl in enumerate(song["slides"], 1):
        cv = Image.new("RGB", (CW, CH), "white")
        im = Image.open(io.BytesIO(base64.b64decode(sl["img"]))).convert("RGBA")
        x, y, w, h = sl["pic"]
        im = im.resize((max(1, w), max(1, h)))
        cv.paste(im, (x, y), im)
        texts = []
        lay = songppt.sub_layout(sl.get("sub"))           # 자막 통일: 아래 띠 20% — 위 절반 러시아어(노랑)·아래 절반 영어(흰색)
        if lay:
            bx, by, bw, bh = lay["box"]
            ImageDraw.Draw(cv).rectangle([bx, by, bx + bw, by + bh], fill=lay["fill"])
            for ln in lay["lines"]:
                texts.append({"x": round(ln["x"] * kx), "y": round(ln["y"] * ky), "w": round(ln["w"] * kx), "h": round(ln["size"] * ky),
                              "s": round(ln["size"] * ky, 1), "c": ln["c"], "b": True, "t": ln["t"], "a": "c"})
        name = f"song_{si:02d}_{j:02d}.jpg"
        cv.save(out / name, "JPEG", quality=85)
        res.append({"n": 0, "w": W, "h": H, "img": name, "texts": texts, "plain": t, "hidden": t, "song": t})
    return res


def add_extra(slides: list[dict], date: str, out: Path | None = None) -> list[dict]:
    """그 주에만 끼우는 순서 장 — data/<날짜>.json 의 ppt_extra (2026-10-03 교장님 지시: 특송 다음 「선교 보고 · 디마 선교사」).
    [{"after": "SpecialPraise", "base": "ScriptureReading", "label": "Mission Report", "title": "선교 보고", "name": "디마 선교사"}]
    base 장(제목 상자 크기가 맞는 순서 표지)의 배경을 빌려 글자만 바꾼다. after 장 바로 뒤에 넣는다."""
    try:
        extra = json.loads((HERE / "data" / f"{date}.json").read_text()).get("ppt_extra", [])
    except Exception:
        return slides
    flat = lambda s: re.sub(r"\s", "", s["plain"])
    for x in extra:
        base = next((s for s in slides if flat(s).startswith(x.get("base", "ScriptureReading"))), None)
        k = next((i for i, s in enumerate(slides) if flat(s).startswith(x["after"])), None)
        if base is None or k is None: continue
        s = json.loads(json.dumps(base)); texts = []
        for t in s["texts"]:
            if t["s"] >= 100: val = x.get("title", "")
            elif t["s"] < 30 and t["y"] < 300: val = x.get("label", "")
            elif 40 <= t["s"] < 100: val = x.get("name", "")
            else: val = x.get("sub", "")
            if not val: continue
            cx = t["x"] + t["w"] / 2; w = t["w"] * max(1.0, len(val) / max(1, len(t["t"])))
            texts.append({**t, "t": val, "w": int(w), "x": int(cx - w / 2)})
        s.update(texts=texts, plain=" ".join(t["t"] for t in texts), hidden="")
        add = [s]
        # 보고 자료(PDF)가 있으면 장마다 그림 한 장씩 표지 뒤에 이어 붙인다 — 글자까지 원본 그대로 (2026-10-03 디마 선교사 몽골 단기선교 보고)
        src = HERE / "extra" / date / x["pdf"] if x.get("pdf") else None
        if src and src.exists() and out is not None:
            import fitz
            doc = fitz.open(src); tag = re.sub(r"\W", "", x.get("name", "extra"))[:8] or "extra"
            for i, pg in enumerate(doc, 1):
                name = f"x_{tag}_{i:02d}.jpg"
                pg.get_pixmap(matrix=fitz.Matrix(1920 / pg.rect.width, 1920 / pg.rect.width)).save(str(out / name), jpg_quality=88)
                add.append({"n": 0, "w": s["w"], "h": s["h"], "img": name, "texts": [], "plain": "", "hidden": ""})
        slides[k + 1:k + 1] = add
    for n, s in enumerate(slides, 1): s["n"] = n
    return slides


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
    slides = rewrap(slides, pptx)
    import fitz                                   # 모음 쪽(jegok_worship) 「오늘」 칸에 쓸 첫 장 그림(글자까지 그대로)
    fitz.open(pdf)[0].get_pixmap(dpi=110).save(str(folder / "cover.jpg"))
    slides = add_song_frames(slides, date, folder / "slides")
    slides = add_extra(slides, date, folder / "slides")
    shutil.copy(pdf, folder / "worship.pdf")
    dl = '<a href="worship.pdf" download="{0} 주일예배 PPT.pdf">⬇ PDF</a>'.format(date)
    if pptx:
        shutil.copy(pptx, folder / "worship.pptx")
        dl = f'<a href="worship.pptx" download="{date} 주일예배 PPT.pptx">⬇ PPT</a>' + dl
    title = f"{int(date[5:7])}월 {int(date[8:10])}일 주일예배 PPT"
    (folder / "ppt.html").write_text(render(slides, title, dl, song_titles(date), date=date))
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
    import pptfill                                   # 곡 장(악보)까지 든 PPT 는 구글 내보내기 한도를 넘는다 — 곡 장을 뺀 사본으로 PDF
    base = pptfill.base_copy(px, px.with_name(px.stem + ".base.pptx"))
    try:
        pptfill.to_pdf(base, pdf)
    finally:
        base.unlink(missing_ok=True)
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
