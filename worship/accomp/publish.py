#!/usr/bin/env python3
"""주일예배 악보집 게시 규약 (2026-10-03 교장님 확정).

  주소   https://report-site-kohl.vercel.app/jegok_worship_YYYYMMDD   ← 그 주 악보집
  모음   https://report-site-kohl.vercel.app/jegok_worship            ← 지금까지 낸 악보집이 계속 쌓이는 목록
  노션   「📖 주일예배 악보집」 DB 에 같은 날짜 한 줄(있으면 고쳐 씀)

build.py --share 가 docsave 에 올리기 **전에** prepare(date) 를 불러 주소 연결·모음 쪽·노션을 마친다
(그래야 한 번의 배포에 다 들어간다).
  python3 accomp/publish.py 2026-10-04      # 빌드 없이 주소·모음·노션만 다시
"""
from __future__ import annotations
import datetime as dt, html, json, re, secrets, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
SITE = Path.home() / "dev/daily-briefing/report-site"
SHARES = Path.home() / "dev/daily-briefing/docsave/shares.json"
BASE = "https://report-site-kohl.vercel.app"
INDEX = "jegok_worship"
PUBLISHED = HERE / "published.json"
NOTION_CFG = HERE / "notion_book.json"


def slug(date: str) -> str:
    return f"{INDEX}_{date.replace('-', '')}"


def url(date: str) -> str:
    return f"{BASE}/{slug(date)}"


def sid_for(date: str) -> str:
    """docsave 와 같은 등록부(shares.json)에 미리 자리를 잡는다 — 같은 날짜는 늘 같은 id."""
    key = f"/accomp/{date}"
    reg = json.loads(SHARES.read_text()) if SHARES.exists() else {}
    if key not in reg:
        reg[key] = secrets.token_urlsafe(12)
        SHARES.write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    return reg[key]


def route(date: str, sid: str) -> None:
    p = SITE / "vercel.json"; v = json.loads(p.read_text())
    s = "/" + slug(date)
    v["rewrites"] = [r for r in v["rewrites"] if not r["source"].startswith(s + "/")] + [
        {"source": s + "/", "destination": f"/d/{sid}/"}, {"source": s + "/:path*", "destination": f"/d/{sid}/:path*"}]
    keep = [r for r in v.get("redirects", []) if r["source"] not in (s, "/" + INDEX)]
    v["redirects"] = keep + [{"source": s, "destination": s + "/", "permanent": False}]
    # 옛 주소(jegokworship20261004)는 새 주소로 넘긴다
    old = "/jegokworship" + date.replace("-", "")
    v["rewrites"] = [r for r in v["rewrites"] if not r["source"].startswith(old)]
    v["redirects"] = [r for r in v["redirects"] if r["source"] != old] + [{"source": old, "destination": s + "/", "permanent": False}]
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2))


def summary(date: str) -> dict:
    d = json.loads((HERE / "data" / f"{date}.json").read_text())
    st = next((p for p in d["pages"] if p["type"] == "sermon_text"), {})
    songs = d.get("songs")
    if not songs:   # 옛 형식(쪽마다 slots)
        sc = [s for p in d["pages"] if p["type"] == "scores" for s in p["slots"]]
        songs = {"intro": sc[:1], "main": sc[1:-1], "apply": sc[-1:]}
    t = lambda L: [s.get("title") or "제목 미정" for s in L]
    leader = []
    try:
        leader = json.loads((HERE / "roster.json").read_text())["weeks"].get(date, {}).get("인도자", [])
    except Exception:  # noqa: BLE001
        pass
    return {"date": date, "ref": st.get("ref", ""), "title": st.get("title", ""), "intro": t(songs.get("intro", [])),
            "main": t(songs.get("main", [])), "apply": t(songs.get("apply", [])), "leader": leader, "url": url(date)}


def leader_from_path(path: str) -> str:
    """「2026 0118 주일예배 정영화/…」 처럼 폴더 이름 끝에 적힌 인도자. 없으면 ""(지어내지 않는다)."""
    m = re.search(r"\d{4}\s?\d{4}\s*\S*예배\s+([가-힣]{2,4})(?:/|$)", path or "")
    return m.group(1) if m else ""


def past_services() -> list[dict]:
    """곡 스캔(songppt/scan)으로 찾은 지난 예배(2021~ 주일·수요·금요…) — 날짜·종류·곡·원본 PPT."""
    out = []
    for f in sorted((HERE / "songppt" / "scan").glob("*.json")):
        if "~p" in f.name: continue          # 큰 슬라이드를 나눠 읽은 조각 — 묶음 기록(같은 id.json)만 쓴다
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        src = d["src"]
        if not src.get("date") or "0000" in src["name"] or "템플릿" in src.get("path", ""): continue   # 예배준비 템플릿은 예배가 아니다
        link = (f"https://docs.google.com/presentation/d/{src['id']}/edit" if src["mimeType"].endswith("google-apps.presentation")
                else f"https://drive.google.com/file/d/{src['id']}/view")
        ld = leader_from_path(src.get("path", ""))
        out.append({"date": src["date"], "kind": src["kind"], "songs": [g["title"] for g in d.get("groups", [])], "src": link,
                    "leader": [ld] if ld else []})
    return out


def index_page() -> None:
    """모음 쪽 = 랜딩 (2026-10-03 교장님 지시).
    위 가운데: 주일 0시~24시(한국 시간)는 「오늘」 — 그 주 예배 PPT 첫 장을 크게, 누르면 PPT.
               그 밖의 날은 다가오는 주일을 「준비 중」 표지로(함께 준비하는 예배팀에게 한마디).
    아래: 지난 예배 목록 10개씩 쪽 넘김 — 악보집이 있는 주 + 곡 스캔으로 찾은 예전 예배.
    날짜 판단은 페이지가 열릴 때 브라우저가 하므로 주일이 되어도 다시 올릴 필요가 없다."""
    pub = sorted(json.loads(PUBLISHED.read_text()) if PUBLISHED.exists() else [])
    items = []
    for x in pub:
        sm = summary(x)
        cover = (SITE / "d" / sid_for(x) / "cover.jpg").exists()
        items.append({"date": x, "kind": "주일", "title": sm["title"], "ref": sm["ref"], "leader": sm["leader"],
                      "songs": sm["intro"] + sm["main"] + sm["apply"], "book": sm["url"] + "/",
                      "ppt": sm["url"] + "/ppt.html", "cover": (sm["url"] + "/cover.jpg") if cover else ""})
    have = {(i["date"], i["kind"]) for i in items}
    items += [o for o in past_services() if (o["date"], o["kind"]) not in have]
    (SITE / INDEX).mkdir(exist_ok=True)
    (SITE / INDEX / "index.html").write_text(landing_html(items))
    # 「악보와 PPT」 곡 목록의 인도자 배지(2026-10-07 교장님: 한 번이라도 부른 곡엔 그 사람 이름표)
    roles = json.loads((HERE / "services.json").read_text()) if (HERE / "services.json").exists() else {}
    (SITE / INDEX / "song_leaders.json").write_text(json.dumps({"leaders": roles.get("leaders", []), "songs": song_leaders(items)}, ensure_ascii=False))


def song_key(title: str) -> str:
    """곡 제목 맞추기: 띄어쓰기·문장부호·괄호 속 덧말·끝 번호(「주의 인자하심이 1」)를 뺀다. 곡 페이지 JS 의 sk() 와 같은 규칙."""
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", title or "")
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t).lower()
    return re.sub(r"\d+$", "", t) or t


def song_leaders(items: list[dict]) -> dict:
    """곡 → {인도자: 부른 횟수}. 인도자 기록이 없는 예배는 세지 않는다(지어내지 않는다)."""
    out: dict[str, dict[str, int]] = {}
    for i in items:
        for ld in i.get("leader") or []:
            for t in dict.fromkeys(song_key(x) for x in i.get("songs") or []):
                if t:
                    out.setdefault(t, {}); out[t][ld] = out[t].get(ld, 0) + 1
    return out


def landing_html(items: list[dict]) -> str:
    data = json.dumps(sorted(items, key=lambda i: i["date"], reverse=True), ensure_ascii=False).replace("</", "<\\/")
    roles = json.loads((HERE / "services.json").read_text()) if (HERE / "services.json").exists() else {}
    roles = json.dumps(roles, ensure_ascii=False).replace("</", "<\\/")
    return LANDING.replace("@@SCHED@@", SCHED_JS).replace("@@ROLES@@", roles).replace("@@DATA@@", data)


# ── 예배 단추 넷 (2026-10-07 교장님) ─────────────────────────────────
# 지금 띄울 예배 = 「끝나고 1시간」이 아직 안 지난 가장 이른 예배. 시간은 한국 시간 벽시계(Date 의 UTC 칸에 KST 를 담아 다룬다).
# 새벽 월~금(토요일 새벽 없음, 주일은 주일예배) · 수요·금요 19:30~20:30 · 주일은 하루 종일 「오늘」.
# tests/test_landing_schedule.py 가 이 JS 를 node 로 그대로 돌려 본다.
SCHED_JS = r"""const SVC=[
 {k:'dawn',name:'새벽예배',en:'Early Morning Prayer',ru:'Утренняя молитва',days:[1,2,3,4,5],s:'05:00',e:'06:00',hold:60},
 {k:'wed',name:'수요예배',en:'Wednesday Worship',ru:'Богослужение в среду',days:[3],s:'19:30',e:'20:30',hold:60},
 {k:'fri',name:'금요예배',en:'Friday Worship',ru:'Богослужение в пятницу',days:[5],s:'19:30',e:'20:30',hold:60},
 {k:'sun',name:'주일예배',en:'Sunday Worship',ru:'Воскресное богослужение',days:[0],s:'00:00',e:'24:00',hold:0}];
const _min=s=>{const p=s.split(':');return (+p[0]*60+ +p[1])*60e3;};
function _scan(now,ok){const t=now.getTime(),d0=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate());
  for(let i=0;i<10;i++){const d=d0+i*864e5,wd=new Date(d).getUTCDay();
    const ev=SVC.filter(v=>ok(v)&&v.days.includes(wd)).map(v=>({v,s:d+_min(v.s),e:d+_min(v.e)})).sort((a,b)=>a.s-b.s);
    for(const x of ev) if(x.e+x.v.hold*60e3>t) return {k:x.v.k,v:x.v,date:new Date(d).toISOString().slice(0,10),state:t<x.s?'ready':t<x.e?'live':'done'};}
  return null;}
function svcAt(now){return _scan(now,()=>true);}
function nextOf(k,now){return _scan(now,v=>v.k===k);}"""


LANDING = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>제곡교회 예배 플랫폼</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:'Pretendard Variable',Pretendard,sans-serif;background:#f3f4f8;color:#0b1430;word-break:keep-all}
header{background:linear-gradient(160deg,#0b1430,#172a5e 55%,#2b2f6e);color:#fff;padding:30px 20px 90px;text-align:center}
header .k{font-size:11px;letter-spacing:.35em;color:#f6c76b;font-weight:800}header h1{margin:8px 0 0;font-size:26px}
main{max-width:860px;margin:-70px auto 40px;padding:0 14px}
.hero{max-width:720px;margin:0 auto;background:#fff;border-radius:20px;padding:16px;box-shadow:0 10px 30px rgba(11,20,48,.18)}
.hero .tag{display:inline-block;font-size:12px;font-weight:800;border-radius:999px;padding:4px 12px;background:#fdf3dc;color:#8a5a00}
.hero .tag.live{background:#dc2626;color:#fff}
.hero .row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}
.hero .who{font-size:12.5px;color:#64748b}
.shot{display:block;position:relative;aspect-ratio:16/9;border-radius:12px;overflow:hidden;background:#0b1430 center/cover no-repeat}
.shot .play{position:absolute;right:12px;bottom:12px;background:rgba(11,20,48,.72);color:#fff;font-weight:800;border-radius:999px;padding:12px 22px;font-size:16px}
.ready{aspect-ratio:16/9;border-radius:12px;background:linear-gradient(160deg,#172a5e,#2b2f6e);color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:24px}
.ready .big{font-size:clamp(26px,6vw,40px);font-weight:800;letter-spacing:.04em}
.ready .when{margin-top:6px;color:#f6c76b;font-weight:700;font-size:15px}
.ready .msg{margin-top:16px;max-width:460px;color:#dbe3ff;font-size:14.5px;line-height:1.7}
.hero h2{margin:12px 2px 2px;font-size:19px}.hero .ref{margin:0 2px;color:#64748b;font-size:13px}
.btns{display:flex;gap:8px;margin-top:12px}.btns a{flex:1;text-align:center;text-decoration:none;font-weight:800;font-size:14px;border-radius:12px;padding:12px 8px;background:#f1f5f9;color:#0b1430}
.btns a.p{background:#f6c76b;color:#0b1430}
.chips{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px}.chips li{font-size:12.5px;background:#f1f5f9;border-radius:8px;padding:3px 9px}
h3.sec{margin:28px 4px 10px;font-size:15px;color:#334155;display:flex;justify-content:space-between;align-items:baseline}h3.sec span{font-size:12px;color:#94a3b8;font-weight:500}
.list{background:#fff;border-radius:16px;box-shadow:0 2px 10px rgba(11,20,48,.06);overflow:hidden}
.it{display:flex;gap:14px;align-items:flex-start;padding:13px 16px;border-top:1px solid #eef1f6;text-decoration:none;color:inherit}.it:first-child{border-top:0}
.it:hover{background:#f8fafc}
.d{flex:0 0 58px;text-align:center}.d b{display:block;font-size:19px}.d span{font-size:11px;color:#94a3b8}
.m{flex:1;min-width:0}.m .t{font-weight:700;font-size:15px}.m .s{color:#64748b;font-size:12.5px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kind{font-size:11px;font-weight:800;border-radius:6px;padding:1px 6px;margin-left:6px;background:#eef2ff;color:#3730a3}
.go{flex:0 0 auto;font-size:12px;font-weight:700;color:#b8860b;padding-top:4px}
.pg{display:flex;justify-content:center;flex-wrap:wrap;gap:6px;margin:14px 0}
.pg button{font:700 13px inherit;border:0;border-radius:10px;padding:8px 12px;background:#fff;color:#0b1430;cursor:pointer;box-shadow:0 1px 4px rgba(11,20,48,.08)}
.pg button.on{background:#0b1430;color:#fff}.pg button:disabled{opacity:.4;cursor:default}
/* 예배 단추 넷 + 새 템플릿(A 키노트) 표지 — 2026-10-07 */
.svc{max-width:720px;margin:0 auto 12px;display:grid;grid-template-columns:repeat(4,1fr);gap:6px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);border-radius:16px;padding:6px;backdrop-filter:blur(6px)}
.svc button{position:relative;font:inherit;border:0;border-radius:11px;padding:11px 4px 10px;background:transparent;color:#dbe3ff;font-weight:700;font-size:15px;cursor:pointer;line-height:1.2}
.svc button small{display:block;font-size:11px;font-weight:600;color:#9fb0e0;margin-top:3px;min-height:13px}
.svc button.now{color:#fff;box-shadow:inset 0 0 0 1.5px #f6c76b}
.svc button.now small{color:#f6c76b}
.svc button.on{background:#fff;color:#0b1430;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.svc button.on.now{box-shadow:inset 0 0 0 2px #f6c76b,0 4px 14px rgba(0,0,0,.18)}
.svc button.on small{color:#8a5a00}
.svc button:focus-visible{outline:2px solid #f6c76b;outline-offset:2px}
.slide{position:relative;aspect-ratio:16/9;border-radius:12px;overflow:hidden;background:#05070d;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.slide:before{content:"";position:absolute;inset:0;background:radial-gradient(55% 60% at 50% 38%,rgba(56,92,255,.30),transparent 62%),radial-gradient(40% 45% at 85% 95%,rgba(0,190,200,.14),transparent 60%),radial-gradient(35% 40% at 10% 90%,rgba(120,80,255,.12),transparent 60%)}
.slide:after{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:36px 36px;-webkit-mask-image:radial-gradient(70% 65% at 50% 42%,#000,transparent);mask-image:radial-gradient(70% 65% at 50% 42%,#000,transparent)}
.slide>*{position:relative;z-index:1}
.slide .ch{font-size:11px;letter-spacing:.42em;color:rgba(255,255,255,.55);font-weight:600}
.slide .nm{font-size:clamp(34px,8.4vw,58px);font-weight:900;letter-spacing:.06em;margin:6px 0 4px}
.slide .en{font-size:13px;color:#cfd9ff}.slide .ru{font-size:11.5px;color:#8fb0ff;margin-top:2px}
.slide .ln{width:44px;height:2px;background:#5b7cff;margin:12px 0 10px}
.slide .tm{font-size:14px;color:#f6c76b;font-weight:700;letter-spacing:.04em}
.svmsg{margin:12px 2px 0;font-size:14.5px;line-height:1.7;color:#334155}
.svmsg small{display:block;color:#94a3b8;font-size:12.5px;margin-top:2px}
.hero .tag.done{background:#e2e8f0;color:#475569}
.btns a.off{opacity:.45;cursor:default;pointer-events:none}
.flt{display:flex;flex-wrap:wrap;gap:6px;margin:0 2px 10px}.flt .g{display:flex;flex-wrap:wrap;gap:6px;width:100%}
.flt button{font:inherit;font-size:12.5px;font-weight:700;border:1px solid #dbe1ea;background:#fff;color:#334155;border-radius:999px;padding:5px 11px;cursor:pointer}
.flt button.on{background:#0b1430;color:#fff;border-color:#0b1430}.flt button em{font-style:normal;font-weight:500;opacity:.7;margin-left:3px}
.ld{font-size:11px;font-weight:800;border-radius:6px;padding:1px 6px;margin-left:6px;background:#fdf3dc;color:#8a5a00;white-space:nowrap}
.roles{display:block;color:#475569;font-size:13px;margin-top:4px}
@media(max-width:560px){.svc button{font-size:13.5px;padding:10px 2px 9px}.svc button small{font-size:10.5px}.ready{aspect-ratio:auto;min-height:220px}.ready .msg br{display:none}header{padding:24px 16px 80px}.go{display:none}.hero{padding:12px}.d{flex-basis:48px}}
</style></head><body>
<header><span class="k">JEGOK CHURCH · WORSHIP TEAM</span><h1>제곡교회 예배 플랫폼</h1></header>
<main><nav class="svc" id="svc" aria-label="예배 고르기"></nav><section class="hero" id="hero"></section>
<h3 class="sec">지난 예배 <span id="cnt"></span></h3><div class="flt" id="flt"></div><div class="list" id="list"></div><div class="pg" id="pg"></div></main>
<script id="data" type="application/json">@@DATA@@</script><script id="roles" type="application/json">@@ROLES@@</script>
<script>
const ALL=JSON.parse(document.getElementById('data').textContent);
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const Q=new URLSearchParams(location.search), NOW=Q.get('now')?new Date(Q.get('now')+':00Z'):new Date(Date.now()+9*3600e3);   // ?now=2026-10-07T19:45 미리 보기용(한국 시간)
const TODAY=Q.get('today')||NOW.toISOString().slice(0,10);   // ?today= 은 옛 미리 보기용
@@SCHED@@
const W='일월화수목금토';
const md=d=>{const x=new Date(d+'T00:00:00Z');return (x.getUTCMonth()+1)+'월 '+x.getUTCDate()+'일('+W[x.getUTCDay()]+')';};
function nextSunday(){const x=new Date(TODAY+'T00:00:00Z');x.setUTCDate(x.getUTCDate()+((7-x.getUTCDay())%7||7));return x.toISOString().slice(0,10);}
const sundays=ALL.filter(i=>i.ppt);
const today=sundays.find(i=>i.date===TODAY);
function hero(){const h=document.getElementById('hero');   // 주일예배
  if(today){const i=today;
    h.innerHTML='<div class="row"><span class="tag live">● 오늘 · '+md(i.date)+'</span><span class="who">'+(i.leader.length?'인도 '+esc(i.leader.join(', ')):'')+'</span></div>'
      +'<a class="shot" href="'+i.ppt+'#pv" style="background-image:url(\''+i.cover+'\')"></a>'
      +'<h2>'+esc(i.title||'주일예배')+'</h2><p class="ref">'+esc(i.ref)+'</p>'
      +'<div class="btns"><a class="p" href="'+i.book+'#prep">예배준비</a><a href="'+i.book+'">악보</a><a href="'+i.ppt+'#pv">PPT</a></div>';
    return;}
  const up=sundays.filter(i=>i.date>TODAY).sort((a,b)=>a.date<b.date?-1:1)[0];
  const day=up?up.date:nextSunday();
  const left=Math.round((new Date(day)-new Date(TODAY))/864e5);
  h.innerHTML='<div class="row"><span class="tag">준비 중 · '+md(day)+'</span><span class="who">'+(up&&up.leader.length?'인도 '+esc(up.leader.join(', ')):'')+'</span></div>'
    +'<div class="ready"><div class="big">예배 준비 중</div><div class="when">'+md(day)+' 주일예배'+(left>0?' · '+left+'일 남음':'')+'</div>'
    +'<div class="msg">함께 예배를 준비하는 동역자 여러분, 고맙습니다.<br> 이번 한 주도 말씀과 찬양으로 마음을 준비해 주세요.<br> 주일 아침, 기쁨으로 만나요.</div></div>'
    +(up?'<h2>'+esc(up.title||'주일예배')+'</h2><p class="ref">'+esc(up.ref)+'</p>'
      +(up.songs.length?'<ul class="chips">'+up.songs.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ul>':'')
      +'<div class="btns"><a class="p" href="'+up.book+'#prep">예배준비</a><a href="'+up.book+'">악보</a><a href="'+up.ppt+'">PPT</a></div>':'');}
const PAST0=ALL.filter(i=>i!==today&&i.date<=TODAY), PER=10;
const KINDS=['주일','수요','금요'], NOREC='기록 없음';
const kOf=i=>KINDS.includes(i.kind)?i.kind:'기타', lOf=i=>(i.leader&&i.leader.length)?i.leader:[NOREC];
function hp(){const h=new URLSearchParams(location.hash.slice(1));return {p:+(h.get('p')||1),k:h.get('k')||'',l:h.get('l')||''};}
function go(o){const h=new URLSearchParams();if(o.k)h.set('k',o.k);if(o.l)h.set('l',o.l);if(o.p>1)h.set('p',o.p);location.hash=h.toString()||'p=1';}
function flt(st){const pool=PAST0.filter(i=>!st.k||kOf(i)===st.k), cnt={};pool.forEach(i=>lOf(i).forEach(n=>cnt[n]=(cnt[n]||0)+1));
  const names=Object.keys(cnt).sort((a,b)=>a===NOREC?1:b===NOREC?-1:cnt[b]-cnt[a]);
  const kb=['','주일','수요','금요','기타'].map(k=>'<button type="button" data-k="'+k+'" class="'+(st.k===k?'on':'')+'">'+(k?k+'예배':'전체')+'</button>').join('');
  const lb='<button type="button" data-l="" class="'+(!st.l?'on':'')+'">인도자 전체</button>'+names.map(n=>'<button type="button" data-l="'+esc(n)+'" class="'+(st.l===n?'on':'')+'">'+esc(n)+'<em>'+cnt[n]+'</em></button>').join('');
  const f=document.getElementById('flt'); f.innerHTML='<div class="g">'+kb+'</div><div class="g">'+lb+'</div>';
  f.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>go({k:b.dataset.k,l:''}));
  f.querySelectorAll('[data-l]').forEach(b=>b.onclick=()=>go({k:st.k,l:b.dataset.l}));}
function list(st){const PAST=PAST0.filter(i=>(!st.k||kOf(i)===st.k)&&(!st.l||lOf(i).includes(st.l)));
  let p=st.p; const n=Math.max(1,Math.ceil(PAST.length/PER)); p=Math.min(Math.max(1,p),n); flt(st);
  document.getElementById('cnt').textContent=PAST.length+'개 · '+p+'/'+n+'쪽';
  document.getElementById('list').innerHTML=PAST.slice((p-1)*PER,p*PER).map(i=>{const x=new Date(i.date+'T00:00:00Z');
    const href=i.ppt||i.src, t=i.ppt?(i.title||'주일예배'):(i.kind+'예배');
    const sub=(i.ref?i.ref+' · ':'')+(i.songs.length?i.songs.join(' · '):'곡 정보 없음');
    return '<a class="it" href="'+href+'"'+(i.ppt?'':' target="_blank" rel="noopener"')+'><div class="d"><b>'+(x.getUTCMonth()+1)+'.'+x.getUTCDate()+'</b><span>'+x.getUTCFullYear()+'</span></div>'
      +'<div class="m"><div class="t">'+esc(t)+(i.kind!=='주일'?'<span class="kind">'+esc(i.kind)+'</span>':'')+(i.leader&&i.leader.length?'<span class="ld">인도 '+esc(i.leader.join(', '))+'</span>':'')+'</div><div class="s">'+esc(sub)+'</div></div>'
      +'<span class="go">'+(i.ppt?'PPT · 악보 →':'원본 PPT ↗')+'</span></a>';}).join('')||'<div class="it">아직 없음</div>';
  const pg=document.getElementById('pg'); let b='<button '+(p<=1?'disabled':'')+' data-p="'+(p-1)+'">◀ 이전</button>';
  const a=Math.max(1,Math.min(p-2,n-4)), z=Math.min(n,a+4);
  for(let k=a;k<=z;k++) b+='<button class="'+(k===p?'on':'')+'" data-p="'+k+'">'+k+'</button>';
  b+='<button '+(p>=n?'disabled':'')+' data-p="'+(p+1)+'">다음 ▶</button>'; pg.innerHTML=b;
  pg.querySelectorAll('button').forEach(x=>x.onclick=()=>go(Object.assign({},st,{p:+x.dataset.p})));}
function route(){list(hp());}
addEventListener('hashchange',()=>{route();document.getElementById('cnt').scrollIntoView({behavior:'smooth'});});
const md2=d=>{const x=new Date(d+'T00:00:00Z');return (x.getUTCMonth()+1)+'월 '+x.getUTCDate()+'일('+W[x.getUTCDay()]+')';};
function dayWord(d){const t=new Date(TODAY+'T00:00:00Z'),x=new Date(d+'T00:00:00Z'),n=Math.round((x-t)/864e5);return n===0?'오늘':n===1?'내일':md2(d);}
function hm(s){const p=s.split(':'),h=+p[0],m=+p[1];return (h<12?'새벽 ':'저녁 ')+(h>12?h-12:h)+'시'+(m?' '+m+'분':'');}
function heroSvc(r){const v=r.v,h=document.getElementById('hero'),w=dayWord(r.date);
  const tag=r.state==='live'?'<span class="tag live">● 지금 예배 중</span>':r.state==='done'?'<span class="tag done">마쳤습니다 · '+md(r.date)+'</span>':'<span class="tag">준비 중 · '+md(r.date)+'</span>';
  const msg=r.state==='live'?'지금 '+v.name+'를 드리고 있습니다.':r.state==='done'?w+' '+v.name+'를 마쳤습니다. 함께해 주셔서 고맙습니다.':w+' '+hm(v.s)+', '+v.name+'를 준비하고 있습니다.';
  h.innerHTML='<div class="row">'+tag+'<span class="who">'+v.s+' ~ '+v.e+'</span></div>'
    +'<div class="slide"><div class="ch">제 곡 교 회</div><div class="nm">'+v.name+'</div>'
    +'<div class="en">'+v.en+'</div><div class="ru">'+v.ru+'</div><div class="ln"></div><div class="tm">'+md(r.date)+' · '+hm(v.s)+'</div></div>'
    +'<p class="svmsg">'+msg+(roleOf(v.k,r.date)?'<span class="roles">'+esc(roleOf(v.k,r.date))+'</span>':'')+'</p>'+svcBtns(v.k,r.date);}
// 새벽·수요·금요도 [예배준비][악보][PPT] (2026-10-07 교장님). 그 예배 자료가 올라와 있으면 열리고, 아직이면 흐리게 막아 둔다.
function svcBtns(k,d){const kind={dawn:'새벽',wed:'수요',fri:'금요'}[k], it=ALL.find(i=>i.date===d&&i.kind===kind&&(i.book||i.ppt));
  const b=(cls,href,t)=>href?'<a class="'+cls+'" href="'+href+'">'+t+'</a>':'<a class="'+cls+' off" aria-disabled="true" title="아직 올라오지 않았습니다">'+t+'</a>';
  return '<div class="btns">'+b('p',it&&it.book?it.book+'#prep':'','예배준비')+b('',it&&it.book,'악보')+b('',it&&it.ppt,'PPT')+'</div>'
    +(it?'':'<p class="svmsg" style="margin-top:8px"><small>악보와 PPT는 준비되는 대로 열립니다.</small></p>');}
const ROLES=JSON.parse(document.getElementById('roles').textContent||'{}');
function roleOf(k,d){const r=Object.assign({},ROLES[k]||{},(ROLES.dates||{})[d]||{});return [r['인도']?'인도 '+r['인도']:'',r['설교']?'설교 '+r['설교']:''].filter(Boolean).join(' · ');}
const CUR=svcAt(NOW); let SEL=CUR.k;
function svcTabs(){const n=document.getElementById('svc');
  n.innerHTML=SVC.map(v=>{const isNow=v.k===CUR.k, sub=isNow?(function(w){return w==='오늘'||w==='내일'?w:CUR.date.slice(5).replace('-','/').replace(/^0/,'')+' 다음';})(dayWord(CUR.date)):'';
    return '<button type="button" data-k="'+v.k+'" class="'+(v.k===SEL?'on ':'')+(isNow?'now':'')+'" aria-pressed="'+(v.k===SEL)+'">'+v.name+'<small>'+sub+'</small></button>';}).join('');
  n.querySelectorAll('button').forEach(b=>b.onclick=()=>{SEL=b.dataset.k;svcTabs();show();});}
function show(){if(SEL==='sun'){hero();return;} heroSvc(SEL===CUR.k?CUR:nextOf(SEL,NOW));}
svcTabs(); show(); route();
</script></body></html>"""


# ── 노션 ──────────────────────────────────────────────
def notion(date: str) -> str:
    import notion_conti as NC   # 같은 토큰·요청 함수(제곡교회 예배팀 페이지 아래)
    s = summary(date)
    if NOTION_CFG.exists():
        db = json.loads(NOTION_CFG.read_text())["db"]
    else:
        r = NC.req("POST", "/databases", {"parent": {"type": "page_id", "page_id": NC.PARENT},
              "icon": {"type": "emoji", "emoji": "📖"}, "title": [{"type": "text", "text": {"content": "주일예배 악보집"}}],
              "properties": {"제목": {"title": {}}, "예배일": {"date": {}}, "설교본문": {"rich_text": {}}, "설교제목": {"rich_text": {}},
                             "인도자": {"rich_text": {}}, "도입곡": {"rich_text": {}}, "본곡": {"rich_text": {}}, "적용송": {"rich_text": {}},
                             "곡 수": {"number": {}}, "악보집": {"url": {}}}})
        db = r["id"]; NOTION_CFG.write_text(json.dumps({"db": db, "url": r.get("url", "")}, ensure_ascii=False))
    tx = lambda v: {"rich_text": [{"text": {"content": v[:1900]}}]}
    d = dt.date.fromisoformat(date)
    props = {"제목": {"title": [{"text": {"content": f"{d.year}.{d.month:02d}.{d.day:02d} 주일예배"}}]}, "예배일": {"date": {"start": date}},
             "설교본문": tx(s["ref"]), "설교제목": tx(s["title"]), "인도자": tx(", ".join(s["leader"])),
             "도입곡": tx(" / ".join(s["intro"])), "본곡": tx("\n".join(f"{i + 1}. {n}" for i, n in enumerate(s["main"]))),
             "적용송": tx(" / ".join(s["apply"])), "곡 수": {"number": len(s["intro"]) + len(s["main"]) + len(s["apply"])}, "악보집": {"url": s["url"]}}
    hit = NC.req("POST", f"/databases/{db}/query", {"filter": {"property": "예배일", "date": {"equals": date}}}).get("results", [])
    if hit:
        NC.req("PATCH", f"/pages/{hit[0]['id']}", {"properties": props}); return hit[0]["url"]
    return NC.req("POST", "/pages", {"parent": {"database_id": db}, "properties": props})["url"]


def prepare(date: str) -> str:
    """주소 연결 + 모음 쪽 + 노션. 반환: 이 주 주소."""
    sid = sid_for(date); route(date, sid)
    pub = set(json.loads(PUBLISHED.read_text())) if PUBLISHED.exists() else set()
    pub.add(date); PUBLISHED.write_text(json.dumps(sorted(pub)))
    index_page()
    try:
        notion(date)
    except Exception as ex:  # noqa: BLE001 — 노션이 막혀도 게시는 한다
        print(f"[노션 기록 실패] {ex}", file=sys.stderr)
    return url(date)


if __name__ == "__main__":
    print(prepare(sys.argv[1]))
