#!/usr/bin/env python3
"""예배 플랫폼 옮기기 — 지금까지 파일로 만들던 것을 DB(Turso)+그림 창고(Blob)로 (2026-10-03 교장님 승인).

  python3 accomp/migrate.py songs [곡명 …]     곡별 PPT(songppt/db) → songs·song_slides·song_uses (다시 돌려도 같은 결과)
  python3 accomp/migrate.py deck 2026-10-04    그 주 예배 PPT → services(배경 그림 지문·글자·곡 참조·목차·내려받기 뼈대)
  python3 accomp/migrate.py scores [N]         드라이브 「찬양 악보 모음」 + 노션 보관함 → scores(그림은 Blob 에 한 번만)
"""
from __future__ import annotations

import base64, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import store as S  # noqa: E402

DB = HERE / "songppt" / "db"
INDEX = HERE / "songppt" / "index.json"


def _ext(b: bytes) -> str:
    return "png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "jpg" if b[:3] == b"\xff\xd8\xff" else "gif" if b[:3] == b"GIF" else "bin"


def push_song(song: dict, rec: dict | None = None) -> int:
    """곡 하나 → DB. 그림은 지문으로(이미 있으면 다시 올리지 않음). 돌려주는 값: 곡 번호."""
    imgs = [base64.b64decode(sl["img"]) for sl in song["slides"]]
    urls = S.put_assets([(b, _ext(b)) for b in imgs])
    rec = rec or {}
    uses = rec.get("uses", [])
    first = next((u.get("first") for u in uses if u.get("first")), "")
    langs = (rec.get("latest") or {}).get("langs", [])
    t = song["title"]
    S.sql("""INSERT INTO songs(title, aliases, first_line, hymn, langs, src_date, src_kind, src_file, check_flag, n, updated)
             VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
             ON CONFLICT(title) DO UPDATE SET aliases=excluded.aliases, first_line=excluded.first_line, hymn=excluded.hymn,
               langs=excluded.langs, src_date=excluded.src_date, src_kind=excluded.src_kind, src_file=excluded.src_file,
               check_flag=excluded.check_flag, n=excluded.n, updated=CURRENT_TIMESTAMP""",
          t, json.dumps(rec.get("aliases", []), ensure_ascii=False), first, song.get("hymn") or rec.get("hymn"),
          json.dumps(langs), song.get("date"), song.get("kind"), song.get("file"), 1 if song.get("check") else 0, len(song["slides"]))
    sid = int(S.sql("SELECT id FROM songs WHERE title=?", t)[0]["id"])
    stmts = [("DELETE FROM song_slides WHERE song_id=?", [sid]), ("DELETE FROM song_uses WHERE song_id=?", [sid])]
    for n, (sl, b) in enumerate(zip(song["slides"], imgs), 1):
        stmts.append(("INSERT INTO song_slides(song_id,n,asset,pic,sub,chips,auto_sub) VALUES(?,?,?,?,?,?,?)",
                      [sid, n, S.digest(b), json.dumps(sl["pic"]), json.dumps(sl.get("sub"), ensure_ascii=False),
                       json.dumps(sl.get("chips", []), ensure_ascii=False), 1 if sl.get("auto_sub") else 0]))
    for u in uses:
        stmts.append(("INSERT OR REPLACE INTO song_uses(song_id,date,kind,file,slides,header) VALUES(?,?,?,?,?,?)",
                      [sid, u.get("date"), u.get("kind"), u.get("file"), json.dumps(u.get("slides")), u.get("header", "")]))
    for i in range(0, len(stmts), 150): S.sql_many(stmts[i:i + 150])
    return sid


def songs(only: list[str] | None = None) -> None:
    ix = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    dirs = sorted(p for p in DB.iterdir() if (p / "song.json").exists())
    done = 0
    for d in dirs:
        song = json.loads((d / "song.json").read_text(encoding="utf-8"))
        if only and song["title"] not in only: continue
        push_song(song, ix.get(song["title"]))
        done += 1
        if done % 20 == 0: print(f"  {done}곡 …", flush=True)
    print(f"곡 {done}개 옮김 ·", json.dumps(S.stats(), ensure_ascii=False))

# ── 예배 PPT(주) → services ─────────────────────────────────────
def _song_row(title: str) -> dict | None:
    key = S.song_find(title)
    if not key: return None
    r = S.sql("SELECT id, title, n FROM songs WHERE title=?", key)
    return r[0] if r else None


def skeleton(pptx: Path, date: str) -> dict:
    """PPT 에서 그림(ppt/media/*)을 빼 그림 창고로 — 남은 글·배치(xml)만 작은 zip 으로. 내려받을 때 브라우저가 다시 합친다."""
    import io, zipfile
    zin = zipfile.ZipFile(pptx); media = {}; items = []
    for n in zin.namelist():
        if n.startswith("ppt/media/"):
            b = zin.read(n); media[n] = S.digest(b); items.append((b, n.rsplit(".", 1)[-1]))
    urls = S.put_assets(items)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for info in zin.infolist():
            if not info.filename.startswith("ppt/media/"): z.writestr(info, zin.read(info.filename))
    b = buf.getvalue(); h = S.digest(b)
    url = S.put_assets([(b, "zip")])[h]
    return {"zip": url, "size": len(b), "media": {n: urls[x] for n, x in media.items()}}


def deck(date: str, pdf: Path | None = None, pptx: Path | None = None) -> dict:
    """그 주 예배 PPT 를 DB 로. 기본 장 = 배경 그림(지문) + 글자 위치, 곡 장 = (곡 번호, 장 번호) 참조, 목차, 내려받기 뼈대."""
    import tempfile
    import slides as SL, pptfill as F
    pptx = pptx or HERE / "worship_ppt" / f"{date}.pptx"; pdf = pdf or HERE / "worship_ppt" / f"{date}.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        base = SL.parse(pdf, Path(tmp) / "s")
        base = SL.rewrap(base, pptx)
        imgs = {s["img"]: (Path(tmp) / "s" / s["img"]).read_bytes() for s in base}
        import fitz
        cover = fitz.open(pdf)[0].get_pixmap(dpi=110).tobytes("jpg")
    urls = S.put_assets([(b, "jpg") for b in imgs.values()] + [(cover, "jpg")])
    d = json.loads((HERE / "data" / f"{date}.json").read_text())
    songs = [(lab, x.get("title", "")) for g, name in (("intro", "도입곡"), ("main", ""), ("apply", "적용송"))
             for i, x in enumerate(d.get("songs", {}).get(g, [])) for lab in [name or str(i + 1)]]
    flat = lambda s: re.sub(r"\s", "", s["plain"])[:40]
    is_div = lambda s: ("찬양과경배" in flat(s) or "찬양과결단" in flat(s)) and len(re.sub(r"\s", "", s["plain"])) < 160
    divs = [k for k, s in enumerate(base) if is_div(s)]
    is_sec = lambda s: any(x in flat(s) for x in SL.SECTIONS)
    if any(k + 1 < len(base) and not is_sec(base[k + 1]) for k in divs):
        divs = []                                    # 가사 장이 이미 든 PPT(예: 9/27) — 곡 장을 또 넣지 않는다
    out, conti, si = [], [], 0
    for k, s in enumerate(base):
        out.append({"img": S.digest(imgs[s["img"]]), "texts": s["texts"], "plain": s["plain"], "hidden": s["hidden"]})
        if k in divs and si < len(songs):
            lab, title = songs[si]; si += 1
            row = _song_row(title) if title else None
            conti.append({"label": lab, "title": title, "song": int(row["id"]) if row else None, "db": row["title"] if row else None})
            if row:
                out += [{"song": int(row["id"]), "sn": j, "plain": row["title"], "hidden": row["title"]} for j in range(1, int(row["n"]) + 1)]
    for n, x in enumerate(out, 1): x["n"] = n
    toc = SL.outline(out, [t for _, t in songs])
    for x in out: x.pop("plain", None); x.pop("hidden", None); x.pop("n", None)
    sk = skeleton(pptx, date)
    st = next((p for p in d["pages"] if p["type"] == "sermon_text"), {})
    leader = ""
    try:
        leader = ", ".join(json.loads((HERE / "roster.json").read_text())["weeks"].get(date, {}).get("인도자", []))
    except Exception:
        pass
    deckj = {"title": f"{int(date[5:7])}월 {int(date[8:10])}일 주일예배 PPT", "cover": urls[S.digest(cover)],
             "slides": out, "toc": toc, "skeleton": sk}
    S.sql("""INSERT INTO services(date, kind, title, ref, leader, conti, deck, skeleton, updated) VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
             ON CONFLICT(date) DO UPDATE SET title=excluded.title, ref=excluded.ref, leader=excluded.leader, conti=excluded.conti,
               deck=excluded.deck, skeleton=excluded.skeleton, updated=CURRENT_TIMESTAMP""",
          date, "주일", st.get("title", ""), st.get("ref", ""), leader, json.dumps(conti, ensure_ascii=False),
          json.dumps(deckj, ensure_ascii=False, separators=(",", ":")), json.dumps(sk))
    return {"slides": len(out), "base": len(base), "toc": len(toc), "skeleton_kb": sk["size"] // 1024, "media": len(sk["media"])}

# ── 악보 → scores (2026-10-03 교장님: 악보도 DB 에서 가져다 쓰기) ─────────────────
SCORE_FOLDER = "1GHYOq02R7nfpuEXl-uxMGyqi0K90dOV5"            # 드라이브 「찬양 악보 모음」(찬송가 악보·CCM 악보)
KEY = re.compile(r"(?:^|[\s(_])([A-G](?:b|#|♭|♯)?m?)(?=$|[\s)_\-])")
NOTES = ("기타", "피아", "피아노", "피아버전", "4:4", "3:4", "원키")


def parse_score_name(name: str) -> tuple[str, str | None, list[str]]:
    """「주와 같이 길 가는 것 E.png」 → (주와 같이 길 가는 것, E, 별칭들). 끝 번호(-1)·확장자·코드·괄호를 뗀다."""
    import songbank
    stem = re.sub(r"\.(png|jpe?g|pdf)$", "", name, flags=re.I)
    stem = re.sub(r"\s*-\s*\d+$", "", stem)
    keys = KEY.findall(stem)
    title, alias = songbank.clean_title(stem.replace("_", " "))
    title = re.sub(r"\s*\((?:[A-G](?:b|#)?m?)\)\s*", " ", title).strip()
    return title, (keys[-1] if keys else None), [a for a in alias if a not in NOTES]


def _save_scores(rows: list[dict]) -> None:
    urls = S.put_assets([(r["bytes"], r["ext"]) for r in rows])
    stmts = []
    for r in rows:
        h = S.digest(r["bytes"])
        stmts.append(("""INSERT INTO scores(title, key, kind, source, ref, asset, page, notion_page, used, aliases) VALUES(?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(ref) DO UPDATE SET title=excluded.title, key=excluded.key, kind=excluded.kind, source=excluded.source,
                           asset=excluded.asset, page=excluded.page, notion_page=excluded.notion_page, used=excluded.used, aliases=excluded.aliases""",
                      [r["title"], r["key"], r["kind"], r["source"], r["ref"], h, r.get("page", 1), r.get("notion"),
                       json.dumps(r.get("used", []), ensure_ascii=False), json.dumps(r.get("aliases", []), ensure_ascii=False)]))
    for i in range(0, len(stmts), 100): S.sql_many(stmts[i:i + 100])


def scores(limit: int | None = None) -> None:
    """드라이브 악보 모음 + 노션 보관함(score_bank.json·bank/) → scores. 다시 돌리면 같은 자리(ref)를 고쳐 쓴다."""
    import concurrent.futures as cf, prep, songbank
    g = prep.G(prep.access_token())
    files = [f for f in songbank.list_tree(g, SCORE_FOLDER, "악보")
             if f["name"].lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "pdf") and not f["name"].startswith("._")]
    done = {r["ref"] for r in S.sql("SELECT ref FROM scores WHERE ref LIKE 'drive:%'")}
    files = [f for f in files if f"drive:{f['id']}:1" not in done][:limit]
    print(f"드라이브 악보 {len(files)}개 옮김 시작", flush=True)

    def one(f):
        for attempt in range(3):                       # 내려받기가 잠깐 끊기면 다시, 그래도 안 되면 그 장만 건너뛴다
            try:
                b = g.req("GET", f"{prep.DRIVE}/files/{f['id']}?alt=media&supportsAllDrives=true", timeout=300); break
            except Exception as e:
                if attempt == 2: print(f"  건너뜀 {f['name']}: {type(e).__name__}", flush=True); return []
        title, key, alias = parse_score_name(f["name"])
        kind = "찬송가" if "찬송가" in f["path"] else "CCM"
        base = {"title": title, "key": key, "kind": kind, "source": f["path"], "aliases": alias}
        if f["name"].lower().endswith(".pdf"):
            import fitz
            doc = fitz.open(stream=b, filetype="pdf")
            return [dict(base, ref=f"drive:{f['id']}:{i}", page=i, bytes=pg.get_pixmap(dpi=150).tobytes("png"), ext="png")
                    for i, pg in enumerate(doc, 1)]
        ext = "png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
        return [dict(base, ref=f"drive:{f['id']}:1", bytes=b, ext=ext)]

    batch, n = [], 0
    with cf.ThreadPoolExecutor(6) as ex:
        for rows in ex.map(one, files):
            batch += rows
            if len(batch) >= 60:
                _save_scores(batch); n += len(batch); batch = []; print(f"  {n}장 …", flush=True)
    if batch: _save_scores(batch); n += len(batch)
    # 노션 보관함
    bank = json.loads((HERE / "score_bank.json").read_text()).get("songs", {})
    rows = []
    for title, rec in bank.items():
        for key, sc in rec.get("scores", {}).items():
            f = HERE / sc["file"]
            if f.exists():
                b = f.read_bytes()
                rows.append({"title": title, "key": key, "kind": "보관함", "source": f"노션 보관함 {sc.get('no', '')} · {sc.get('source', '')}",
                             "ref": f"bank:{sc['file']}", "bytes": b, "ext": f.suffix.lstrip(".").lower().replace("jpeg", "jpg"),
                             "notion": rec.get("page"), "used": sc.get("used", [])})
    if rows: _save_scores(rows)
    print(f"악보 {n}장 + 보관함 {len(rows)}장 옮김 ·", json.dumps(S.stats(), ensure_ascii=False),
          "· 악보 표", S.sql("SELECT COUNT(*) n FROM scores")[0]["n"], flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "songs": songs(a[1:] or None)
    elif a and a[0] == "scores": scores(int(a[1]) if len(a) > 1 else None)
    elif a and a[0] == "deck":
        for d in a[1:]: print(d, deck(d))
    else: print(__doc__)
