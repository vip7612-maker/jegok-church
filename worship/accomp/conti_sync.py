#!/usr/bin/env python3
"""콘티 편집판(🔒 준비 탭) ↔ 악보집 잇기 (2026-10-03 교장님: 악보를 끌어 옮기며 곡을 확정).

  편집판에서 「💾 확정 저장」 → 예배 DB conti 줄의 rev 가 오른다 → 이 스크립트(맥미니 launchd, 1분마다)가
  rev > built_rev 인 주를 찾아 data/<날짜>.json 의 곡 순서·후보를 바꾸고 악보집·예배 PPT 를 다시 만든 뒤 built_rev 를 맞춘다.

  python3 accomp/conti_sync.py seed 2026-10-04     # 그 주 data json 의 곡·후보를 편집판에 처음 올린다(이미 있으면 그대로)
  python3 accomp/conti_sync.py                     # 저장된 것 반영(맥미니가 1분마다)
  python3 accomp/conti_sync.py --dry-run           # 무엇을 반영할지만 보기
"""
from __future__ import annotations

import datetime as dt, hashlib, json, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import store as S  # noqa: E402

PY = "/usr/local/bin/python3"
ZONES = ("intro", "main", "apply", "pool")
LOG = HERE / "out" / "conti_sync.log"


def _card(x: dict, urls: dict[str, str]) -> dict:
    img = x.get("img") or ""
    if img and not img.startswith("http"):
        img = urls.get(img, "")
    c = {"title": x.get("title") or "", "img": img}
    for k in ("key", "youtube", "used"):
        if x.get(k): c[k] = x[k]
    return c


def seed(date: str) -> str:
    if S.sql("SELECT 1 FROM conti WHERE date=?", date):
        return f"{date} 편집판은 이미 있음 — 그대로"
    d = json.loads((HERE / "data" / f"{date}.json").read_text())
    songs = d.get("songs", {})
    lists = {z: (songs.get(z, []) if z != "pool" else d.get("pool", [])) for z in ZONES}
    local = sorted({x["img"] for v in lists.values() for x in v if x.get("img") and not x["img"].startswith("http") and (HERE / x["img"]).exists()})
    have = S.put_assets([((HERE / p).read_bytes(), Path(p).suffix) for p in local])
    urls = {p: have[S.digest((HERE / p).read_bytes())] for p in local}
    row = {z: [_card(x, urls) for x in lists[z]] for z in ZONES}
    S.sql("INSERT INTO conti(date,intro,main,apply,pool,rev,built_rev,updated) VALUES(?,?,?,?,?,1,1,CURRENT_TIMESTAMP)",
          date, *[json.dumps(row[z], ensure_ascii=False) for z in ZONES])
    return f"{date} 편집판 올림 — " + ", ".join(f"{z} {len(row[z])}" for z in ZONES)


def _local(url: str, date: str) -> str:
    """편집판 그림(Blob 주소) → scores/<날짜>/ 아래 파일(악보집·PPT 만들기는 로컬 파일을 읽는다)."""
    import trim                                          # 악보 바깥 흰 여백은 늘 타이트하게 잘라 붙인다 (2026-10-04 교장님 원칙)
    b = trim.trim_bytes(S._fetch(url))
    h = hashlib.sha256(b).hexdigest()
    for f in (HERE / "scores" / date).glob("*"):        # 이미 있는 같은 그림이면 그 파일을 그대로
        if f.is_file() and f.stat().st_size == len(b) and hashlib.sha256(f.read_bytes()).hexdigest() == h:
            return f"scores/{date}/{f.name}"
    ext = Path(url.split("?")[0]).suffix or ".jpg"
    rel = f"scores/{date}/c{hashlib.sha256(b).hexdigest()[:16]}{ext}"
    f = HERE / rel
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(b)
    return rel


def apply(row: dict) -> list[str]:
    date = row["date"]; out = []
    f = HERE / "data" / f"{date}.json"
    d = json.loads(f.read_text())
    lists = {z: json.loads(row[z] or "[]") for z in ZONES}
    def item(c):
        x = {"title": c.get("title") or "", "img": _local(c["img"], date) if c.get("img", "").startswith("http") else c.get("img", "")}
        for k in ("key", "youtube"):
            if c.get(k): x[k] = c[k]
        return x
    d["songs"] = {z: [item(c) for c in lists[z]] for z in ("intro", "main", "apply")}
    picked = {c.get("title") for z in ("intro", "main", "apply") for c in lists[z]}
    d["pool"] = [dict(item(c), used=c.get("title") in picked) for c in lists["pool"]]
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    out.append(f"{date} 곡 순서: " + " · ".join(c["title"] for z in ("intro", "main", "apply") for c in lists[z]))
    px = HERE / "worship_ppt" / f"{date}.pptx"
    if px.exists():                                   # 예배 PPT 곡 장도 새 순서로(드라이브 파일도 갱신)
        r = subprocess.run([PY, str(HERE / "pptfill.py"), date, "--upload"], capture_output=True, text=True, timeout=1800)
        out.append("예배 PPT: " + (r.stdout.strip().splitlines() or ["?"])[-1] if r.returncode == 0 else f"예배 PPT 실패: {r.stderr[-300:]}")
    r = subprocess.run([PY, str(HERE / "build.py"), date, "--share"], capture_output=True, text=True, timeout=1800)
    out.append("악보집: " + (r.stdout.strip().splitlines() or ["?"])[-1] if r.returncode == 0 else f"악보집 실패: {r.stderr[-300:]}")
    if px.exists():
        try:
            import migrate
            migrate.deck(date); out.append("예배 DB 갱신")
        except Exception as ex:  # noqa: BLE001
            out.append(f"예배 DB 갱신 실패: {ex}")
    return out


def sync(dry: bool = False) -> None:
    rows = S.sql("SELECT * FROM conti WHERE rev > built_rev")
    for row in rows:
        if dry:
            print(row["date"], "rev", row["rev"], ">", row["built_rev"]); continue
        rev = int(row["rev"])
        lines = apply(row)
        S.sql("UPDATE conti SET built_rev=? WHERE date=? AND built_rev<?", rev, row["date"], rev)
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a") as fp:
            fp.write(f"[{dt.datetime.now():%m-%d %H:%M}] rev {rev}\n" + "\n".join("  " + x for x in lines) + "\n")
        print("\n".join(lines))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "seed":
        for date in a[1:]: print(seed(date))
    else:
        sync("--dry-run" in a)
        if "--dry-run" not in a:                       # 악보와 PPT 「➕ 올리기」도 같은 1분 주기로 (uploads.py)
            import uploads
            uploads.run()
            import ppt_pages                           # 예배 PPT 「＋ 장 넣기」 🎨 AI 디자인 페이지
            ppt_pages.run()
