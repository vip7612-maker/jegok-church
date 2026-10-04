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


def past_services() -> list[dict]:
    """곡 스캔(songppt/scan)으로 찾은 지난 예배(2021~ 주일·수요·금요…) — 날짜·종류·곡·원본 PPT."""
    out = []
    for f in sorted((HERE / "songppt" / "scan").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        src = d["src"]
        if not src.get("date") or "0000" in src["name"] or "템플릿" in src.get("path", ""): continue   # 예배준비 템플릿은 예배가 아니다
        link = (f"https://docs.google.com/presentation/d/{src['id']}/edit" if src["mimeType"].endswith("google-apps.presentation")
                else f"https://drive.google.com/file/d/{src['id']}/view")
        out.append({"date": src["date"], "kind": src["kind"], "songs": [g["title"] for g in d["groups"]], "src": link})
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
    data = json.dumps(sorted(items, key=lambda i: i["date"], reverse=True), ensure_ascii=False).replace("</", "<\\/")
    doc = LANDING.replace("@@DATA@@", data)
    (SITE / INDEX).mkdir(exist_ok=True)
    (SITE / INDEX / "index.html").write_text(doc)


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
@media(max-width:560px){.ready{aspect-ratio:auto;min-height:220px}.ready .msg br{display:none}header{padding:24px 16px 80px}.go{display:none}.hero{padding:12px}.d{flex-basis:48px}}
</style></head><body>
<header><span class="k">JEGOK CHURCH · WORSHIP TEAM</span><h1>제곡교회 예배 플랫폼</h1></header>
<main><section class="hero" id="hero"></section>
<h3 class="sec">지난 예배 <span id="cnt"></span></h3><div class="list" id="list"></div><div class="pg" id="pg"></div></main>
<script id="data" type="application/json">@@DATA@@</script>
<script>
const ALL=JSON.parse(document.getElementById('data').textContent);
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const kst=new Date(Date.now()+9*3600e3), TODAY=(new URLSearchParams(location.search).get('today'))||kst.toISOString().slice(0,10);   // ?today= 은 미리 보기용
const W='일월화수목금토';
const md=d=>{const x=new Date(d+'T00:00:00Z');return (x.getUTCMonth()+1)+'월 '+x.getUTCDate()+'일('+W[x.getUTCDay()]+')';};
function nextSunday(){const x=new Date(TODAY+'T00:00:00Z');x.setUTCDate(x.getUTCDate()+((7-x.getUTCDay())%7||7));return x.toISOString().slice(0,10);}
const sundays=ALL.filter(i=>i.ppt);
const today=sundays.find(i=>i.date===TODAY);
function hero(){const h=document.getElementById('hero');
  if(today){const i=today;
    h.innerHTML='<div class="row"><span class="tag live">● 오늘 · '+md(i.date)+'</span><span class="who">'+(i.leader.length?'인도 '+esc(i.leader.join(', ')):'')+'</span></div>'
      +'<a class="shot" href="'+i.ppt+'" style="background-image:url(\''+i.cover+'\')"></a>'
      +'<h2>'+esc(i.title||'주일예배')+'</h2><p class="ref">'+esc(i.ref)+'</p>'
      +'<div class="btns"><a class="p" href="'+i.ppt+'">▶ 예배용 PPT 열기</a><a href="'+i.book+'">예배자 악보</a></div>';
    return;}
  const up=sundays.filter(i=>i.date>TODAY).sort((a,b)=>a.date<b.date?-1:1)[0];
  const day=up?up.date:nextSunday();
  const left=Math.round((new Date(day)-new Date(TODAY))/864e5);
  h.innerHTML='<div class="row"><span class="tag">준비 중 · '+md(day)+'</span><span class="who">'+(up&&up.leader.length?'인도 '+esc(up.leader.join(', ')):'')+'</span></div>'
    +'<div class="ready"><div class="big">예배 준비 중</div><div class="when">'+md(day)+' 주일예배'+(left>0?' · '+left+'일 남음':'')+'</div>'
    +'<div class="msg">함께 예배를 준비하는 동역자 여러분, 고맙습니다.<br> 이번 한 주도 말씀과 찬양으로 마음을 준비해 주세요.<br> 주일 아침, 기쁨으로 만나요.</div></div>'
    +(up?'<h2>'+esc(up.title||'주일예배')+'</h2><p class="ref">'+esc(up.ref)+'</p>'
      +(up.songs.length?'<ul class="chips">'+up.songs.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ul>':'')
      +'<div class="btns"><a href="'+up.book+'">예배자 악보 미리 보기</a><a href="'+up.ppt+'">예배 PPT 미리 보기</a></div>':'');}
const PAST=ALL.filter(i=>i!==today&&i.date<=TODAY), PER=10;
function list(p){const n=Math.max(1,Math.ceil(PAST.length/PER)); p=Math.min(Math.max(1,p),n);
  document.getElementById('cnt').textContent=PAST.length+'개 · '+p+'/'+n+'쪽';
  document.getElementById('list').innerHTML=PAST.slice((p-1)*PER,p*PER).map(i=>{const x=new Date(i.date+'T00:00:00Z');
    const href=i.ppt||i.src, t=i.ppt?(i.title||'주일예배'):(i.kind+'예배');
    const sub=(i.ref?i.ref+' · ':'')+(i.songs.length?i.songs.join(' · '):'곡 정보 없음');
    return '<a class="it" href="'+href+'"'+(i.ppt?'':' target="_blank" rel="noopener"')+'><div class="d"><b>'+(x.getUTCMonth()+1)+'.'+x.getUTCDate()+'</b><span>'+x.getUTCFullYear()+'</span></div>'
      +'<div class="m"><div class="t">'+esc(t)+(i.kind!=='주일'?'<span class="kind">'+esc(i.kind)+'</span>':'')+'</div><div class="s">'+esc(sub)+'</div></div>'
      +'<span class="go">'+(i.ppt?'PPT · 악보 →':'원본 PPT ↗')+'</span></a>';}).join('')||'<div class="it">아직 없음</div>';
  const pg=document.getElementById('pg'); let b='<button '+(p<=1?'disabled':'')+' data-p="'+(p-1)+'">◀ 이전</button>';
  const a=Math.max(1,Math.min(p-2,n-4)), z=Math.min(n,a+4);
  for(let k=a;k<=z;k++) b+='<button class="'+(k===p?'on':'')+'" data-p="'+k+'">'+k+'</button>';
  b+='<button '+(p>=n?'disabled':'')+' data-p="'+(p+1)+'">다음 ▶</button>'; pg.innerHTML=b;
  pg.querySelectorAll('button').forEach(x=>x.onclick=()=>{location.hash='p='+x.dataset.p;});}
function route(){list(+((location.hash.match(/p=(\d+)/)||[])[1]||1));}
addEventListener('hashchange',()=>{route();document.getElementById('cnt').scrollIntoView({behavior:'smooth'});});
hero(); route();
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
