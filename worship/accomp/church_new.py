#!/usr/bin/env python3
"""새 교회 열기 — Worship Desk 를 다른 교회에 나눌 때 첫 세팅 (2026-10-07 교장님, 테스트베드: /church 예수교회).

  python3 accomp/church_new.py add church 예수교회 홍길동     # 교회·관리자 자리를 만든다(비밀번호는 비워 둠)
  python3 accomp/church_new.py link church 홍길동             # 그 관리자가 비밀번호를 처음 정하는 링크(교장님이 직접 실행해 전달)
  python3 accomp/church_new.py show church                    # 지금 세팅 보기

하는 일
  1. 예배 DB 에 교회 이름(wor_settings.name)과 관리자 자리(wor_users, role=admin, 비밀번호 없음)를 만든다.
  2. 예배 구분은 그 교회 관리자 화면을 처음 열 때 기본 네 가지(주일·수요·금요·새벽)가 들어간다 — 관리자가 고치고 지운다.
  3. worship-desk 주소(/<교회>/)는 worship-desk/churches.json 에 한 줄 더하고 gen.py 로 만든다(app: 공용 화면).
비밀번호는 만들지 않는다 — 관리자가 링크를 열어 직접 정한다.
"""
from __future__ import annotations
import json, re, sys, urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
WD = Path.home() / "dev/worship-desk"
SLUG = re.compile(r"^[a-z0-9-]{2,30}$")
NAME = re.compile(r"^[가-힣A-Za-z][가-힣A-Za-z ]{0,19}$")


def _db(stmts):
    import wadmin
    return wadmin.batch(stmts)


def add(slug: str, church: str, admin: str) -> None:
    if not SLUG.match(slug): sys.exit("교회 주소 열쇠는 영문 소문자·숫자·- 2~30자")
    if not NAME.match(admin): sys.exit("관리자 이름은 한글·영문 20자 안")
    import wadmin
    _db(wadmin.SCHEMA)
    _db([("INSERT INTO wor_settings(church,k,v) VALUES(?,?,?) ON CONFLICT(church,k) DO UPDATE SET v=excluded.v", [slug, "name", church]),
         ("INSERT INTO wor_users(church,name,title,role,hash,ver,active,at) VALUES(?,?,?,?,NULL,0,1,datetime('now')) "
          "ON CONFLICT(church,name) DO UPDATE SET role='admin', active=1", [slug, admin, "", "admin"])])
    cs = json.loads((WD / "churches.json").read_text())
    if not any(c["slug"] == slug for c in cs):
        cs.append({"slug": slug, "name": church, "src": "wd", "app": "jegok_worship"})
        (WD / "churches.json").write_text(json.dumps(cs, ensure_ascii=False) + "\n")
    print(f"교회 {church}({slug}) · 관리자 {admin} 자리를 만들었습니다.")
    print(f"주소: https://worship-desk.vercel.app/{slug}/   (worship-desk 에서 python3 gen.py 뒤 배포)")
    print(f"비밀번호 정하기 링크: python3 accomp/church_new.py link {slug} {admin}")


def link(slug: str, name: str) -> None:
    import wadmin
    r = _db([("SELECT ver,hash FROM wor_users WHERE church=? AND name=?", [slug, name])])[0]
    if not r: sys.exit(f"{slug} 교회에 {name} 님 자리가 없습니다(먼저 add)")
    if r[0]["hash"]: sys.exit(f"{name} 님은 이미 비밀번호가 있습니다. 바꾸려면 관리자 화면에서 [비밀번호 초기화]")
    key = wadmin.setup_key(slug, name, int(r[0]["ver"] or 0), wadmin.env()["JUBO_SECRET"])
    print(f"https://worship-desk.vercel.app/{slug}/admin.html?setup={slug}.{urllib.parse.quote(name)}.{key}")


def show(slug: str) -> None:
    s = _db([("SELECT k,v FROM wor_settings WHERE church=? AND k NOT LIKE '\\_%' ESCAPE '\\'", [slug]),
             ("SELECT name,role,active,hash IS NOT NULL AS ready FROM wor_users WHERE church=?", [slug]),
             ("SELECT id,name,days,time FROM wor_svc WHERE church=? AND COALESCE(active,1)=1 ORDER BY ord", [slug])])
    print("교회 정보:", {r["k"]: r["v"] for r in s[0]})
    print("계정:", [(r["name"], r["role"], "비밀번호 정함" if r["ready"] == "1" else "비밀번호 정하기 전") for r in s[1]])
    print("예배 구분:", [(r["name"], r["days"], r["time"]) for r in s[2]] or "관리자 화면을 처음 열면 기본 네 가지")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["add"] and len(a) == 4: add(a[1], a[2], a[3])
    elif a[:1] == ["link"] and len(a) == 3: link(a[1], a[2])
    elif a[:1] == ["show"] and len(a) == 2: show(a[1])
    else: print(__doc__)
