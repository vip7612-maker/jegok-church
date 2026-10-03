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


def index_page() -> None:
    dates = sorted(json.loads(PUBLISHED.read_text()) if PUBLISHED.exists() else [], reverse=True)
    cards = []
    for x in dates:
        s = summary(x); d = dt.date.fromisoformat(x)
        songs = "".join(f"<li><b>{lab}</b>{html.escape(n)}</li>" for lab, n in
                        [("도입", n) for n in s["intro"]] + [(str(i + 1), n) for i, n in enumerate(s["main"])] + [("적용", n) for n in s["apply"]])
        cards.append(f'''<a class="c" href="{s["url"]}"><div class="d"><b>{d.month}.{d.day}</b><span>{d.year}</span></div>
<div class="m"><h3>{html.escape(s["title"] or "주일예배")}</h3><p>{html.escape(s["ref"])}{" · 인도 " + html.escape(", ".join(s["leader"])) if s["leader"] else ""}</p>
<ol>{songs}</ol></div><span class="go">악보집 열기 →</span></a>''')
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>제곡교회 예배팀 · 주일예배 악보집</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:'Pretendard Variable',Pretendard,sans-serif;background:#f3f4f8;color:#0b1430}}
header{{background:linear-gradient(160deg,#0b1430,#172a5e 55%,#2b2f6e);color:#fff;padding:34px 22px 28px}}
header .k{{font-size:11px;letter-spacing:.35em;color:#f6c76b;font-weight:800}}header h1{{margin:8px 0 4px;font-size:28px}}header p{{margin:0;color:#c7d2fe;font-size:14px}}
main{{max-width:860px;margin:-14px auto 40px;padding:0 14px;display:flex;flex-direction:column;gap:12px}}
.c{{display:flex;gap:16px;align-items:flex-start;background:#fff;border-radius:16px;padding:16px 18px;text-decoration:none;color:inherit;box-shadow:0 2px 10px rgba(11,20,48,.08);position:relative}}
.c:first-child{{outline:2px solid #f6c76b}}
.d{{flex:0 0 64px;text-align:center;background:#0b1430;color:#fff;border-radius:12px;padding:10px 0}}.d b{{display:block;font-size:22px}}.d span{{font-size:11px;color:#c7d2fe}}
.m{{flex:1;min-width:0}}.m h3{{margin:2px 0 4px;font-size:18px}}.m p{{margin:0 0 8px;color:#64748b;font-size:13px}}
ol{{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}}li{{font-size:12.5px;background:#f1f5f9;border-radius:8px;padding:3px 9px}}li b{{color:#1e3a8a;margin-right:5px}}
.go{{position:absolute;right:16px;top:16px;font-size:12px;font-weight:700;color:#b8860b}}
@media(max-width:560px){{.go{{display:none}}}}
</style></head><body>
<header><span class="k">JEGOK CHURCH · WORSHIP TEAM</span><h1>주일예배 악보집</h1><p>반주자·싱어용 · {len(dates)}주 · 최신 주가 맨 위</p></header>
<main>{"".join(cards) or "<p>아직 없음</p>"}</main></body></html>"""
    (SITE / INDEX).mkdir(exist_ok=True)
    (SITE / INDEX / "index.html").write_text(doc)


# ── 노션 ──────────────────────────────────────────────
def notion(date: str) -> str:
    import notion_conti as NC   # 같은 토큰·요청 함수(제곡교회 찬양팀 페이지 아래)
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
