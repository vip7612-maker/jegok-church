#!/usr/bin/env python3
"""예배 플랫폼 저장소 — 그림 창고(Vercel Blob) + DB(Turso jegok-worship) (2026-10-03 교장님: 사본 대신 DB 에서 가져다 쓰기).

  · 그림은 내용 지문(sha256)을 이름으로 assets/<앞2>/<지문>.<확장자> 에 한 번만 올린다 — 같은 그림이면 다시 올리지 않는다.
  · DB 는 곡·곡 장·예배(주)·그림 목록만 담는다(그림 자체는 주소만).
  · 비밀값은 ~/dev/daily-briefing/.env 의 WORSHIP_TURSO_URL·WORSHIP_TURSO_TOKEN·BLOB_READ_WRITE_TOKEN.

  python3 accomp/store.py init        표 만들기(이미 있으면 그대로)
  python3 accomp/store.py stats       그림 수·용량·곡 수·예배 수
"""
from __future__ import annotations

import hashlib, json, os, subprocess, sys, tempfile, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV = Path.home() / "dev/daily-briefing/.env"
NODE = Path.home() / ".local/node/bin/node"
PUT = HERE / "tools" / "blob_put.mjs"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS assets (hash TEXT PRIMARY KEY, url TEXT NOT NULL, ext TEXT, size INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS songs (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT UNIQUE NOT NULL, aliases TEXT DEFAULT '[]',
        first_line TEXT DEFAULT '', hymn INTEGER, langs TEXT DEFAULT '[]', src_date TEXT, src_kind TEXT, src_file TEXT,
        check_flag INTEGER DEFAULT 0, n INTEGER DEFAULT 0, updated TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS song_uses (song_id INTEGER, date TEXT, kind TEXT, file TEXT, slides TEXT, header TEXT,
        PRIMARY KEY (song_id, date, kind))""",
    """CREATE TABLE IF NOT EXISTS song_slides (song_id INTEGER, n INTEGER, asset TEXT, pic TEXT, sub TEXT, chips TEXT,
        auto_sub INTEGER DEFAULT 0, PRIMARY KEY (song_id, n))""",
    """CREATE TABLE IF NOT EXISTS services (date TEXT PRIMARY KEY, kind TEXT DEFAULT '주일', title TEXT, ref TEXT, leader TEXT,
        conti TEXT DEFAULT '[]', deck TEXT, skeleton TEXT, updated TEXT DEFAULT CURRENT_TIMESTAMP)""",
]


# ── 비밀값 ─────────────────────────────────────────────────────
def env(key: str) -> str:
    if os.environ.get(key): return os.environ[key]
    for line in ENV.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"{key} 없음 — {ENV} 확인")


# ── DB (Turso HTTP) ────────────────────────────────────────────
def _arg(v):
    if v is None: return {"type": "null"}
    if isinstance(v, bool): v = int(v)
    if isinstance(v, int): return {"type": "integer", "value": str(v)}
    if isinstance(v, float): return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def sql_many(stmts: list[tuple[str, list]]) -> list[list[dict]]:
    """여러 문장을 한 번에(한 묶음은 한 거래). 각 문장 결과는 [{열: 값}…]."""
    url = env("WORSHIP_TURSO_URL").replace("libsql://", "https://") + "/v2/pipeline"
    reqs = [{"type": "execute", "stmt": {"sql": s, "args": [_arg(a) for a in args]}} for s, args in stmts] + [{"type": "close"}]
    req = urllib.request.Request(url, data=json.dumps({"requests": reqs}).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + env("WORSHIP_TURSO_TOKEN"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.load(r)["results"]
    out = []
    for x in res[:-1]:
        if x["type"] != "ok": raise RuntimeError(f"DB 오류: {x.get('error')}")
        rs = x["response"]["result"]; cols = [c["name"] for c in rs["cols"]]
        out.append([{c: (v.get("value") if v["type"] != "null" else None) for c, v in zip(cols, row)} for row in rs["rows"]])
    return out


def sql(q: str, *args) -> list[dict]:
    return sql_many([(q, list(args))])[0]


def init() -> None:
    sql_many([(s, []) for s in SCHEMA])


# ── 그림 창고 ──────────────────────────────────────────────────
TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif",
         "zip": "application/zip", "emf": "image/x-emf", "wmf": "image/x-wmf", "svg": "image/svg+xml", "json": "application/json"}


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def put_assets(items: list[tuple[bytes, str]]) -> dict[str, str]:
    """[(바이트, 확장자)] → {지문: 주소}. DB 에 이미 있는 지문은 올리지 않는다(같은 그림은 한 번만)."""
    want = {}
    for b, ext in items:
        h = digest(b); want.setdefault(h, (b, ext.lower().lstrip(".")))
    have = {}
    hs = list(want)
    for i in range(0, len(hs), 400):
        part = hs[i:i + 400]
        for r in sql(f"SELECT hash, url FROM assets WHERE hash IN ({','.join('?' * len(part))})", *part):
            have[r["hash"]] = r["url"]
    new = [h for h in want if h not in have]
    if new:
        with tempfile.TemporaryDirectory() as tmp:
            lines = []
            for h in new:
                b, ext = want[h]; f = Path(tmp) / f"{h}.{ext}"; f.write_bytes(b)
                lines.append(json.dumps({"path": f"assets/{h[:2]}/{h}.{ext}", "file": str(f), "type": TYPES.get(ext, "application/octet-stream")}))
            r = subprocess.run([str(NODE), str(PUT)], input="\n".join(lines), capture_output=True, text=True, timeout=3600,
                               cwd=str(PUT.parent), env={**os.environ, "BLOB_READ_WRITE_TOKEN": env("BLOB_READ_WRITE_TOKEN")})
            got = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
            bad = [g for g in got if "error" in g]
            if bad: raise RuntimeError(f"그림 올리기 실패 {len(bad)}건: {bad[0]['error'][:200]}")
            stmts = []
            for g in got:
                h = Path(g["path"]).stem; b, ext = want[h]; have[h] = g["url"]
                stmts.append(("INSERT OR IGNORE INTO assets(hash,url,ext,size) VALUES(?,?,?,?)", [h, g["url"], ext, len(b)]))
            for i in range(0, len(stmts), 200): sql_many(stmts[i:i + 200])
    return have


def stats() -> dict:
    a = sql("SELECT COUNT(*) n, COALESCE(SUM(size),0) bytes FROM assets")[0]
    return {"그림": int(a["n"]), "용량MB": round(int(a["bytes"]) / 1e6, 1),
            "곡": int(sql("SELECT COUNT(*) n FROM songs")[0]["n"]), "곡 장": int(sql("SELECT COUNT(*) n FROM song_slides")[0]["n"]),
            "예배": int(sql("SELECT COUNT(*) n FROM services")[0]["n"])}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "init": init(); print("표 준비됨")
    elif a and a[0] == "stats": print(json.dumps(stats(), ensure_ascii=False))
    else: print(__doc__)
