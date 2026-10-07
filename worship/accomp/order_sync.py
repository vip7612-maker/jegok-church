#!/usr/bin/env python3
"""예배순서 ↔ 주보 ↔ 주일예배 PPT 상호 동기화 (2026-10-07 교장님).

기준은 예배 DB 의 예배순서(wor_order, 예배준비 화면). 세 갈래로 맞춘다.
  1. 주보첨부 → 맥미니가 주보를 읽어 순서에 맡은 분·설교 제목·성경 본문을 채운다(빈 칸만, 지우지 않음).
     주보에만 있는 순서는 앞 순서 뒤에 끼운다. 같은 파일을 PPT 용 주보(jubo/<날짜>.hwp 등)로도 둔다.
  2. 순서확정(rev 오름) → 그 순서대로 PPT 순서 표지를 다시 놓는다(지우면 빠지고, 옮기면 따라가고, 없는 순서는 새 표지).
     딸린 장(성경암송 절·사도신경 본문·소식·봉독 구절)은 표지를 따라간다. 맡은 분·제목·본문은 순서 값이 주보보다 먼저.
  3. PPT 를 만든 뒤 실제로 들어간 순서(그 주에만 끼운 선교 보고 등 포함)를 예배순서에 다시 적는다 — PPT → 예배순서.

  python3 accomp/order_sync.py            # 한 번 돌기(conti_sync 가 1분마다 부른다)
  python3 accomp/order_sync.py --dry-run  # 할 일만 보기
"""
from __future__ import annotations
import copy, datetime as dt, html, json, re, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = "/usr/local/bin/python3"
LOG = HERE / "out" / "order_sync.log"
CHURCH = "jegok"

# ── 순서 이름 ─────────────────────────────────────────────────────────────
# 「찬송」「찬양」 = 새벽·수요의 여는 찬양 → 찬양과 경배 표지(곡이 그 아래, 2026-10-07)
_ALIAS = {"성경암송": "성경암송", "암송": "성경암송", "찬송": "찬양과경배", "찬양": "찬양과경배", "찬양과경배": "찬양과경배", "경배와찬양": "찬양과경배", "사도신경": "사도신경",
          "대표기도": "대표기도", "기도": "대표기도", "교회소식": "교회소식", "광고": "교회소식", "봉헌": "봉헌",
          "성경봉독": "성경봉독", "봉독": "성경봉독", "특송": "특송", "특별찬양": "특송", "설교": "설교", "말씀": "설교",
          "찬양과결단": "찬양과결단", "결단찬양": "찬양과결단", "축도": "축도"}
_SHOW = {"찬양과경배": "찬양과 경배", "찬양과결단": "찬양과 결단"}
# 맡은 분 칸 — 예배준비 화면(prep.html ROLE)과 같아야 한다
FIELDS = {"대표기도": ("who",), "봉헌": ("who",), "특송": ("who",), "축도": ("who",), "성경봉독": ("who", "ref"), "설교": ("who", "title")}
# 주일 기본 순서 = 템플릿 PPT 순서(찬양과 경배는 사도신경 앞뒤로 둘). api/wadmin.js defaultOrder 와 같아야 한다
DEFAULT_SUN = [{"t": x} for x in ["성경암송", "찬양과 경배", "사도신경", "찬양과 경배", "대표기도", "교회소식", "봉헌", "성경봉독",
                                  "특송", "설교", "찬양과 결단", "축도"]]


def norm(t: str) -> str:
    return re.sub(r"\s", "", html.unescape(re.sub(r"<br\s*/?>", " ", str(t or ""), flags=re.I)))


def canon(t: str) -> str:
    n = norm(t)
    return _ALIAS.get(n, n)


def show(c: str) -> str:
    return _SHOW.get(c, c)


def _clean(x: str, pdf: bool = False) -> str:
    x = html.unescape(re.sub(r"\s*<br\s*/?>\s*", " ", x or "", flags=re.I))
    x = re.sub(r"\s+", " ", x).strip()
    if pdf:   # PDF 는 글자 사이에 빈칸이 끼어 나온다(「올 랴 선교사」) → 붙인 뒤 직분 앞만 띄운다 (ppt_tpl.jubo_info 와 같은 규칙)
        x = re.sub(r"\s+", "", x)
        x = re.sub(r"(?<=\S)(목사|전도사|선교사|장로|권사|집사|학생|어린이|청년|가정)$", r" \1", x)
    return x


# ── 1. 주보 → 순서 ────────────────────────────────────────────────────────
def jubo_items(rows: list[list[str]], pdf: bool = False) -> list[dict]:
    """주보 순서표 줄 → 예배순서 줄. 규칙은 jubo_rules(교회마다 다른 주보 꼴, 2026-10-07)."""
    import jubo_rules
    return jubo_rules.items_from_rows([r for r in rows if r and jubo_rules.name_of(r[0]) is not False])


def word(md: str, d: dict) -> tuple[str, str]:
    """주보 「오늘의 말씀」의 설교 제목·본문. HWP 는 jubo_form.parse 가 읽고(s_title·s_ref), PDF 는 표 안에 들어 있어 따로 찾는다."""
    t, r = d.get("s_title", ""), d.get("s_ref", "")
    if not t:
        m = re.search(r"오늘의\s*말씀\s*</th>\s*</tr>\s*<tr>\s*<td>(.*?)<br>\s*(\([^)]*\))", md or "", re.S)
        if m: t, r = m.group(1), m.group(2)
    return _clean(t), _clean(r).strip("()").strip()


def fill_word(items: list[dict], w: tuple[str, str]) -> list[dict]:
    """순서표에 설교 제목·봉독 본문이 비었으면 「오늘의 말씀」 값으로."""
    title, ref = w; out = [dict(x) for x in items]
    for x in out:
        c = canon(x["t"])
        if c == "설교" and title and not x.get("title"): x["title"] = title
        if c == "성경봉독" and ref and not x.get("ref"): x["ref"] = ref
    return out


def merge_jubo(items: list[dict], jubo: list[dict]) -> list[dict]:
    """빈 칸만 채우고 지우지 않는다. 주보에만 있는 순서는 바로 앞에서 맞춘 순서 뒤에 끼운다."""
    res = [dict(x) for x in items]; used: set[int] = set(); last = -1
    for j in jubo:
        c = canon(j["t"])
        i = next((k for k, x in enumerate(res) if k not in used and canon(x["t"]) == c), None)
        if i is None:
            i = last + 1; res.insert(i, dict(j)); used = {u + 1 if u >= i else u for u in used}
        else:
            for f in ("who", "title", "ref"):
                if j.get(f) and not res[i].get(f): res[i][f] = j[f]
        used.add(i); last = i
    return res


def order_info(items: list[dict], info: dict) -> dict:
    """순서에 적은 맡은 분·제목·본문을 PPT 채우기 값(ppt_tpl.jubo_info 꼴)에 얹는다 — 순서 값이 먼저, 빈 칸은 주보 값."""
    info = dict(info); first = {}
    for x in items: first.setdefault(canon(x["t"]), x)
    g = lambda c, f: (first.get(c) or {}).get(f, "")
    if g("대표기도", "who"): info["prayer"] = g("대표기도", "who")
    if g("봉헌", "who"): info["offering"] = g("봉헌", "who")
    if g("특송", "who"): info["special"] = g("특송", "who")
    if "설교" in first:
        o = info.get("sermon", ("", "")); info["sermon"] = (g("설교", "who") or o[0], g("설교", "title") or o[1])
    if "성경봉독" in first:
        o = info.get("reading", ("", "")); info["reading"] = (g("성경봉독", "who") or o[0], g("성경봉독", "ref") or o[1])
    return info


def _from_info(c: str, info: dict) -> dict:
    v = {}
    if c == "대표기도" and info.get("prayer"): v["who"] = info["prayer"]
    if c == "봉헌" and info.get("offering"): v["who"] = info["offering"]
    if c == "특송" and info.get("special"): v["who"] = info["special"]
    if c == "설교" and info.get("sermon"):
        who, title = info["sermon"]
        if who: v["who"] = who
        if title: v["title"] = title
    if c == "성경봉독" and info.get("reading"):
        who, ref = info["reading"]
        if who: v["who"] = who
        if ref: v["ref"] = ref
    return v


# ── 2. 순서 → PPT ─────────────────────────────────────────────────────────
def cover_title(s: dict) -> str | None:
    """순서 표지의 큰 제목(성경암송·찬양과경배 …). 맨 앞 표지는 「주일예배」, 끝 장(예배를 마칩니다)은 None."""
    t = next((x["t"] for x in s.get("texts", []) if x.get("s", 0) >= 100 and isinstance(x.get("t"), str) and x["t"].strip()), None)
    return None if t is None or norm(t) == "예배를마칩니다" else t


def _is_end(s: dict) -> bool:
    return any(x.get("s", 0) >= 100 and norm(x.get("t", "")) == "예배를마칩니다" for x in s.get("texts", []))


def restructure(slides: list[dict], items: list[dict] | None, info: dict) -> list[dict]:
    """맨 앞 표지 + 순서마다 (표지 + 딸린 장) + 끝 장. items 가 없으면 템플릿 순서 그대로(PPT → 예배순서로 적을 목록).
    표지마다 _sec(순서 한 줄)를 달아 둔다 — sections() 가 다시 읽는다."""
    import slides as S
    slides = S.collapse_covers(slides)
    head = slides[:1]; body = slides[1:]
    k_end = next((i for i, s in enumerate(body) if _is_end(s)), len(body))
    tail = body[k_end:]; body = body[:k_end]
    segs: list[tuple[str, list[dict]]] = []
    for s in body:
        t = cover_title(s)
        if t: segs.append((canon(t), [s]))
        elif segs: segs[-1][1].append(s)
        else: head.append(s)
    if items is None:
        items = [{"t": show(c)} for c, _ in segs]
    pool: dict[str, list[int]] = {}
    for i, (c, _) in enumerate(segs): pool.setdefault(c, []).append(i)
    base = next((g[0] for c, g in segs if c == "특송"), None) or next((g[0] for _, g in segs), None)
    out = list(head); after_sermon = False
    for it in items:
        c = canon(it.get("t", ""))
        if not c: continue
        if c == "찬양과경배" and norm(it.get("t", "")) in ("찬양", "찬송") and after_sermon: c = "찬양과결단"   # 설교 뒤 「찬양」 = 결단 찬양(곡도 그 아래)
        if c == "설교": after_sermon = True
        if pool.get(c):
            got = segs[pool[c].pop(0)][1]
        elif any(cc == c for cc, _ in segs):          # 같은 순서를 한 번 더(셋째 찬양과 경배 등) — 표지만 하나 더
            got = [copy.deepcopy(next(g for cc, g in segs if cc == c)[0])]
        elif base is not None:                        # 템플릿에 없는 순서(간증 등) — 같은 디자인 표지를 빌려 이름만
            got = [S.make_cover(base, title=it["t"].strip(), name=it.get("who", ""))]
        else:
            continue
        sec = {"t": it["t"].strip()}
        for f in ("who", "title", "ref"):
            v = it.get(f) or _from_info(c, info).get(f)
            if v: sec[f] = v
        got[0] = dict(got[0]); got[0]["_sec"] = sec
        out += got
    out += tail
    for n, s in enumerate(out, 1): s["n"] = n
    return out


# PPT 표지에서 어느 글자가 어느 칸인가 — ppt_tpl.set_main/set_small 과 같은 자리
FIELD_AT = {"성경봉독": {"ref": "main", "who": "small"}, "설교": {"title": "main", "who": "small"},
            "대표기도": {"who": "main"}, "봉헌": {"who": "main"}, "특송": {"who": "main"}}
_NO_FIELDS = {"찬양과경배", "찬양과결단", "사도신경", "교회소식", "축도", "성경암송"}


def smap_of(slides: list[dict]) -> list[dict]:
    """PPT 장 ↔ 예배순서 칸 짝(2026-10-07 교장님: PPT 에서 이름을 고치면 예배순서도, 예배순서에서 고치면 PPT 도).
    [{i: 장 번호(0부터), key: 순서 열쇠(canon), nth: 같은 순서 몇 번째, f: {who|title|ref: 글자 번호}, orig: 만든 글자(줄바꿈으로 이음), texts: 만든 글자들}]"""
    out, seen = [], {}
    for i, s in enumerate(slides):
        sec = s.get("_sec")
        if not sec: continue
        c = canon(sec["t"]); n = seen.get(c, 0); seen[c] = n + 1
        tx = s.get("texts", [])
        main = next((j for j, t in enumerate(tx) if 40 <= t.get("s", 0) < 100 and t.get("c") != "#efe6dd"), None)
        small = next((j for j, t in enumerate(tx) if 20 <= t.get("s", 0) < 40 and t.get("y", 0) > 520), None)
        spec = FIELD_AT.get(c) or ({} if c in _NO_FIELDS else {"who": "main"})   # 새로 넣은 순서(간증 등)는 가운데 글자가 맡은 분
        f = {k: (main if w == "main" else small) for k, w in spec.items()}
        f = {k: j for k, j in f.items() if j is not None}
        if f:
            texts = [str(t.get("t", "")) for t in tx]
            out.append({"i": i, "key": c, "nth": n, "f": f, "orig": "\n".join(texts), "texts": texts})
    return out


def save_smap(date: str, smap: list[dict]) -> None:
    try:
        ensure()
        _db([("UPDATE wor_order SET smap=? WHERE church=? AND date=?", [json.dumps(smap, ensure_ascii=False), CHURCH, date])])
    except Exception as e:
        print("PPT 짝 못 적음:", e, file=sys.stderr)


def sections(slides: list[dict]) -> list[dict]:
    """PPT 에 실제로 들어간 순서(표지에 단 _sec) — 예배순서에 다시 적을 목록."""
    return [dict(s["_sec"]) for s in slides if s.get("_sec")]


# ── DB ───────────────────────────────────────────────────────────────────
def _db(stmts):
    import wadmin
    return wadmin.batch(stmts)


_ALTERS = ["ALTER TABLE wor_order ADD COLUMN rev INTEGER DEFAULT 0", "ALTER TABLE wor_order ADD COLUMN built_rev INTEGER DEFAULT 0",
           "ALTER TABLE wor_order ADD COLUMN src TEXT", "ALTER TABLE wor_order ADD COLUMN jubo_done TEXT",
           "ALTER TABLE wor_order ADD COLUMN reco_req TEXT",
           "ALTER TABLE wor_order ADD COLUMN smap TEXT"]   # smap: PPT 장 ↔ 예배순서 칸 짝(PPT 에서 이름을 고치면 예배순서도, 거꾸로도)   # reco_req: [추천곡에 반영]을 누른 때(맥미니가 만들면 비운다)


def ensure() -> None:
    _db([("CREATE TABLE IF NOT EXISTS wor_order (church TEXT, date TEXT, items TEXT, confirmed INTEGER DEFAULT 0, jubo TEXT, by TEXT, updated TEXT, PRIMARY KEY (church, date))", [])])
    for a in _ALTERS:
        try: _db([(a, [])])
        except RuntimeError: pass                      # 이미 있는 칸


def load(date: str) -> dict | None:
    try:
        ensure()
        r = _db([("SELECT items,src,updated,rev,built_rev,confirmed FROM wor_order WHERE church=? AND date=?", [CHURCH, date])])[0]
        return r[0] if r else None
    except Exception as e:                              # 예배 DB 가 안 닿아도 PPT 는 템플릿대로 만든다
        print("예배순서 못 읽음:", e, file=sys.stderr)
        return None


def write_back(date: str, secs: list[dict], row: dict | None) -> str:
    """PPT 에 들어간 순서를 예배순서에 적는다. 그 사이 누가 고쳤으면(updated 가 바뀜) 건드리지 않는다."""
    if not secs: return "순서 없음"
    now = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    js = json.dumps(secs, ensure_ascii=False)
    try:
        if row is None:
            _db([("INSERT INTO wor_order(church,date,items,confirmed,src,rev,built_rev,updated) VALUES(?,?,?,0,'ppt',0,0,?) ON CONFLICT(church,date) DO NOTHING",
                  [CHURCH, date, js, now])])
            return "예배순서 새로 적음"
        if json.loads(row.get("items") or "[]") == secs: return "예배순서와 같음"
        _db([("UPDATE wor_order SET items=?, updated=? WHERE church=? AND date=? AND updated IS ?", [js, now, CHURCH, date, row.get("updated")])])
        got = _db([("SELECT updated FROM wor_order WHERE church=? AND date=?", [CHURCH, date])])[0]
        return "예배순서에 PPT 순서 적음" if got and got[0]["updated"] == now else "그 사이 예배순서를 고쳐서 적지 않음(고친 순서 그대로)"
    except Exception as e:
        return f"예배순서 적기 실패: {e}"


def _log(lines: list[str]) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as fp:
        fp.write(f"[{dt.datetime.now():%m-%d %H:%M}]\n" + "\n".join("  " + x for x in lines) + "\n")


def take_jubo(row: dict, dry: bool = False) -> list[str]:
    """올라온 주보 파일을 받아 PPT 용 자리에 두고, 읽어서 순서를 채운다."""
    date = row["date"]; j = json.loads(row["jubo"])
    ext = (re.search(r"\.(\w+)$", urllib.parse.urlparse(j["url"]).path) or [None, ""])[1].lower()
    if dry: return [f"{date} 주보 {j.get('name')} 받을 차례"]
    now = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if ext not in ("hwp", "hwpx", "pdf"):              # 사진 주보는 읽지 못한다 — 첨부만
        _db([("UPDATE wor_order SET jubo_done=? WHERE church=? AND date=?", ["image", CHURCH, date])])
        return [f"{date} 주보가 사진이라 순서는 채우지 않음"]
    data = urllib.request.urlopen(j["url"], timeout=60).read()
    J = HERE / "jubo"; J.mkdir(exist_ok=True); (J / "prev").mkdir(exist_ok=True)
    for x in ("hwp", "hwpx", "pdf"):                    # 새 주보가 먼저 읽히게 — 같은 날 예전 파일은 prev/ 로 옮긴다(지우지 않음)
        old = J / f"{date}.{x}"
        if old.exists(): old.rename(J / "prev" / f"{date}.{x}.{dt.datetime.now():%H%M%S}")
    (J / f"{date}.{ext}").write_bytes(data)
    import jubo_form, jubo_rules
    md, _ = jubo_form.kordoc(data)
    if len(jubo_rules.nospace(re.sub(r"<[^>]+>", "", md))) < 40:          # 글자가 없는 PDF(스캔한 그림) — 첨부만
        _db([("UPDATE wor_order SET jubo_done=? WHERE church=? AND date=?", ["image", CHURCH, date])])
        return [f"{date} 주보 PDF 에 글자가 없어(스캔) 순서는 채우지 않음"]
    got, how = jubo_rules.read(md)                                        # 순서표 찾기·칸 가르기·이름 맞추기·원문 대조
    got = fill_word(got, word(md, jubo_form.parse(md)))
    cur = json.loads(row["items"] or "[]") or [dict(x) for x in DEFAULT_SUN]
    merged = merge_jubo(cur, got) if got else cur
    sunday = True   # 예배마다 PPT 를 만든다(새벽·수요·금요·새로 만든 예배도, 2026-10-07)
    _db([("UPDATE wor_order SET items=?, jubo_done=?, src=CASE WHEN src='user' THEN 'user' ELSE 'jubo' END, rev=COALESCE(rev,0)+?, updated=? "
          "WHERE church=? AND date=? AND updated IS ?", [json.dumps(merged, ensure_ascii=False), now, 1 if sunday else 0, now, CHURCH, date, row["updated"]])])
    return [f"{date} 주보 {j.get('name')} → 순서 {len(got)}줄 읽음({how['by']}), 예배순서 {len(merged)}줄" + (" · PPT 다시 만들 차례" if sunday else "")]


def build(row: dict, dry: bool = False) -> list[str]:
    date, rev = row["date"], int(row["rev"] or 0)
    if dry: return [f"{date} 순서 rev {rev} > {row['built_rev']} — PPT 다시 만들 차례"]
    out = []
    try:                                              # 순서를 확정하면 본문·제목으로 말씀에 맞는 곡과 예배 방향 글(새벽·수요·금요·주일 모두)
        import reco_gen
        cur = load(date)
        out.append(reco_gen.ensure_for(date, json.loads(cur["items"]) if cur and cur.get("items") else []))
    except Exception as e:
        out.append(f"{date} 추천 실패: {e}")
    if True:                                          # 예배마다 PPT(새벽·수요·금요·새로 만든 예배도, 2026-10-07)
        r = subprocess.run([PY, str(HERE / "build.py"), date, "--share"], capture_output=True, text=True, timeout=1800)
        out.append(f"{date} build {'ok' if r.returncode == 0 else '실패: ' + (r.stderr or r.stdout)[-300:]}")
        if r.returncode == 0:                          # 사이트에 다 올라간 뒤에 「PPT에 반영했습니다」
            import publish
            publish.wait_live(date)
    _db([("UPDATE wor_order SET built_rev=? WHERE church=? AND date=? AND COALESCE(built_rev,0)<?", [rev, CHURCH, date, rev])])
    return out


def sync(dry: bool = False) -> None:
    ensure()
    lines = []
    for row in _db([("SELECT date,jubo,items,updated FROM wor_order WHERE church=? AND jubo IS NOT NULL AND jubo<>'' AND (jubo_done IS NULL OR jubo_done='')", [CHURCH])])[0]:
        try: lines += take_jubo(row, dry)
        except Exception as e: lines.append(f"{row['date']} 주보 읽기 실패: {e}")
    try:   # 예배준비 [초기화] — 악보집·PPT 를 사이트에서 내리고(옮겨 두고) 첫 화면을 다시(2026-10-07 교장님)
        resets = _db([("SELECT date,at FROM wor_reset WHERE church=?", [CHURCH])])[0]
    except Exception:
        resets = []
    for row in resets:
        if dry: lines.append(f"{row['date']} 초기화 차례"); continue
        try:
            import publish
            done = publish.unpublish(row["date"])
            publish.index_page()
            r = subprocess.run([str(Path.home() / ".local/node/bin/vercel"), "deploy", "--prod", "--yes"], cwd=str(publish.SITE),
                               capture_output=True, text=True, timeout=900)
            lines.append(f"{row['date']} 초기화: " + (" · ".join(done) or "내릴 것 없음") + (" · 사이트 반영" if r.returncode == 0 else " · 사이트 반영 실패"))
        except Exception as e:
            lines.append(f"{row['date']} 초기화 실패: {e}")
        _db([("DELETE FROM wor_reset WHERE church=? AND date=? AND at=?", [CHURCH, row["date"], row["at"]])])
    for row in _db([("SELECT date,items,reco_req FROM wor_order WHERE church=? AND reco_req IS NOT NULL AND reco_req<>''", [CHURCH])])[0]:
        if dry: lines.append(f"{row['date']} 추천곡에 반영 차례"); continue
        try:                                          # [추천곡에 반영] — 본문·제목·주보 설교 요약으로 다시(2026-10-07 교장님)
            import reco_gen
            lines.append(reco_gen.ensure_for(row["date"], json.loads(row["items"] or "[]"), force=True))
        except Exception as e:
            lines.append(f"{row['date']} 추천 실패: {e}")
        _db([("UPDATE wor_order SET reco_req=NULL WHERE church=? AND date=? AND reco_req=?", [CHURCH, row["date"], row["reco_req"]])])
    for row in _db([("SELECT date,rev,built_rev FROM wor_order WHERE church=? AND COALESCE(rev,0) > COALESCE(built_rev,0)", [CHURCH])])[0]:
        try: lines += build(row, dry)
        except Exception as e: lines.append(f"{row['date']} PPT 다시 만들기 실패: {e}")
    if lines:
        print("\n".join(lines))
        if not dry: _log(lines)


if __name__ == "__main__":
    sync("--dry-run" in sys.argv)
