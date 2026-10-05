#!/usr/bin/env python3
"""곡별 PPT 모으기 — 예배 PPT 들을 훑어 곡마다 최신 판을 songppt/db 에 (2026-10-03 교장님 지시).

예배 PPT 의 곡 장은 그림(악보·가사) 왼쪽 위에 곡명 머리글(「♬ 내 삶은 주의 것」)이 찍혀 있다.
  · 머리글을 맥 글자 인식(tools/ocr, Vision)으로 읽어 곡 경계와 이름을 정하고
  · 찬송가처럼 첫 장에만 머리글이 있는 곡은 뒤따르는 장(오선·자막·절 단추가 있는 장)을 이어 붙이고
  · 이름은 곡명 사전(콘티 기록 · 악보 모음 파일명 · 새찬송가 645장 · 악보집)과 맞춘다.
같은 곡이 여러 번 나오면 가장 최근 날짜 판을 대표로 둔다(쓴 날은 모두 index.json 에 남는다).

  python3 accomp/songbank.py sources                 대상 PPT 목록 → songppt/sources.json
  python3 accomp/songbank.py scan [--limit N] [--only 2025-11-23,…] [--upload]
  python3 accomp/songbank.py find 곡명               DB 에서 곡 찾기
"""
from __future__ import annotations

import io, json, re, subprocess, sys, tempfile, unicodedata
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import songppt as P  # noqa: E402

ROOT = P.ROOT
SRC, SCAN = ROOT / "src", ROOT / "scan"
INDEX, SOURCES = ROOT / "index.json", ROOT / "sources.json"
OCR = HERE / "tools" / "ocr"
CONTI_DOC = "1nF0M6jVozi02m8alxC1pel-H7LWazpHPM-gcW_xLiqg"            # 콘티 기록 2026 2025 2024
YEAR_FOLDERS = {"2026": "1sRJ7X8heOaM5BmDa0WW6Jvs__O2upcpV", "2025": "1lOfY_jtKaBjYfVCvLqRgZv-aL7OX2RDK",
                "2024": "1IwsaTNOO1j4JgfMPd__k2UUIKmtnWgoi"}
ALL_PPT = "1mKYQaXuaioaZNyBUwMWeBSYV76dl535B"                         # 제곡교회 전체 PPT (2021~2023)
SCORES = "1GHYOq02R7nfpuEXl-uxMGyqi0K90dOV5"                           # 찬양 악보 모음
GSLIDES = "application/vnd.google-apps.presentation"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


# ── 글자 비교 ───────────────────────────────────────────────────
def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", nfc(s).lower())


def jamo(s: str) -> str:
    """한글 음절을 자모로 풀어 비교한다(「총만」↔「충만」처럼 한 획 틀린 인식을 가깝게 본다)."""
    out = []
    for ch in s:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out += [chr(0x1100 + c // 588), chr(0x1161 + c % 588 // 28)] + ([chr(0x11A7 + c % 28)] if c % 28 else [])
        else:
            out.append(ch)
    return "".join(out)


def sim(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b: return 0.0
    if a == b: return 1.0
    s, l = sorted((a, b), key=len)
    if len(s) >= 4 and l.startswith(s): return 0.93
    if len(s) >= 5 and s in l: return 0.88
    return SequenceMatcher(None, jamo(a), jamo(b)).ratio()


KEY_RE = r"(?:[A-G][b#♭♯]?m?(?:\s*[→\-/]\s*[A-G][b#♭♯]?m?)*)"


def clean_title(t: str) -> tuple[str, list[str]]:
    """「무명이어도 G (충만)」 → ("무명이어도", ["충만"]). 조(코드)·찬송가 표시·괄호를 뗀다."""
    t = nfc(t).strip().lstrip("*•").strip()
    alias = [a.strip() for a in re.findall(r"\(([^)]*)\)", t)]
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(rf"\s+{KEY_RE}\s*$", "", t.strip())
    t = re.sub(rf"\s+{KEY_RE}(\s|$)", " ", t)
    alias = [a for a in alias if a and not re.match(r"^(찬송가|통|\d|와이드|wide|피아|아아|4:4)", a, re.I) and not re.fullmatch(KEY_RE, a)]
    return re.sub(r"\s+", " ", t).strip(" .-_"), alias


# ── 곡명 사전 ───────────────────────────────────────────────────
class Dictionary:
    """곡명 후보 모음. 이름표(display)는 교장님 콘티 기록 → 악보집 → 악보 파일명 → 새찬송가 순으로 고른다."""

    def __init__(self):
        self.items: list[tuple[str, list[str], int]] = []   # (이름표, 비교할 이름들, 우선순위 낮을수록 먼저)
        self.hymns: dict[int, str] = {}

    def add(self, title: str, aliases=(), prio: int = 5):
        title = title.strip()
        if len(norm(title)) >= 2:
            self.items.append((title, [title, *aliases], prio))

    def aliases(self, title: str) -> list[str]:
        return sorted({a for disp, names, _ in self.items if disp == title for a in names if a != title})

    def match(self, text: str, cut: float = 0.8) -> tuple[str | None, float]:
        best, bs, bp = None, 0.0, 9
        for disp, names, prio in self.items:
            s = max(sim(text, n) for n in names)
            if s > bs + 1e-9 or (abs(s - bs) < 1e-9 and prio < bp):
                best, bs, bp = disp, s, prio
        return (best, bs) if bs >= cut else (None, bs)


def conti_weeks(text: str) -> dict[str, list[str]]:
    """콘티 기록 문서 → {"2025-11-23": [도입, 메인…, 적용]} (문서 순서 그대로)."""
    weeks, cur = {}, None
    for line in nfc(text).splitlines():
        m = re.match(r"^\s*(\d\d)\s?(\d\d)(\d\d)\s*$", line)
        if m:
            cur = f"20{m[1]}-{m[2]}-{m[3]}"; weeks.setdefault(cur, []); continue
        if cur and line.strip().startswith("*"):
            t = line.strip().lstrip("* ").strip()
            if norm(t): weeks[cur].append(t)
    return weeks


def build_dictionary(g=None, tree: dict | None = None) -> tuple[Dictionary, dict]:
    D = Dictionary()
    cache = ROOT / "conti_record.txt"
    if g is not None:
        import prep
        raw = g.req("GET", f"{prep.DRIVE}/files/{CONTI_DOC}/export?mimeType=text/plain&supportsAllDrives=true")
        cache.write_text(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"), encoding="utf-8")
    weeks = conti_weeks(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    for songs in weeks.values():
        for t in songs:
            D.add(*clean_title(t), prio=1)
    for f in sorted((HERE / "data").glob("*.json")):
        try:
            d = json.loads(f.read_text()).get("songs", {})
            for grp in d.values():
                for x in grp:
                    if x.get("title"): D.add(*clean_title(x["title"]), prio=2)
        except Exception:
            pass
    try:
        for t in json.loads((HERE / "score_bank.json").read_text())["songs"]:
            D.add(*clean_title(t), prio=2)
    except Exception:
        pass
    for name in (tree or {}):
        t, al = clean_title(re.sub(r"\.(png|jpe?g|pdf)$", "", name, flags=re.I).replace("_", " "))
        t = re.sub(r"\s*-\s*\d+$", "", t)
        D.add(t, al, prio=3)
    hy = HERE / "hymns645.txt"
    if hy.exists():
        for line in hy.read_text(encoding="utf-8").splitlines()[1:]:
            no, title = (line.split(",") + [""])[:2]
            if no.isdigit():
                D.hymns[int(no)] = title.strip(); D.add(title.strip(), [f"{no}장 {title.strip()}"], prio=4)
    return D, weeks


# ── 머리글 읽기 ─────────────────────────────────────────────────
JUNK = re.compile(r"^(?:[^\w가-힣]+|[A-Za-z0-9]{1,2}|[가-힣])\s+")


def header_variants(raw: str) -> tuple[list[str], int | None]:
    """머리글 인식 글 → 이름 후보들 + 찬송가 장수. 앞의 아이콘이 글자로 읽힌 것(F·J·여·며·§…)을 떼어 본다."""
    t = nfc(raw).strip()
    t = re.sub(r"[-–]?\s*통\s*\d*\)?\s*$|\(통\s*\d+\)", "", t).strip(" -")
    hymn = None
    cands = [t]
    stripped = JUNK.sub("", t, count=1)
    if stripped != t: cands.append(stripped)
    out = []
    for c in cands:
        m = re.match(r"^(\d{1,3})\s*장\s*(.*)$", c)
        if m:
            hymn = int(m[1]); c = m[2]
        c = re.sub(r"^[^\w가-힣(]+", "", c).strip()
        if len(norm(c)) >= 2: out.append(c)
    return list(dict.fromkeys(out)), hymn


def flatten(im):
    from PIL import Image
    im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
    return bg.convert("RGB")


def has_staff(im) -> bool:
    """오선(가로줄 다섯 개가 고르게)이 있는 그림인가."""
    import numpy as np
    g = im.convert("L"); g = g.resize((max(1, int(g.width * 720 / g.height)), 720))
    rows = np.where((np.asarray(g) < 170).mean(1) > 0.18)[0]
    lines = []
    for y in rows:
        if lines and y - lines[-1][1] <= 1: lines[-1][1] = y
        else: lines.append([y, y])
    cs = [(a + b) / 2 for a, b in lines if b - a <= 4]
    for i in range(len(cs) - 4):
        gaps = np.diff(cs[i:i + 5])
        if gaps.max() < 30 and gaps.min() > 4 and gaps.max() / gaps.min() < 1.5:
            return True
    return False


def ocr(paths: list[str]) -> dict[str, list[dict]]:
    out = {}
    for i in range(0, len(paths), 200):
        r = subprocess.run([str(OCR), *paths[i:i + 200]], capture_output=True, text=True, timeout=1800)
        for line in r.stdout.splitlines():
            try:
                d = json.loads(line); out[d["file"]] = d["lines"]
            except Exception:
                pass
    return out


# ── 한 PPT 훑기 ─────────────────────────────────────────────────
def analyze(pptx: Path, D: Dictionary, week: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """→ (장 목록, 곡 구간 [{title, a, b, header, score, hymn}]). week = 그 주 콘티 곡(있으면 먼저 맞춘다)."""
    W = Dictionary()
    for t in week or []:
        W.add(*clean_title(t), prio=0)
    from PIL import Image
    slides = P.parse(pptx)
    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for s in slides:
            if not s["song"]: continue
            im = flatten(Image.open(io.BytesIO(s["blob"])))
            s["staff"] = has_staff(im)
            w, h = im.size
            c = im.crop((0, 0, int(w * .75), int(h * .2)))
            c = c.resize((1400, max(1, int(c.height * 1400 / c.width))))
            p = f"{tmp}/{s['n']:04d}.png"; c.save(p); paths[p] = s
        for p, lines in ocr(list(paths)).items():
            ls = [x for x in sorted(lines, key=lambda x: x["y"]) if x["y"] < 0.6 and re.search(r"[가-힣]{2}", x["t"])]
            paths[p]["header"] = ls[0]["t"] if ls else ""
    for s in slides:
        s.setdefault("header", ""); s.setdefault("staff", False)
        s["cand"], s["hymn"] = header_variants(s["header"]) if s["header"] else ([], None)
        s["dict"], s["dscore"] = None, 0.0
        for c in s["cand"]:
            t, sc = D.match(c, cut=0.0)
            if sc >= 0.86 and sc > s["dscore"]: s["dict"], s["dscore"] = t, sc   # 비슷하기만 한 다른 곡 이름은 붙이지 않는다
            t, sc = W.match(c, cut=0.6) if W.items else (None, 0)
            if t and s["dscore"] < 0.9 and max(sc, 0.8) >= s["dscore"]:   # 그 주 콘티 곡이면 인식이 조금 틀려도 그 이름
                s["dict"], s["dscore"] = t, max(sc, 0.8)

    def songish(s):          # 머리글 없이 이어지는 장도 곡 장으로 볼 만한가
        return s["song"] and not s["creed"] and (s["staff"] or s.get("sub") or s.get("chips"))

    groups, cur = [], None
    for s in slides:
        named = s["song"] and s["cand"] and (s["dscore"] >= 0.8 or s["staff"] or s.get("sub") or s.get("chips"))
        if named:
            key = s["dict"] if s["dscore"] >= 0.8 else s["cand"][-1]
            if cur and cur["b"] == s["n"] - 1 and (sim(key, cur["key"]) >= 0.8 or any(sim(c, h) >= 0.8 for c in s["cand"] for h in cur["heads"])):
                cur["b"] = s["n"]; cur["heads"] += s["cand"]
            else:
                cur = {"key": key, "a": s["n"], "b": s["n"], "heads": list(s["cand"]), "hymn": s["hymn"]}; groups.append(cur)
        elif cur and cur["b"] == s["n"] - 1 and not s["cand"] and songish(s):
            cur["b"] = s["n"]
        else:
            cur = None
    out = []
    for gr in groups:
        part = [s for s in slides if gr["a"] <= s["n"] <= gr["b"]]
        votes: dict[str, float] = {}
        for s in part:
            if s["dict"] and s["dscore"] >= 0.8: votes[s["dict"]] = votes.get(s["dict"], 0) + s["dscore"]
        if votes:
            title = max(votes, key=votes.get); score = max(s["dscore"] for s in part if s["dict"] == title)
        else:
            heads = [h for s in part for h in s["cand"][-1:]]
            title = max(set(heads), key=heads.count); score = 0.0
        if gr["hymn"] and D.hymns.get(gr["hymn"]) and sim(D.hymns[gr["hymn"]], title) >= 0.6:
            title = D.hymns[gr["hymn"]] if score < 0.8 else title; score = max(score, 0.8)
        if score < 0.8 and (len(part) < 2 or re.search(r"주차|\d+월\s*\d+일", title) or len(re.findall(r"[가-힣]", title)) < 2
                            or not any(s["staff"] or s.get("sub") for s in part)):
            continue                                   # 곡이라 볼 근거가 없다(성경암송·예배 순서 장 등)
        out.append({"title": title, "a": gr["a"], "b": gr["b"], "header": part[0]["header"], "score": round(score, 2), "hymn": gr["hymn"]})
    first_lines(slides, out)
    for x in out:                                    # 머리글로 못 정한 곡은 첫 가사로 사전과 다시 맞춘다
        if x["score"] < 0.86 and x.get("first"):
            t, sc = D.match(x["first"], cut=0.86)
            if t: x["title"], x["score"] = t, round(sc, 2)
    # 한 PPT 에 같은 곡이 두 번이면 긴 쪽만
    best: dict[str, dict] = {}
    for x in out:
        if x["title"] not in best or x["b"] - x["a"] > best[x["title"]]["b"] - best[x["title"]]["a"]:
            best[x["title"]] = x
    return slides, sorted(best.values(), key=lambda x: x["a"])


def first_lines(slides: list[dict], groups: list[dict]) -> None:
    """곡마다 첫 장의 첫 가사 줄(머리글 아래) — 악보집·콘티가 첫 가사로 곡을 부를 때 찾는 데 쓴다."""
    from PIL import Image
    by_n = {s["n"]: s for s in slides}
    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for gr in groups:
            im = flatten(Image.open(io.BytesIO(by_n[gr["a"]]["blob"])))
            im = im.resize((1400, max(1, int(im.height * 1400 / im.width))))
            p = f"{tmp}/{gr['a']:04d}.png"; im.save(p); paths[p] = gr
        for p, lines in ocr(list(paths)).items():
            ls = [re.sub(r"[-–—~]+", " ", x["t"]) for x in sorted(lines, key=lambda x: x["y"])
                  if 0.15 < x["y"] < 0.8 and len(re.findall(r"[가-힣]", x["t"])) >= 4]
            paths[p]["first"] = re.sub(r"\s+", " ", " ".join(ls[:2])).strip()


def langs(song: dict) -> list[str]:
    t = " ".join(ln["t"] for s in song["slides"] if s.get("sub") for ln in s["sub"]["lines"])
    return [l for l, rx in (("ru", r"[А-Яа-яЁё]"), ("en", r"[A-Za-z]{3}")) if re.search(rx, t)]


# ── 대상 목록 ───────────────────────────────────────────────────
def date_of(name: str, fallback: str) -> str | None:
    n = nfc(name)
    for rx, fmt in ((r"(20\d\d)[ _.,-]?(\d\d)[ _.,-]?(\d\d)", "{0}-{1}-{2}"), (r"(?<!\d)(\d\d),(\d\d),(\d\d)(?!\d)", "20{0}-{1}-{2}")):
        m = re.search(rx, n)
        if m and 1 <= int(m[2]) <= 12 and 1 <= int(m[3]) <= 31:
            return fmt.format(*m.groups())
    return fallback[:10] if fallback else None


def kind_of(name: str) -> str:
    n = nfc(name)
    for k in ("수요", "금요", "송구영신", "성탄", "부활", "창립", "임직"):
        if k in n: return k
    return "주일" if re.search(r"주일|제곡교회예배|주일예배", n) else "기타"


def is_service_ppt(name: str) -> bool:
    n = nfc(name)
    if n.startswith(("._", "~$")) or "0000" in n or re.search(r"반주자|싱어|_?wide|와이드|사본|자동 저장|목회자 세미나|기도제목|청춘사진관", n, re.I):
        return False
    return bool(re.search(r"예배|PPT", re.sub(r"\.pptx?$", "", n, flags=re.I), re.I))


def list_tree(g, fid: str, path: str = "") -> list[dict]:
    import prep, urllib.parse
    out, tok = [], ""
    while True:
        q = urllib.parse.quote(f"'{fid}' in parents and trashed=false")
        r = g.req("GET", f"{prep.DRIVE}/files?q={q}&fields=nextPageToken,files(id,name,mimeType,size,modifiedTime)&pageSize=1000"
                  f"&supportsAllDrives=true&includeItemsFromAllDrives=true" + (f"&pageToken={tok}" if tok else ""))
        for x in r["files"]:
            x["name"] = nfc(x["name"]); x["path"] = f"{path}/{x['name']}"
            if x["mimeType"] == prep.FOLDER_MIME: out += list_tree(g, x["id"], x["path"])
            else: out.append(x)
        tok = r.get("nextPageToken")
        if not tok: return out


def sources(g) -> list[dict]:
    """예배 PPT(주일·수요·금요·절기) 목록. 한 날짜·종류에 여럿이면 가장 늦게 고친 것 하나."""
    import datetime as dt
    today = dt.date.today().isoformat()
    files = []
    for yr, fid in YEAR_FOLDERS.items():
        files += [dict(x, root=yr) for x in list_tree(g, fid, yr)]
    files += [dict(x, root="전체PPT") for x in list_tree(g, ALL_PPT, "전체PPT") if not re.search(r"참고용|러시아어", x["path"])]
    pick: dict[tuple, dict] = {}
    for x in files:
        ext = x["name"].lower().rsplit(".", 1)[-1] if "." in x["name"] else ""
        if not (x["mimeType"] in (GSLIDES, PPTX) or ext == "pptx") or not is_service_ppt(x["name"]):
            continue
        d = date_of(x["name"], "") or date_of(x["path"], x.get("modifiedTime", ""))
        if d and d > today: continue                       # 아직 오지 않은 주일의 틀(곡이 없다)
        k = (d, kind_of(x["name"]) if kind_of(x["name"]) != "기타" else kind_of(x["path"]))
        if k not in pick or x["modifiedTime"] > pick[k]["modifiedTime"]:
            pick[k] = {"id": x["id"], "name": x["name"], "path": x["path"], "mimeType": x["mimeType"],
                       "modifiedTime": x["modifiedTime"], "date": d, "kind": k[1], "size": int(x.get("size") or 0)}
    return sorted(pick.values(), key=lambda x: (x["date"] or "", x["kind"]), reverse=True)


def fetch(g, src: dict) -> Path:
    import prep
    SRC.mkdir(parents=True, exist_ok=True)
    p = SRC / f"{src['id']}.pptx"
    if not p.exists():
        if src["mimeType"] == GSLIDES:
            b = g.req("GET", f"{prep.DRIVE}/files/{src['id']}/export?mimeType={prep.PPTX_MIME}", timeout=900)
        else:
            b = g.req("GET", f"{prep.DRIVE}/files/{src['id']}?alt=media&supportsAllDrives=true", timeout=900)
        p.write_bytes(b)
    return p


def fetch_parts(g, src: dict, parts: int) -> list[Path]:
    """구글 슬라이드가 「too large to be exported」 면 사본을 만들어 장을 나눠 pptx 로 내보낸다(사본은 지움, 2026-10-05)."""
    import prep
    SRC.mkdir(parents=True, exist_ok=True)
    pres = g.req("GET", f"{prep.SLIDES}/presentations/{src['id']}?fields=slides.objectId")
    ids = [x["objectId"] for x in pres["slides"]]; size = -(-len(ids) // parts); out = []
    for k, a in enumerate(range(0, len(ids), size), 1):
        c = g.req("POST", f"{prep.DRIVE}/files/{src['id']}/copy?supportsAllDrives=true&fields=id", {"name": f"_임시 나눔 {k}"})
        try:
            keep = set(ids[a:a + size])
            g.slides_batch(c["id"], [{"deleteObject": {"objectId": i}} for i in ids if i not in keep])
            b = g.req("GET", f"{prep.DRIVE}/files/{c['id']}/export?mimeType={prep.PPTX_MIME}", timeout=900)
        finally:
            g.req("DELETE", f"{prep.DRIVE}/files/{c['id']}?supportsAllDrives=true")
        q = SRC / f"{src['id']}~p{k}.pptx"; q.write_bytes(b); out.append(q)
    return out


def scan_split(g, src: dict, D, ix: dict, do_upload=False, weeks=None) -> list[str]:
    """너무 큰 슬라이드: 2·3·4·6 조각으로 나눠 조각마다 scan_one (조각 경계에 걸친 곡은 앞 조각 쪽이 잘릴 수 있다)."""
    for parts in (2, 3, 4, 6):
        try:
            files = fetch_parts(g, src, parts)
        except RuntimeError as ex:
            if "too large" in str(ex) or "exportSizeLimitExceeded" in str(ex): continue
            raise
        got = []
        for k, _ in enumerate(files, 1):
            got += scan_one(g, {**src, "id": f"{src['id']}~p{k}", "name": f"{src['name']} ({k}/{len(files)})"}, D, ix, do_upload, False, weeks)
        groups = []
        for k in range(1, len(files) + 1):
            q = SCAN / f"{src['id']}~p{k}.json"
            if q.exists(): groups += json.loads(q.read_text(encoding="utf-8")).get("groups", [])
        (SCAN / f"{src['id']}.json").write_text(json.dumps({"src": src, "split": len(files), "groups": groups, "heads": {}}, ensure_ascii=False), encoding="utf-8")
        return got
    raise RuntimeError("6조각으로 나눠도 구글 내보내기 크기 한도를 넘습니다")


# ── 모으기 ──────────────────────────────────────────────────────
def load_index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}


def save_index(ix: dict) -> None:
    INDEX.write_text(json.dumps(ix, ensure_ascii=False, indent=1), encoding="utf-8")


def scan_one(g, src: dict, D: Dictionary, ix: dict, do_upload: bool = False, keep: bool = False,
             weeks: dict | None = None) -> list[str]:
    SCAN.mkdir(parents=True, exist_ok=True)
    pptx = fetch(g, src)
    try:
        slides, groups = analyze(pptx, D, (weeks or {}).get(src["date"]) if src["kind"] == "주일" else None)
    finally:
        if not keep: pptx.unlink(missing_ok=True)
    label = f"{src['date']} {src['kind']}예배 PPT"
    (SCAN / f"{src['id']}.json").write_text(json.dumps({"src": src, "groups": groups,
        "heads": {s["n"]: s["header"] for s in slides if s["header"]}}, ensure_ascii=False, indent=1), encoding="utf-8")
    for t in list(ix):                                   # 이 파일로 전에 만든 기록은 지우고 다시 쓴다
        rec = ix[t]
        rec["uses"] = [u for u in rec["uses"] if u["id"] != src["id"]]
        if rec.get("latest") and rec["latest"]["id"] == src["id"]:
            rec["latest"] = None
        if not rec["uses"]:
            for f in (P.OUT / P.file_name(t), P.DB / P.file_name(t)[:-5] / "song.json"):
                f.unlink(missing_ok=True)
            del ix[t]
    done = []
    for gr in groups:
        t = gr["title"]
        rec = ix.setdefault(t, {"uses": [], "latest": None})
        use = {"date": src["date"], "kind": src["kind"], "file": src["name"], "id": src["id"], "slides": [gr["a"], gr["b"]],
               "header": gr["header"], "score": gr["score"], "first": gr.get("first", "")}
        rec["uses"] = [u for u in rec["uses"] if u["id"] != src["id"]] + [use]
        rec["uses"].sort(key=lambda u: u["date"] or "", reverse=True)
        if gr["hymn"]: rec["hymn"] = gr["hymn"]
        rec["aliases"] = sorted(set(rec.get("aliases", [])) | set(D.aliases(t)))
        newer = not rec["latest"] or (src["date"] or "") > (rec["latest"]["date"] or "") or rec["latest"]["id"] == src["id"]
        if newer:
            song = P.song_record(t, slides, gr["a"], gr["b"], f"{label} {gr['a']}~{gr['b']}장")
            song.update({"date": src["date"], "kind": src["kind"], "file": src["name"], "hymn": gr["hymn"], "check": gr["score"] < 0.8})
            o = P.write(song)
            rec["latest"] = {"date": src["date"], "id": src["id"], "n": len(song["slides"]), "langs": langs(song),
                             "file": o.name, "check": song["check"]}
            if do_upload:
                rec["drive"] = P.upload(o).get("webViewLink")
            done.append(t)
    return done


def scan(only: list[str] | None = None, limit: int | None = None, do_upload: bool = False, keep: bool = False, redo: bool = False) -> None:
    import prep
    g = prep.G(prep.access_token())
    if not SOURCES.exists():
        SOURCES.write_text(json.dumps(sources(g), ensure_ascii=False, indent=1), encoding="utf-8")
    srcs = json.loads(SOURCES.read_text(encoding="utf-8"))
    tree = json.loads((ROOT / "scores_tree.json").read_text()) if (ROOT / "scores_tree.json").exists() else {}
    D, weeks = build_dictionary(g, tree)
    ix = load_index()
    todo = [s for s in srcs if (not only or s["date"] in only or s["id"] in only)
            and (only or redo or not (SCAN / f"{s['id']}.json").exists())]
    for i, s in enumerate(todo[:limit] if limit else todo, 1):
        try:
            try:
                got = scan_one(g, s, D, ix, do_upload, keep, weeks)
            except RuntimeError as ex:
                if s["mimeType"] != GSLIDES or not ("too large" in str(ex) or "exportSizeLimitExceeded" in str(ex)): raise
                got = scan_split(g, s, D, ix, do_upload, weeks)
            save_index(ix)
            print(f"[{i}/{len(todo)}] {s['date']} {s['kind']} {s['name']}: {len(got)}곡 새로 — {', '.join(got)}", flush=True)
        except Exception as e:  # 한 파일이 깨져도 나머지는 계속
            print(f"[{i}/{len(todo)}] {s['date']} {s['name']}: 실패 {type(e).__name__}: {e}", flush=True)
            if "token" in str(e).lower() or "401" in str(e):
                g = prep.G(prep.access_token())


def find(title: str, ix: dict | None = None, cut: float = 0.8) -> str | None:
    """악보집 곡명(「우리는 기대하고」) → DB 곡명(「우리는 기대하고 기도하며 기다리네」)."""
    ix = ix if ix is not None else load_index()
    best, bs = None, 0.0
    for t, rec in ix.items():
        if not rec.get("latest"): continue
        names = ([t] + [h for u in rec["uses"][:3] for h in header_variants(u.get("header") or "")[0]] + rec.get("aliases", [])
                 + [u["first"] for u in rec["uses"][:3] if u.get("first")])
        s = max(sim(title, n) for n in names)
        if s > bs: best, bs = t, s
    return best if bs >= cut else None


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "help":
        print(__doc__); sys.exit(0)
    if a[0] == "sources":
        import prep
        s = sources(prep.G(prep.access_token()))
        SOURCES.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        print(len(s), "개", sum(x["size"] for x in s) // 10**6, "MB")
    elif a[0] == "scan":
        only = a[a.index("--only") + 1].split(",") if "--only" in a else None
        lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
        scan(only, lim, "--upload" in a, "--keep" in a, "--redo" in a)
    elif a[0] == "find":
        print(find(" ".join(a[1:])))
