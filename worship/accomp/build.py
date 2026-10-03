#!/usr/bin/env python3
"""예배자 악보(옛 이름 반주자·싱어용 악보) — data/<날짜>.json → out/<날짜>.html (2026-10-03 교장님 지시).

쪽마다 구획(slot)이 있어 말로 고치거나 악보를 주시면 그 자리에 넣는다.
  python3 accomp/build.py 2026-09-27            # 만들기
  python3 accomp/build.py 2026-09-27 --open     # 만들고 열기
  python3 accomp/build.py 2026-10-04 --share    # 게시: …/jegok_worship_20261004 + 모음 …/jegok_worship + 노션 (publish.py)

쪽 종류(type): cover 표지 · roster 섬김표 · recite 암송 · sermon_text 설교본문 · sermon_summary 설교요약
              · creed 사도신경 · scores 악보(왼쪽 L / 오른쪽 R 두 칸)
악보 칸: {"side": "L", "title": "곡 제목", "img": "scores/<날짜>/파일.png"} — img 가 비면 빈 구획으로 보인다.
"""
from __future__ import annotations
import base64, html, json, re, subprocess, sys
from pathlib import Path

import wsnav  # 예배 주간 쪽 공통 상단 메뉴 (2026-10-03)
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
.sup{margin-top:2.5mm;border:1.5px dashed #94a3b8;border-radius:3mm;padding:2.4mm 4mm;display:flex;gap:5mm;align-items:center}
.sup-h{white-space:nowrap}.sup-h b{display:inline;margin-right:1.5mm;font-size:15pt;color:#0b1430}.sup-h span{font-size:8.5pt;color:#64748b}
.notice{flex:1;min-height:0;margin-top:2.5mm;border:1.5px solid #cbd5e1;background:#f8fafc;border-radius:3mm;padding:3mm 5mm;overflow:hidden}.notice b{font-size:13pt;color:#0b1430}.notice ul{margin:1.5mm 0 0;padding-left:5mm}.notice li{font-size:12pt;line-height:1.55;color:#1f2937}
.sup-n{display:flex;flex-wrap:wrap;gap:1mm 1.2mm}.sup-n .nm{background:#f1f5f9}
/* 글 쪽 */
.textpage{padding:8mm 10mm;height:100%;display:flex;flex-direction:column}
.textpage h2{margin:0 0 4mm;font-size:22pt}
.textpage .body{flex:1;min-height:0;overflow:hidden;line-height:1.45}
.red{color:#dc2626;font-style:normal}
.verses{line-height:1.75}
.focus{font-weight:800;color:#9d174d;background:#fdf2f6;box-shadow:0 0 0 1.2mm #fdf2f6;border-radius:1mm}
.sm-head{background:#e8edf8;border-left:2mm solid #1e3a8a;border-radius:2mm;padding:2.6mm 4mm;margin-bottom:4mm;flex:0 0 auto}.sm-head b{display:block;font-size:21pt;color:#0b1430}.sm-head span{font-size:14pt;color:#334155;font-weight:600}
.creed{padding:9mm 14mm}.creed h2{font-size:32pt;margin-bottom:6mm}.creed .body{white-space:nowrap;line-height:1.62;font-weight:600;letter-spacing:-.01em}
.vn{color:#1e3a8a;margin-right:1.5mm}
.sermon-head{display:flex;gap:6mm;align-items:baseline}
.sermon-head{border-bottom:2px solid #1e3a8a;padding-bottom:2mm;margin-bottom:4mm}.sermon-head h2{margin:0;font-size:24pt}.sermon-head .ref{font-size:22pt;font-weight:800}.sermon-head .tt{font-size:22pt;font-weight:800;color:#1e3a8a;margin-left:auto}
.col{position:absolute;top:0;bottom:0;width:50%;padding:7mm 9mm}
.col .body{height:100%;overflow:hidden;line-height:1.5}
/* 악보 칸 */
.slot{position:absolute;inset:1mm;display:flex;flex-direction:column}
.slot img{width:100%;flex:1;min-height:0;object-fit:contain;object-position:top center}
.slot.empty{border:2px dashed #93c5fd;border-radius:3mm;align-items:center;justify-content:center;color:#3b82f6;background:#f8fbff}
.slot.empty b{font-size:16pt}.slot.empty span{font-size:10pt;margin-top:2mm;color:#64748b}
.shead{flex:0 0 auto;display:flex;align-items:center;gap:2.5mm;padding:0 0 1mm 0}.shead .stt{font-size:11pt;font-weight:700;color:#1e3a8a}
.slot .badge{position:static;align-self:flex-start;flex:0 0 auto;min-width:11mm;text-align:center;font-size:13pt;font-weight:900;color:#fff;background:#1e3a8a;border-radius:2mm;padding:.8mm 3.5mm}
.slot.empty .badge{position:absolute;left:0;top:0}
.slot .st{position:absolute;left:0;bottom:0;font-size:8pt;color:#fff;background:rgba(37,99,235,.85);padding:.5mm 2mm;border-radius:0 2mm 0 0}
@media print{
  body{background:#fff}.bar,.tag,.slot .st{display:none}
.slot.empty .badge{position:absolute;left:0;top:0}
.slot .st{display:none}
  html,body{margin:0!important;padding:0!important;width:297mm}
  .pages{display:block;padding:0}.page{box-shadow:none;break-after:page;zoom:1!important;margin:0!important;transform:none!important}   /* 화면 맞춤 축소(zoom)가 인쇄에 남아 왼쪽 위로 쏠리던 것 (2026-10-03) */
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
#rail{width:var(--rw,210px);flex:0 0 var(--rw,210px);overflow-y:auto;background:#f8fafc;border-right:1px solid #d1d5db;padding:10px 12px 40px}
.th{position:relative;display:flex;gap:6px;margin-bottom:10px;cursor:pointer}
.th .n{font-size:12px;color:#64748b;width:16px;text-align:right;padding-top:2px}
.th .box{width:168px;height:118.8px;overflow:hidden;border-radius:4px;border:2px solid transparent;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.15)}
.th.cur .box{border-color:#2563eb}
.th .box .page{transform-origin:0 0;box-shadow:none}
/* 썸네일·큰 화면 사이 손잡이 — 끌어서 폭 조절, 좁히면 썸네일이 작아진다 (2026-10-03 교장님 지시) */
#split{flex:0 0 8px;cursor:col-resize;background:#e5e7eb;border-left:1px solid #d1d5db;border-right:1px solid #d1d5db;position:relative;touch-action:none}
#split::after{content:'';position:absolute;left:2px;top:50%;width:2px;height:36px;margin-top:-18px;border-left:1px solid #9ca3af;border-right:1px solid #9ca3af}
#split:hover,#split.drag{background:#bfdbfe}
body.pr #split{display:none}
body.dragging,body.dragging *{cursor:col-resize!important;user-select:none!important}
#stage{flex:1;position:relative;overflow:hidden;display:flex;align-items:center;justify-content:center}
#stage .page{transform-origin:center center;flex:0 0 auto}
#hint{position:absolute;right:14px;bottom:10px;font-size:12px;color:#64748b}
body.pr{background:#000}
body.pr .bar,body.pr #rail,body.pr #hint,body.pr .dlbar{display:none!important}
body.pr #sv{inset:0;background:#000}
body.pr #stage .page{box-shadow:none}
body.pr .tag,body.sv #stage .tag{display:none}
#pn{position:absolute;left:50%;bottom:8px;transform:translateX(-50%);font-size:12px;color:#9ca3af;display:none}
body.pr #pn{display:block}
@media print{#sv{display:none!important}body.sv .pages,body.pr .pages{display:block!important}}
.bar b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.bar .btns{display:flex;gap:8px;flex:0 0 auto}
.bar button{white-space:nowrap}
/* 휴대폰: 제목 한 줄 + 아래 줄에 단추 4개 한 줄, 스크롤해도 위에 고정 (2026-10-03 교장님 지시) */
@media screen and (max-width:700px){
  .bar{position:sticky;top:0;flex-wrap:wrap;gap:6px;padding:7px 10px}
  .bar b{flex:1 0 100%;font-size:13px;margin:0}
  .bar .btns{flex:1 0 100%;display:grid;grid-template-columns:repeat(5,1fr);gap:5px}
  .bar button{font-size:12px;padding:7px 1px;width:100%}
}
/* 🔒 준비 — 준비자만 비밀번호로 여는 후보 악보함 (2026-10-03 교장님 지시) */
#prep{display:none;position:fixed;left:0;right:0;bottom:0;top:44px;z-index:8;overflow:auto;background:#eef1f5}
body.prep{overflow:hidden}body.prep #prep{display:block}
#prep .lock{max-width:340px;margin:12vh auto 0;background:#fff;border-radius:14px;padding:26px 22px;box-shadow:0 6px 24px rgba(0,0,0,.12);text-align:center}
#prep .lock h3{margin:0 0 6px;font-size:18px}#prep .lock p{margin:0 0 16px;color:#64748b;font-size:13px}
#prep .lock input{width:100%;font:inherit;font-size:18px;padding:10px 12px;border:1.5px solid #cbd5e1;border-radius:10px;text-align:center;letter-spacing:.2em}
#prep .lock button{margin-top:10px;width:100%;font:inherit;font-weight:800;border:0;border-radius:10px;padding:11px;background:#1e3a8a;color:#fff;cursor:pointer}
#prep .lock .err{color:#b91c1c;font-size:13px;min-height:18px;margin-top:8px}
#prep .in{padding:16px 18px 60px;max-width:1500px;margin:0 auto}
#prep .ph{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;margin-bottom:12px}
#prep .ph h3{margin:0;font-size:18px}#prep .ph .now{font-size:13px;color:#475569}
#prep .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
#prep .card{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.12);overflow:hidden;cursor:zoom-in}
#prep .card .ct{display:flex;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid #e5e7eb;font-weight:700;font-size:14px}
#prep .card .ct i{font-style:normal;font-size:12px;color:#fff;background:#7c3aed;border-radius:6px;padding:2px 7px}
#prep .card .ct u{text-decoration:none;font-size:11px;color:#0e7490;background:#e6f7fa;border-radius:6px;padding:2px 6px;margin-left:auto}
#prep .card img{display:block;width:100%;height:auto}
#prep .empty{color:#64748b;text-align:center;padding:60px 0}
#prep .conti{margin-top:22px;background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
#prep .conti h3{margin:0 0 6px;font-size:16px}#prep .conti .th{margin:0 0 8px;color:#475569;font-size:13px}
#prep .conti .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}#prep .conti h4{margin:6px 0;font-size:14px;color:#1e3a8a}
#prep .conti .tp i{font-style:normal;font-size:12px;font-weight:700;color:#b45309}#prep .conti ol{margin:4px 0 10px;padding-left:22px;font-size:14px;line-height:1.7}
#prep .conti a{color:#1d4ed8;text-decoration:none}#prep .conti a.sh{font-size:12px;color:#64748b;border:1px solid #cbd5e1;border-radius:6px;padding:0 5px;margin-left:4px}
#prep .conti .empty{padding:20px 0}
#zoom{display:none;position:fixed;inset:0;z-index:60;background:rgba(15,23,42,.92);overflow:auto;cursor:zoom-out}
#zoom img{display:block;max-width:min(1100px,100%);margin:20px auto;background:#fff}
@media print{#prep,#zoom{display:none!important}}
.rt .nm.off{opacity:.32;filter:grayscale(1)}
.shead .skey{flex:0 0 auto;font:900 12pt/1 inherit;color:#1e3a8a;background:#dbeafe;border:1px solid #93c5fd;border-radius:1.6mm;padding:.8mm 2.2mm}
.shead .skeys{display:inline-flex;align-items:center;gap:1mm}.shead .karr{font-weight:900;color:#1e3a8a}
.shead button.skey{cursor:pointer;opacity:.55}.shead button.skey.on{opacity:1;background:#1e3a8a;color:#fff;border-color:#1e3a8a}
.slot img.kalt{display:none}
@media print{.shead button.skey{opacity:1}}
.shead a.stt{text-decoration:underline;text-decoration-color:#93c5fd;text-underline-offset:2px}.shead a.stt .yt{font-size:8pt;color:#dc2626}
@media print{.shead a.stt{text-decoration:none}.shead a.stt .yt{display:none}}
@media screen and (max-width:1150px){.page{zoom:calc(100vw / 1150px)}}
"""

VIEW = r"""
// 슬라이드 보기(왼쪽 작은 쪽 목록 + 오른쪽 큰 쪽) · 발표(전체 화면) — ←→ ↑↓ 스페이스 PgUp/PgDn, Esc 나가기
(function(){
  const pages=[...document.querySelectorAll('.pages > .page')];
  const rail=document.getElementById('rail'), stage=document.getElementById('stage'), pn=document.getElementById('pn');
  const PW=pages[0].offsetWidth, PH=pages[0].offsetHeight;
  let cur=0, built=false, big=null;
  const sv=document.getElementById('sv'), split=document.getElementById('split');
  let RW=+localStorage.getItem('ws_rw')||210;
  function thumbs(){  // 썸네일 칸 폭에 맞춰 작은 쪽 크기를 다시 맞춘다
    sv.style.setProperty('--rw',RW+'px');
    const w=Math.max(40,RW-24-22), s=(w-4)/PW;
    rail.querySelectorAll('.th .box').forEach(b=>{b.style.width=w+'px';b.style.height=(PH*s+4)+'px';
      const c=b.firstElementChild; if(c) c.style.transform='scale('+s+')';});
  }
  function build(){
    if(built) return; built=true;
    pages.forEach((p,i)=>{
      const t=document.createElement('div'); t.className='th'; t.innerHTML='<span class="n">'+(i+1)+'</span><div class="box"></div>';
      const c=p.cloneNode(true); c.removeAttribute('id');
      t.querySelector('.box').appendChild(c); t.onclick=()=>go(i); rail.appendChild(t);
    });
    thumbs();
  }
  split.addEventListener('pointerdown',e=>{
    e.preventDefault(); try{split.setPointerCapture(e.pointerId)}catch(_){} split.classList.add('drag'); document.body.classList.add('dragging');
    const x0=e.clientX, r0=RW;
    function mv(ev){RW=Math.round(Math.max(90,Math.min(innerWidth*0.6,r0+ev.clientX-x0))); thumbs(); fit();}
    function up(){split.removeEventListener('pointermove',mv);split.removeEventListener('pointerup',up);split.removeEventListener('pointercancel',up);
      split.classList.remove('drag');document.body.classList.remove('dragging');localStorage.setItem('ws_rw',RW);
      const th=rail.children[cur]; if(th) th.scrollIntoView({block:'nearest'});}
    split.addEventListener('pointermove',mv); split.addEventListener('pointerup',up); split.addEventListener('pointercancel',up);
  });
  split.addEventListener('dblclick',()=>{RW=210;localStorage.setItem('ws_rw',RW);thumbs();fit();});
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
  // 공유본은 맨 위에 다운로드 단추 줄(.dlbar)이 따로 붙는다 — 우리 막대는 그 바로 아래에 붙어 함께 고정
  function stick(){const dl=document.querySelector('.dlbar'),bar=document.querySelector('.bar');if(bar)bar.style.top=(dl?dl.offsetHeight:0)+'px'}
  stick(); addEventListener('resize',stick);
  document.addEventListener('keydown',e=>{
    const on=document.body.classList.contains('sv')||document.body.classList.contains('pr');
    if(!on) return;
    if(['ArrowRight','ArrowDown','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();go(cur+1)}
    else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(e.key)){e.preventDefault();go(cur-1)}
    else if(e.key==='Home') go(0); else if(e.key==='End') go(pages.length-1);
    else if(e.key==='Escape') mode('doc');
  });
  stage.addEventListener('click',e=>{ if(!document.body.classList.contains('pr')) return;
    go(cur+(e.clientX>innerWidth/2?1:-1)); });
  let x0=null; stage.addEventListener('touchstart',e=>x0=e.touches[0].clientX,{passive:true});
  stage.addEventListener('touchend',e=>{ if(x0===null) return; const dx=e.changedTouches[0].clientX-x0; if(Math.abs(dx)>40) go(cur+(dx<0?1:-1)); x0=null; });
  document.addEventListener('fullscreenchange',()=>{ if(!document.fullscreenElement && document.body.classList.contains('pr')) mode('doc'); });
  addEventListener('resize',fit);
  const start=()=>{ if(location.hash==='#slides') mode('sv'); else if(location.hash==='#present') mode('pr'); };
  (document.fonts?document.fonts.ready:Promise.resolve()).then(start);
})();
"""

PREP = r"""
// 🔒 준비 — 비밀번호로 후보 악보를 푼다(PBKDF2+AES-GCM, seal.mjs 와 같은 방식). 한 번 맞히면 이 창을 닫을 때까지 기억
(function(){
  const box=JSON.parse(document.getElementById('prep-box').textContent), P=document.getElementById('prep');
  const lock=P.querySelector('.lock'), inner=P.querySelector('.in'), err=document.getElementById('prep-err'), zoom=document.getElementById('zoom');
  const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  async function open(pw){
    const base=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
    const key=await crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt:b64(box.salt),iterations:box.it},base,{name:'AES-GCM',length:256},false,['decrypt']);
    const t=new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(box.iv)},key,b64(box.ct)));
    inner.innerHTML=t; inner.hidden=false; lock.hidden=true; if(window.wsBoardInit) wsBoardInit(inner);
    inner.querySelectorAll('.card').forEach(c=>c.onclick=()=>{zoom.innerHTML='';zoom.appendChild(c.querySelector('img').cloneNode());zoom.style.display='block';zoom.scrollTop=0});
  }
  zoom.onclick=()=>{zoom.style.display='none'};
  window.wsUnlock=async e=>{ e.preventDefault(); const pw=document.getElementById('prep-pw').value.trim(); err.textContent='';
    try{ await open(pw); sessionStorage.setItem('ws_prep',pw); }catch(_){ err.textContent='비밀번호가 맞지 않습니다'; } };
  window.wsPrep=()=>{
    if(document.body.classList.contains('prep')){ wsMode('doc'); return; }
    wsMode('doc'); document.body.classList.add('prep');
    document.querySelectorAll('.bar [data-mode]').forEach(b=>b.classList.toggle('on',b.dataset.mode==='prep'));
    const bar=document.querySelector('.bar'); P.style.top=Math.max(0,bar.getBoundingClientRect().bottom)+'px';
    const pw=sessionStorage.getItem('ws_prep');
    if(inner.hidden && pw) open(pw).catch(()=>sessionStorage.removeItem('ws_prep'));
    if(inner.hidden) setTimeout(()=>document.getElementById('prep-pw').focus(),50);
  };
  const m0=window.wsMode; window.wsMode=x=>{ document.body.classList.remove('prep'); zoom.style.display='none'; m0(x); };
  if(location.hash==='#prep') wsPrep();
})();
"""

BOARD = r"""
// 🎼 콘티 편집판 (2026-10-03 교장님) — 악보 카드를 끌어 도입곡·진행곡·적용곡·후보함 사이를 옮기고(놓은 자리의 카드는 밀림),
// 칸을 누른 뒤 ⌘V 로 악보 그림을 붙여 넣고, 악보 DB 에서 찾아 넣고, 「확정 저장」 → 예배 DB → 맥미니가 악보집·예배 PPT 를 다시 만든다.
(function(){
  const css=`#board{margin:12px 0 18px}#board .bd-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
  #board .bd-top b{font-size:16px}#board .bd-msg{font-size:13px;color:#475569;flex:1}
  #board .bd-save{font:800 14px inherit;border:0;border-radius:10px;padding:9px 16px;background:#16a34a;color:#fff;cursor:pointer}
  #board .bd-row{display:grid;grid-template-columns:1fr 3fr 1fr;gap:8px}
  #board .zone{background:#fff;border:2px solid #cbd5e1;border-radius:12px;padding:6px;min-height:140px}
  #board .zone.act{border-color:#e8a33c;box-shadow:0 0 0 3px rgba(232,163,60,.2)}
  #board .zone h5{margin:2px 4px 6px;font-size:14px;color:#1e3a8a}#board .zone h5 small{font-weight:400;color:#64748b;font-size:11.5px}
  #board .zc{display:flex;flex-wrap:wrap;gap:6px;min-height:100px}#board .pool{margin-top:8px}
  #board .cd{position:relative;width:118px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:4px;cursor:grab;user-select:none}
  #board .cd img{width:100%;height:120px;object-fit:contain;background:#fff;display:block;pointer-events:none}
  #board .cd .ct{font-size:11.5px;line-height:1.3;margin-top:3px;word-break:keep-all}#board .cd .ct i{font-style:normal;font-weight:800;color:#b45309;margin-right:3px}
  #board .cd .ct b{color:#1e3a8a;margin-left:3px}
  #board .cd .x{position:absolute;right:2px;top:2px;border:0;border-radius:999px;width:22px;height:22px;background:rgba(15,23,42,.65);color:#fff;cursor:pointer;font-size:12px}
  #board .cd .hd{position:absolute;left:2px;top:2px;width:26px;height:26px;border-radius:6px;background:rgba(232,163,60,.9);color:#fff;text-align:center;line-height:26px;font-size:14px;touch-action:none;cursor:grab}
  #board .cd.mark{box-shadow:-4px 0 0 #e8a33c}#board .zc.mark-end{box-shadow:inset -4px 0 0 #e8a33c}
  .bd-ghost{position:fixed;z-index:9999;pointer-events:none;opacity:.85;transform:rotate(2deg);width:118px}
  #board .bd-find{margin-top:10px;background:#fff;border-radius:12px;padding:8px}#board .bd-find input{width:100%;font-size:15px;padding:8px 12px;border:1px solid #cbd5e1;border-radius:10px}
  #board .bd-res{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}#board .bd-res .cd{cursor:pointer}
  @media(max-width:700px){#board .bd-row{grid-template-columns:1fr}#board .cd{width:30%}#board .cd img{height:100px}}`;
  const st=document.createElement('style'); st.textContent=css; document.head.appendChild(st);
  const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const ZN={intro:'도입',main:'',apply:'적용',pool:'후보'};
  window.wsBoardInit=function(root){
    const B=root.querySelector('#board'); if(!B||B.dataset.ready) return; B.dataset.ready=1;
    const DATE=B.dataset.date, KEY=B.dataset.key; let S={intro:[],main:[],apply:[],pool:[]}, dirty=false, active='pool', rev=0;
    B.innerHTML=`<div class="bd-top"><b>🎼 콘티 편집판</b><span class="bd-msg"></span><button class="bd-save">💾 확정 저장</button></div>
      <div class="bd-row"><div class="zone" data-z="intro"><h5>도입곡</h5><div class="zc"></div></div>
      <div class="zone" data-z="main"><h5>진행곡</h5><div class="zc"></div></div><div class="zone" data-z="apply"><h5>적용곡</h5><div class="zc"></div></div></div>
      <div class="zone pool" data-z="pool"><h5>후보함 <small>카드를 끌어 위 칸에 놓으면 그 자리 카드가 밀립니다 · 칸을 누르고 ⌘V(붙여넣기)로 악보 그림 넣기 · ✕ 는 후보함으로</small></h5><div class="zc"></div></div>
      <div class="bd-find"><input placeholder="🔍 악보 찾기 — 곡명을 넣으면 악보 DB(1,375장)에서 찾아 누른 칸에 넣습니다"><div class="bd-res"></div></div>`;
    const msg=t=>{B.querySelector('.bd-msg').textContent=t;};
    const zoneEl=z=>B.querySelector(`.zone[data-z="${z}"]`);
    function setActive(z){active=z; B.querySelectorAll('.zone').forEach(e=>e.classList.toggle('act',e.dataset.z===z));}
    function card(x,z,i){ const lab=z==='main'?(i+1)+'번':ZN[z];
      return `<div class="cd" data-z="${z}" data-i="${i}"><span class="hd" title="끌어 옮기기">⠿</span><img src="${esc(x.img)}" alt="" loading="lazy">
        <div class="ct"><i>${lab}</i>${esc(x.title||'제목 미정')}${x.key?'<b>'+esc(x.key)+'</b>':''}</div><button class="x" title="${z==='pool'?'빼기':'후보함으로'}">✕</button></div>`; }
    function render(){ ['intro','main','apply','pool'].forEach(z=>{ zoneEl(z).querySelector('.zc').innerHTML=S[z].map((x,i)=>card(x,z,i)).join('')||'<div style="color:#94a3b8;font-size:12px;padding:8px">비어 있음</div>'; }); }
    function move(z0,i0,z1,i1){ const [it]=S[z0].splice(i0,1); if(z0===z1&&i0<i1) i1--; S[z1].splice(Math.max(0,Math.min(i1,S[z1].length)),0,it); dirty=true; render(); msg('바뀐 순서가 있습니다 — 💾 확정 저장을 눌러 주세요'); }
    // 끌기 — 마우스는 카드 어디든, 손가락은 ⠿ 손잡이로
    let drag=null;
    B.addEventListener('pointerdown',e=>{ const c=e.target.closest('.cd'); if(!c||e.target.closest('.x')||!c.closest('.zone')) return;
      if(e.pointerType!=='mouse'&&!e.target.closest('.hd')) return;
      drag={c,z:c.dataset.z,i:+c.dataset.i,x:e.clientX,y:e.clientY,on:false,id:e.pointerId}; });
    function target(x,y){ const el=document.elementFromPoint(x,y); const zn=el&&el.closest('.zone'); if(!zn) return null;
      const cs=[...zn.querySelectorAll('.cd')]; let idx=cs.length;
      for(let k=0;k<cs.length;k++){ const r=cs[k].getBoundingClientRect(); if(y<r.bottom&&(x<r.left+r.width/2||y<r.top)){ idx=k; break; } }
      return {z:zn.dataset.z,i:idx,cs,zn}; }
    addEventListener('pointermove',e=>{ if(!drag||e.pointerId!==drag.id) return;
      if(!drag.on){ if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<6) return; drag.on=true; drag.g=drag.c.cloneNode(true); drag.g.className='cd bd-ghost'; document.body.appendChild(drag.g); drag.c.style.opacity=.35; }
      e.preventDefault(); drag.g.style.left=(e.clientX-55)+'px'; drag.g.style.top=(e.clientY-30)+'px';
      B.querySelectorAll('.mark,.mark-end').forEach(x=>x.classList.remove('mark','mark-end'));
      const t=target(e.clientX,e.clientY); if(t){ if(t.cs[t.i]) t.cs[t.i].classList.add('mark'); else t.zn.querySelector('.zc').classList.add('mark-end'); } },{passive:false});
    addEventListener('pointerup',e=>{ if(!drag||e.pointerId!==drag.id) return; const d=drag; drag=null;
      B.querySelectorAll('.mark,.mark-end').forEach(x=>x.classList.remove('mark','mark-end'));
      if(!d.on){ return; } d.g.remove(); d.c.style.opacity=''; const t=target(e.clientX,e.clientY); if(t) move(d.z,d.i,t.z,t.i); else render(); });
    B.addEventListener('click',e=>{ const x=e.target.closest('.x'); const zn=e.target.closest('.zone'); if(zn) setActive(zn.dataset.z);
      if(x){ const c=x.closest('.cd'), z=c.dataset.z, i=+c.dataset.i;
        if(z==='pool'){ if(confirm('후보함에서 뺄까요?')){ S.pool.splice(i,1); dirty=true; render(); msg('바뀐 것이 있습니다 — 💾 확정 저장을 눌러 주세요'); } }
        else move(z,i,'pool',S.pool.length); return; }
      const c=e.target.closest('.cd'); if(c&&c.closest('.zone')){ const z=document.getElementById('zoom'); if(z){ z.innerHTML=''; const im=new Image(); im.src=c.querySelector('img').src; z.appendChild(im); z.style.display='block'; z.scrollTop=0; } } });
    // 붙여넣기 — 누른 칸(테두리 주황)에 들어간다
    document.addEventListener('paste',async e=>{ if(!B.isConnected||!document.body.classList.contains('prep')) return;
      if(e.target&&e.target.tagName==='INPUT') return;
      const it=[...(e.clipboardData||{}).items||[]].find(i=>i.type&&i.type.startsWith('image/')); if(!it) return; e.preventDefault();
      const f=it.getAsFile(); const title=prompt('곡명을 넣어 주세요',''); if(title===null) return; const mk=prompt('코드(예: G, A, Bb) — 모르면 비워 두세요','');
      msg('그림을 올리는 중…');
      const img=await new Promise(r=>{ const u=URL.createObjectURL(f), im=new Image(); im.onload=()=>r(im); im.src=u; });
      const k=Math.min(1,1800/Math.max(img.width,img.height)), cv=document.createElement('canvas'); cv.width=Math.round(img.width*k); cv.height=Math.round(img.height*k);
      const cx=cv.getContext('2d'); cx.fillStyle='#fff'; cx.fillRect(0,0,cv.width,cv.height); cx.drawImage(img,0,0,cv.width,cv.height);
      const r=await fetch('/api/conti',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'upload',key:KEY,title:title.trim(),music_key:(mk||'').trim(),data:cv.toDataURL('image/jpeg',0.88)})});
      const j=await r.json(); if(!j.ok){ msg('올리기 실패: '+(j.error||'')); return; }
      S[active].push(j.card); dirty=true; render(); msg('「'+j.card.title+'」 악보를 '+({intro:'도입곡',main:'진행곡',apply:'적용곡',pool:'후보함'}[active])+'에 넣었습니다 — 💾 확정 저장을 눌러 주세요'); });
    // 악보 찾기
    let tm=null; const inp=B.querySelector('.bd-find input'), res=B.querySelector('.bd-res');
    inp.addEventListener('input',()=>{ clearTimeout(tm); tm=setTimeout(async()=>{ const v=inp.value.trim(); if(!v){ res.innerHTML=''; return; }
      const rows=await (await fetch('/api/worship?scores='+encodeURIComponent(v))).json();
      res.innerHTML=rows.slice(0,24).map((x,i)=>`<div class="cd" data-r="${i}"><img src="${esc(x.url)}" alt="" loading="lazy"><div class="ct"><i>${esc(x.kind)}</i>${esc(x.title)}${x.key?'<b>'+esc(x.key)+'</b>':''}</div></div>`).join('')||'<span style="color:#64748b;font-size:13px">찾은 악보가 없습니다</span>';
      res.onclick=e=>{ const c=e.target.closest('.cd'); if(!c) return; const x=rows[+c.dataset.r];
        S[active].push({title:x.title,key:x.key,img:x.url,score_id:+x.id,src:'db'}); dirty=true; render();
        msg('「'+x.title+'」 을(를) '+({intro:'도입곡',main:'진행곡',apply:'적용곡',pool:'후보함'}[active])+'에 넣었습니다 — 💾 확정 저장을 눌러 주세요'); }; },300); });
    // 저장 → 맥미니가 악보집·예배 PPT 를 다시 만든다
    B.querySelector('.bd-save').onclick=async()=>{ msg('저장 중…');
      const r=await fetch('/api/conti',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:DATE,key:KEY,...S})});
      const j=await r.json(); if(!j.ok){ msg('저장 실패: '+(j.error||'')); return; } dirty=false; rev=j.rev;
      msg('✅ 저장했습니다 — 맥미니가 악보집·예배 PPT 를 다시 만드는 중입니다(몇 분)'); let n=0;
      const t=setInterval(async()=>{ n++; const g=await (await fetch(`/api/conti?date=${DATE}&key=${KEY}`,{cache:'no-store'})).json();
        if(g.built_rev>=rev){ clearInterval(t); msg('✅ 악보집·예배 PPT 에 반영됐습니다 — 새로고침하면 보입니다'); } else if(n>45){ clearInterval(t); msg('저장은 됐습니다 · 반영이 늦어지고 있습니다(맥미니 확인 필요)'); } },20000); };
    addEventListener('beforeunload',e=>{ if(dirty){ e.preventDefault(); e.returnValue='저장하지 않은 콘티가 있습니다'; } });
    fetch(`/api/conti?date=${DATE}&key=${KEY}`,{cache:'no-store'}).then(r=>r.json()).then(j=>{ if(j.error){ msg(j.error); return; }
      S={intro:j.intro||[],main:j.main||[],apply:j.apply||[],pool:j.pool||[]}; rev=j.rev||0; setActive('pool'); render();
      msg(j.updated?('마지막 저장 '+j.updated+' (UTC)'):''); }).catch(e=>msg('불러오기 실패: '+e));
  };
})();
"""

PDF_JS = r"""
// PDF 저장 — 공유본 옆에 서버가 미리 만들어 둔 doc.pdf(A4 가로 12쪽)를 받아 저장 위치를 묻는다 (2026-10-03 교장님 지시)
// 크롬·엣지: 저장 위치 창(showSaveFilePicker) · 사파리 등: 내려받기 · 카톡 안 브라우저: PDF 를 바로 연다 · doc.pdf 가 없으면(로컬 파일) 인쇄 창
// PPT — 같은 폴더의 ppt.html(쪽마다 한 장 · 보기 + .pptx 내려받기) 로 간다 (2026-10-03 교장님 지시)
window.wsPpt = function(){
  if (location.protocol === 'file:') { alert('PPT 페이지는 링크(공유본)에서 열립니다'); return; }
  location.href = location.pathname.endsWith('/') ? 'ppt.html' : location.pathname + '/ppt.html';
};
window.wsJubo = function(){   // 주보 — 그 주 드라이브 주보 PDF 를 보고 내려받는 jubo.html (2026-10-03 교장님 지시)
  if (location.protocol === 'file:') { alert('주보 페이지는 링크(공유본)에서 열립니다'); return; }
  location.href = location.pathname.endsWith('/') ? 'jubo.html' : location.pathname + '/jubo.html';   // 한글 주보를 읽어 만든 HTML 주보 (2026-10-03 교장님 지시)
};
window.wsPdf = async function(){
  const name = "@@NAME@@";
  if (/KAKAOTALK|NAVER|Line\//i.test(navigator.userAgent)) { location.href = 'doc.pdf'; return; }
  let blob = null;
  try { const r = await fetch('doc.pdf', {cache:'no-store'});
        if (r.ok && /pdf/.test(r.headers.get('content-type') || '')) blob = await r.blob(); } catch (e) {}
  if (!blob) { window.print(); return; }
  if (window.showSaveFilePicker) {
    try { const h = await showSaveFilePicker({suggestedName: name, types: [{description: 'PDF 문서', accept: {'application/pdf': ['.pdf']}}]});
          const w = await h.createWritable(); await w.write(blob); await w.close(); return; }
    catch (e) { if (e && e.name === 'AbortError') return; }
  }
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 5000);
};
"""

FIT = """
window.wsKey = function(b){   // 두 코드 악보 — 누른 코드의 악보만 보이게 (2026-10-03 교장님 지시)
  var slot = b.closest('.slot'), k = b.dataset.k;
  slot.querySelectorAll('button.skey').forEach(function(x){ x.classList.toggle('on', x === b); });
  slot.querySelectorAll('img[data-k]').forEach(function(im){ im.classList.toggle('kalt', im.dataset.k !== k); });
};
// 글이 칸을 넘치면 글자를 줄인다 — 웹글꼴이 늦게 오면 한 번 더
function wsFit(){document.querySelectorAll('.pages .body').forEach(b=>{let s=parseFloat(b.dataset.max||16);b.style.fontSize=s+'pt';
  while((b.scrollHeight>b.clientHeight+1||b.scrollWidth>b.clientWidth+1)&&s>6){s-=.25;b.style.fontSize=s+'pt'}})}
wsFit(); if(document.fonts) document.fonts.ready.then(wsFit);
"""


def img_src(rel: str) -> str:
    if str(rel).startswith(("http://", "https://")): return rel     # 그림 창고(Blob) 주소 — 복사하지 않고 그대로 (2026-10-03)
    p = HERE / rel
    return f"data:image/{p.suffix[1:].replace('jpg', 'jpeg')};base64," + base64.b64encode(p.read_bytes()).decode()



PASS_FILE = HERE / "prep_pass.txt"   # git 제외. 없으면 네 자리 임시 비번을 만든다
NODE = Path.home() / ".local/bin/node"


def prep_pass() -> str:
    if not PASS_FILE.exists():
        import secrets
        PASS_FILE.write_text(f"{secrets.randbelow(9000) + 1000}\n")
    return PASS_FILE.read_text().strip()


def seal(text: str) -> dict:
    r = subprocess.run([str(NODE), str(HERE / "seal.mjs")], input=json.dumps({"pass": prep_pass(), "text": text}),
                       capture_output=True, text=True, timeout=60, check=True)
    return json.loads(r.stdout)


def prep_html(d: dict, date: str) -> str:
    """준비 탭: 후보 악보(pool)를 비밀번호로 암호화해 넣는다 — 비번 없이는 페이지 원본을 열어도 못 본다."""
    pool = d.get("pool", [])
    S = d.get("songs", {})
    now = [f"{'도입곡' if g == 'intro' else '적용송' if g == 'apply' else f'{i + 1}번'} {x.get('title') or '제목 미정'}"
           for g in ("intro", "main", "apply") for i, x in enumerate(S.get(g, []))]
    cards = "".join(
        f'<div class="card"><div class="ct"><i>후보 {i}</i>{html.escape(x.get("title") or "제목 미정")}'
        f'{"<u>확정</u>" if x.get("used") else ""}</div><img src="{img_src(x["img"])}" alt=""></div>'
        for i, x in enumerate(pool, 1))
    import hmac, hashlib
    sec = next((ln.split("=", 1)[1].strip() for ln in (Path.home() / "dev/daily-briefing/.env").read_text().splitlines() if ln.startswith("JUBO_SECRET=")), "")
    bkey = hmac.new(sec.encode(), b"conti", hashlib.sha256).hexdigest()[:32] if sec else ""
    inner = (f'<div class="ph"><h3>🔒 준비 · {int(date[5:7])}월 {int(date[8:10])}일 주일 콘티 편집판</h3>'
             f'<span class="now">지금 확정: {html.escape(" · ".join(now) or "아직 없음")}</span></div>'
             f'<div id="board" data-date="{date}" data-key="{bkey}"><div class="empty">편집판을 불러오는 중…</div></div>')
    inner += conti_html(date)
    box = seal(inner)
    return ('<div id="prep"><div class="lock"><h3>🔒 준비자 전용</h3><p>비밀번호를 넣으면 이번 주 후보 악보가 열립니다.</p>'
            '<form onsubmit="wsUnlock(event)"><input id="prep-pw" type="password" inputmode="numeric" autocomplete="off" placeholder="비밀번호">'
            '<button>열기</button></form><div class="err" id="prep-err"></div></div><div class="in" hidden></div></div><div id="zoom"></div>'
            f'<script type="application/json" id="prep-box" data-share>{json.dumps(box)}</script>')

def conti_html(date: str) -> str:
    """준비 탭 아래 — 주보로 뽑은 콘티 추천(CCM·찬송가, 빠른·중간·느린, 코드·유튜브·악보 검색). 2026-10-03 교장님 지시:
    텔레그램으로 따로 보내던 콘티를 여기에 넣는다. 원본은 out/<YYYYMMDD>-conti.json(conti.py)."""
    import urllib.parse as up
    f = HERE.parent / "out" / f"{date.replace('-', '')}-conti.json"
    if not f.exists():
        return '<div class="conti"><h3>🎵 콘티 추천</h3><div class="empty">주보를 보내 주시면 설교에 맞는 콘티 추천이 여기에 들어옵니다.</div></div>'
    c = json.loads(f.read_text()); s, r = c.get("sermon", {}), c.get("rec", {})
    def rows(items):
        out = []
        for tempo in ("빠른곡", "중간곡", "느린곡"):
            xs = [x for x in items if x.get("tempo") == tempo]
            if not xs: continue
            li = []
            for i, x in enumerate(xs, 1):
                name = (f"{x['no']}장 " if x.get("no") else "") + x.get("title", "")
                q = (f"새찬송가 {x['no']}장 " if x.get("no") else "") + f"{x.get('title', '')} 악보"
                t_ = (f'<a href="{html.escape(x["url"])}" target="_blank" rel="noopener">{html.escape(name)} ▶</a>' if x.get("url")
                      else html.escape(name))
                li.append(f'<li>{t_}{" <b>" + html.escape(x["key"]) + "</b>" if x.get("key") else ""}'
                          f' <a class="sh" href="https://www.google.com/search?tbm=isch&q={up.quote_plus(q)}" target="_blank" rel="noopener">악보</a></li>')
            out.append(f'<div class="tp"><i>{tempo}</i><ol>{"".join(li)}</ol></div>')
        return "".join(out)
    head = f'설교 「{html.escape(s.get("title") or "-")}」 {html.escape(s.get("scripture") or "")}'
    theme = f'<p class="th">주제: {html.escape(r["theme"])}</p>' if r.get("theme") else ""
    return (f'<div class="conti"><h3>🎵 콘티 추천 · {head}</h3>{theme}'
            f'<div class="cols"><div><h4>CCM {len(r.get("ccm", []))}곡</h4>{rows(r.get("ccm", []))}</div>'
            f'<div><h4>찬송가 {len(r.get("hymns", []))}곡</h4>{rows(r.get("hymns", []))}</div></div></div>')


ROSTER = HERE / "roster.json"
WEEKS_SHOWN = 6
GROUP_COLOR = {"인도·세션": ("#1e3a8a", "#eef2ff"), "싱어": ("#b45309", "#fff4e5"), "미디어": ("#0e7490", "#e6f7fa")}


def notice_html(date: str) -> str:
    """섬김표 아래 공지사항 — data/<날짜>.json 의 notices (2026-10-03 교장님 지시)."""
    f = HERE / "data" / f"{date}.json"
    ns = json.loads(f.read_text()).get("notices", []) if f.exists() else []
    items = "".join(f"<li>{html.escape(x)}</li>" for x in ns)
    return f'<div class="notice"><b>📢 공지사항</b><ul>{items}</ul></div>'


CHG_PALETTE = ["#7c3aed", "#0f766e", "#b45309", "#1d4ed8", "#be185d", "#4d7c0f"]   # 빨강 없음


def chg_style(R: dict, name: str) -> str:
    """바뀐 사람 색 — 사람마다 다른 색(roster.json person_colors, 없으면 이름으로 고정 배정). 2026-10-03 교장님 지시."""
    import hashlib
    key = re.sub(r"\(.*?\)", "", name).strip()
    c = R.get("person_colors", {}).get(key) or CHG_PALETTE[int(hashlib.md5(key.encode()).hexdigest(), 16) % len(CHG_PALETTE)]
    return f"background:{c};border-color:{c}"


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
                cap = R.get("role_slots", {}).get(role, 4)   # 촬영은 2자리(2×1)
                slots = (names + [""] * cap)[:max(cap, len(names))]
                base = R.get("defaults", {}).get(role)   # 평소 사람과 다르면 색을 바꿔 눈에 띄게 (2026-10-03 교장님 지시)
                chip = lambda v: (f'<span class="nm chg" style="{chg_style(R, v)}">{html.escape(v)}</span>' if base and v not in base
                                  else f'<span class="nm" style="background:{soft};border-color:{c}33">{html.escape(v)}</span>')
                if g.get("single"):   # 인도·세션: 한 줄, 두 칸을 합친 긴 칸 하나 (2026-10-03 교장님 지시)
                    v = ", ".join(names)
                    inner = (f'<span class="nm wide chg" style="{chg_style(R, names[0])}">{html.escape(v)}</span>' if v and base and any(n not in base for n in names)
                             else f'<span class="nm wide" style="background:{soft};border-color:{c}33">{html.escape(v)}</span>' if v
                             else '<span class="nm wide empty"></span>')
                    cells.append(f'<td class="{"now" if k == 0 else ""}"><div class="q1">{inner}</div></td>')
                    continue
                off = R.get("absent", {}).get(x.isoformat(), [])   # 결석은 흐리게 (2026-10-03 교장님 지시)
                inner = "".join((chip(v).replace('class="nm', 'title="결석" class="nm off', 1) if v in off else chip(v)) if v else '<span class="nm empty"></span>' for v in slots)
                cells.append(f'<td class="{"now" if k == 0 else ""}"><div class="q4">{inner}</div></td>')
            rows.append(f'<tr class="{"gs" if n == 0 else ""}">{gc}<td class="role" style="color:{c}">{role}</td>{"".join(cells)}</tr>')
    sup = "".join(f'<span class="nm">{html.escape(v)}</span>' for v in R.get("support", []))
    return (f'<div class="rs"><div class="rs-h"><div><span class="kick">WORSHIP TEAM ROSTER</span><h2>예배팀 섬김표</h2></div>'
            f'<div class="rr"><span class="range">{days[0].month}.{days[0].day} ~ {days[-1].month}.{days[-1].day}</span></div></div>'
            f'<table class="rt"><colgroup><col style="width:19mm"><col style="width:27mm">{"<col>" * WEEKS_SHOWN}</colgroup>'
            f'<tr><th></th><th></th>{head}</tr>{"".join(rows)}</table>'
            f'<div class="sup"><div class="sup-h"><b>지원팀</b><span>{len(R.get("support", []))}명</span></div><div class="sup-n">{sup}</div></div>{notice_html(date)}</div>')


RECITE = HERE / "recite.json"


def focus_verse(p: dict, date: str) -> int | None:
    """암송 쪽에서 이번 주 외울 절 — recite.json 의 시작 주일·절에서 한 주에 한 절씩 넘어간다."""
    import datetime as _dt
    if not RECITE.exists(): return None
    head = re.sub(r"<[^>]+>", "", p.get("heading", ""))
    for key, v in json.loads(RECITE.read_text()).items():
        if key.startswith("_") or key not in head: continue
        weeks = (_dt.date.fromisoformat(date) - _dt.date.fromisoformat(v["from"])).days // 7
        return v["verse"] + weeks if weeks >= 0 else None
    return None


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
    elif t == "recite" and focus_verse(p, date):
        n = focus_verse(p, date)
        lines = p["body"].split("<br>")
        lines = [f'<span class="focus">{l}</span>' if re.match(rf"\s*(<[^>]+>)*\s*{n}(\s|&nbsp;)", l) else l for l in lines]
        inner = f'<div class="textpage"><h2>{p["heading"]}</h2><div class="body" data-max="14">{"<br>".join(lines)}</div></div>'
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
                ks = song_keys(s, date)
                alt = html.escape(s.get("title", ""))
                imgs = "".join(f'<img src="{img_src(f)}" alt="{alt}{" " + html.escape(k) if k else ""}"{" class=kalt" if j else ""} data-k="{j}">'
                               for j, (k, f) in enumerate(ks))
                halves.append(f'<div class="half {side}"><div class="slot"><div class="shead">{badge}{key_html(ks)}{stt_html(s)}</div>{imgs}'
                              f'</div></div>')
            else:
                halves.append(f'<div class="half {side}"><div class="slot empty">{badge}<b>악보 자리</b><span>{where}{" · " + html.escape(s["label"]) if s.get("label") else ""} — 악보를 주시면 여기에 넣습니다</span></div></div>')
        inner = "".join(halves) + '<div class="divider"></div>'
    return f'<section class="page" id="p{n}">{tag}{inner}</section>'


def song_keys(s: dict, date: str) -> list[tuple[str, str]]:
    """곡의 코드와 악보 — [(코드, 그림 경로)] (2026-10-03 교장님 지시).
    한 곡을 두 코드로 이어 부를 때는 data 의 "keys": [{"key":"G","img":…},{"key":"A","img":…}] — 「5 G→A 온 땅의 주인」.
    한 코드면 "key", 없으면 악보 보관함 기록(그 곡 악보가 한 장뿐이거나, 이번 주에 쓴 코드)에서 찾는다."""
    if s.get("keys"):
        return [(k.get("key", ""), k["img"]) for k in s["keys"] if k.get("img")] or [("", s["img"])]
    k = s.get("key", "")
    if not k and s.get("title"):
        try:
            import bank
            r = bank.load()["songs"]; t = bank.norm(s["title"])
            sc = next((v["scores"] for n, v in r.items() if bank.norm(n) == t), {})
            k = (next(iter(sc)) if len(sc) == 1
                 else next((c for c, v in sc.items() if any(u.startswith(date) for u in v.get("used", []))), ""))
        except Exception:
            k = ""
    return [(k, s["img"])]


def key_html(ks: list[tuple[str, str]]) -> str:
    """번호 옆 코드 — 한 코드면 「G」, 두 코드면 「G→A」 이고 코드를 누르면 그 코드 악보가 보인다."""
    if not any(k for k, _ in ks): return ""
    if len(ks) == 1: return f'<span class="skey">{html.escape(ks[0][0])}</span>'
    btn = [f'<button type="button" class="skey{" on" if j == 0 else ""}" data-k="{j}" onclick="wsKey(this)">{html.escape(k or "?")}</button>'
           for j, (k, _) in enumerate(ks)]
    return '<span class="skeys">' + '<span class="karr">→</span>'.join(btn) + '</span>'


def stt_html(s: dict) -> str:
    """곡 제목 — 유튜브 주소가 있으면 제목을 누르면 열리게 (2026-10-03 교장님 지시). 없으면 악보 보관함 기록에서 찾는다."""
    t = html.escape(s.get("title") or "")
    u = s.get("youtube")
    if not u and s.get("title"):
        try:
            import bank
            r = bank.load()["songs"]; k = bank.norm(s["title"])
            u = next((v.get("youtube") for n, v in r.items() if bank.norm(n) == k and v.get("youtube")), "")
        except Exception:
            u = ""
    return (f'<a class="stt" href="{html.escape(u)}" target="_blank" rel="noopener">{t} <span class="yt">▶</span></a>' if u
            else f'<span class="stt">{t}</span>')


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
<title>{html.escape(d["title"])}</title><meta name="description" content="제곡교회 예배팀 · {int(date[5:7])}월 {int(date[8:10])}일 주일예배 예배자 악보 {len(d["pages"])}쪽">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>{CSS}{wsnav.CSS}</style></head><body>
{wsnav.nav("score", wsnav.label(date), '<button class="sub on" data-mode="doc" onclick="wsMode(\'doc\')">📖 악보집</button><button class="sub" data-mode="sv" onclick="wsMode(\'sv\')">▣ 한 장씩</button><button class="sub" data-mode="pr" onclick="wsMode(\'pr\')">▶ 예배용 넘기기</button>', [("📄 HWPX 받기", "doc.hwpx"), ("📕 PDF 받기", "js:wsPdf()")], prep_js=True)}
<main class="pages">{pages}</main><div id="sv"><aside id="rail"></aside><div id="split" title="끌어서 폭 조절"></div><div id="stage"><span id="hint">← → 방향키로 넘김 · Esc 나가기</span><span id="pn"></span></div></div>{prep_html(d, date)}<script data-share>{wsnav.JS}</script><script data-share>{FIT}</script><script data-share>{VIEW}</script><script data-share>{PREP}</script><script data-share>{BOARD}</script><script data-share>{PDF_JS.replace("@@NAME@@", f"{date} 예배자 악보.pdf")}</script></body></html>"""
    out = HERE / "out" / f"{date}.html"; out.parent.mkdir(exist_ok=True); out.write_text(doc)
    return out


if __name__ == "__main__":
    o = build(sys.argv[1])
    print(o)
    if "--open" in sys.argv: subprocess.run(["open", o])
    if "--share" in sys.argv:
        import urllib.request, publish
        pretty = publish.prepare(sys.argv[1])   # jegok_worship_YYYYMMDD · 모음 쪽 · 노션 — 배포 전에
        # PPT 페이지(쪽 그림·doc.pptx·ppt.html)를 공유 폴더에 먼저 둔다 — PIL·python-pptx 가 있는 파이썬으로
        subprocess.run(["/usr/local/bin/python3", str(HERE / "pptpage.py"), sys.argv[1]], check=False)
        # 예배 화면용 PPT(PDF)가 있으면 PPT 단추는 그것을 HTML 슬라이드로 (2026-10-03 교장님 지시) — accomp/worship_ppt/<날짜>.pdf [.pptx]
        wp = HERE / "worship_ppt" / f"{sys.argv[1]}.pdf"
        # 드라이브 그 주 폴더의 「주일예배 PPT」를 먼저 받아 둔다 — 없을 때만 악보집 쪽 그림 PPT (2026-10-03 교장님 지시)
        # 2026-10-03 교장님 지시: 드라이브에서 불러오지 않고 예배 PPT 템플릿(ppt_template, 10/4 PPT)으로 날짜마다 찍는다.
        # worship_ppt/<날짜>.pdf 를 교장님이 따로 주신 주만 그것을 그대로 쓴다.
        if wp.exists():
            px = wp.with_suffix(".pptx")
            subprocess.run(["/usr/local/bin/python3", str(HERE / "slides.py"), str(wp), sys.argv[1]] + (["--pptx", str(px)] if px.exists() else []), check=False)
        elif (HERE / "ppt_template" / "slides.json").exists():
            subprocess.run(["/usr/local/bin/python3", str(HERE / "ppt_tpl.py"), "make", sys.argv[1]], check=False)
        body = json.dumps({"key": f"/accomp/{sys.argv[1]}", "title": o.stem + " 예배자 악보", "html": o.read_text()}).encode()
        req = urllib.request.Request("http://127.0.0.1:8765/share", data=body, headers={"Content-Type": "application/json"})
        json.load(urllib.request.urlopen(req, timeout=180))
        print(pretty)
