#!/usr/bin/env python3
"""예배 플랫폼 관리자·인도자 계정 — 맥미니 쪽 손잡이 (2026-10-07 교장님).

  python3 accomp/wadmin.py sync          # 교회 정보 첫값·예배별 인도(섬김표·services.json)·준비 탭 열쇠·관리자(이경진) 자리를 DB 에 맞춘다
  python3 accomp/wadmin.py link 이경진    # 그 사람이 비밀번호를 처음 정하는 링크를 찍는다(교장님이 직접 실행)
  python3 accomp/wadmin.py link --admin  # 관리자(이경진) 링크

웹 API 는 daily-briefing/report-site/api/wadmin.js. 표: wor_users · wor_settings · wor_assign (예배 DB).
publish.prepare() 가 게시할 때마다 sync 를 부른다(섬김표 인도자·준비 열쇠가 늘 맞게).
교회 정보는 처음 한 번만 넣고, 그 뒤로는 관리자 화면에서 고친 값을 덮어쓰지 않는다.
"""
from __future__ import annotations
import hashlib, hmac, json, sys, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV = Path.home() / "dev/daily-briefing/.env"
CHURCH = "jegok"
ADMIN = "이경진"
SITE = "https://report-site-kohl.vercel.app"
# 10/4 주보에서 읽은 값(지어내지 않음). 담임목사는 확인 전이라 비워 둔다 — 관리자 화면에서 넣는다.
SEED = {"name": "제곡교회", "denom": "대한예수교장로회", "zip": "25106", "address": "강원도 홍천군 남면 남노일로 578",
        "phone": "033-435-4722", "phone2": "010-4449-0091",
        "times": "주일예배 오전 10:30 · 수요예배 저녁 7:30 · 금요예배 저녁 7:30 · 새벽예배 월~금 오전 5:00"}


def env() -> dict:
    out = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return out


def batch(stmts: list) -> list:
    e = env()
    url = e["WORSHIP_TURSO_URL"].replace("libsql://", "https://") + "/v2/pipeline"
    arg = lambda v: {"type": "null"} if v is None else {"type": "integer", "value": str(v)} if isinstance(v, int) else {"type": "text", "value": str(v)}
    body = {"requests": [{"type": "execute", "stmt": {"sql": s, "args": [arg(a) for a in args]}} for s, args in stmts] + [{"type": "close"}]}
    r = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + e["WORSHIP_TURSO_TOKEN"], "Content-Type": "application/json"})
    res = json.load(urllib.request.urlopen(r, timeout=30))["results"][:len(stmts)]
    out = []
    for x in res:
        if x["type"] != "ok": raise RuntimeError(x.get("error"))
        cols = [c["name"] for c in x["response"]["result"]["cols"]]
        out.append([dict(zip(cols, [None if v["type"] == "null" else v["value"] for v in row])) for row in x["response"]["result"]["rows"]])
    return out


SCHEMA = [
    ("CREATE TABLE IF NOT EXISTS wor_users (church TEXT, name TEXT, title TEXT, role TEXT, hash TEXT, ver INTEGER DEFAULT 0, active INTEGER DEFAULT 1, at TEXT, PRIMARY KEY (church, name))", []),
    ("CREATE TABLE IF NOT EXISTS wor_settings (church TEXT, k TEXT, v TEXT, PRIMARY KEY (church, k))", []),
    ("CREATE TABLE IF NOT EXISTS wor_assign (church TEXT, svc TEXT, date TEXT, leader TEXT, preacher TEXT, PRIMARY KEY (church, svc, date))", []),
]


def sync_statements(roster_weeks: dict, services: dict, prep_key: str, church: str = CHURCH) -> list:
    """DB 에 넣을 문장들(시험하기 쉽게 따로). 교회 정보·평소 인도는 없을 때만, 주일 날짜별 인도·준비 열쇠는 늘 맞춘다."""
    st = list(SCHEMA)
    st += [("INSERT INTO wor_settings(church,k,v) VALUES(?,?,?) ON CONFLICT(church,k) DO NOTHING", [church, k, v]) for k, v in SEED.items()]
    for svc in ("wed", "fri", "dawn"):
        r = services.get(svc) or {}
        if r.get("인도") or r.get("설교"):
            st.append(("INSERT INTO wor_assign(church,svc,date,leader,preacher) VALUES(?,?,'',?,?) ON CONFLICT(church,svc,date) DO NOTHING",
                       [church, svc, (r.get("인도") or "").split()[0] if r.get("인도") else "", r.get("설교", "")]))
    for date, w in sorted(roster_weeks.items()):
        names = ", ".join(w.get("인도자") or [])
        if names:   # 섬김표가 바뀌면 따라간다 — 관리자 화면에서 그날을 고쳤으면 그 값이 섬김표보다 늦게 들어가므로 다음 게시 때 섬김표로 돌아간다(섬김표를 고칠 것)
            st.append(("INSERT INTO wor_assign(church,svc,date,leader,preacher) VALUES(?,'sun',?,?,'') ON CONFLICT(church,svc,date) DO UPDATE SET leader=excluded.leader",
                       [church, date, names]))
    if prep_key:
        st.append(("INSERT INTO wor_settings(church,k,v) VALUES(?,'_prep_key',?) ON CONFLICT(church,k) DO UPDATE SET v=excluded.v", [church, prep_key]))
    st.append(("INSERT INTO wor_users(church,name,title,role,hash,ver,active,at) VALUES(?,?,?,?,NULL,0,1,datetime('now')) ON CONFLICT(church,name) DO UPDATE SET role='admin', active=1",
               [church, ADMIN, "", "admin"]))
    return st


def sync() -> None:
    import build
    roster = json.loads((HERE / "roster.json").read_text()).get("weeks", {})
    services = json.loads((HERE / "services.json").read_text()) if (HERE / "services.json").exists() else {}
    batch(sync_statements(roster, services, build.prep_pass()))
    print("동기화: 교회 정보(처음만)·예배별 인도·준비 열쇠·관리자", ADMIN)


def setup_key(church: str, name: str, ver: int, secret: str) -> str:
    return hmac.new(secret.encode(), f"wor-setup:{church}:{name}:{ver}".encode(), hashlib.sha256).hexdigest()[:32]   # api/wadmin.js setupKey 와 같아야 한다


def link(name: str) -> None:
    r = batch([("SELECT ver,hash FROM wor_users WHERE church=? AND name=?", [CHURCH, name])])[0]
    if not r: sys.exit(f"{name} 님 계정이 없습니다(먼저 sync 또는 관리자 화면에서 추가)")
    if r[0]["hash"]: sys.exit(f"{name} 님은 이미 비밀번호가 있습니다. 바꾸려면 관리자 화면에서 [비밀번호 초기화]")
    key = setup_key(CHURCH, name, int(r[0]["ver"] or 0), env()["JUBO_SECRET"])
    print(f"{SITE}/jegok_worship/admin.html?setup={CHURCH}.{urllib.parse.quote(name)}.{key}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["sync"]: sync()
    elif a[:1] == ["link"] and len(a) == 2: link(ADMIN if a[1] == "--admin" else a[1])   # --admin: 터미널에 한글을 못 칠 때
    else: print(__doc__)
