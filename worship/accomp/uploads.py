#!/usr/bin/env python3
"""악보와 PPT 「➕ 올리기」 처리 (2026-10-03 교장님: 악보만 올리면 제목·코드를 읽고 자막까지 넣어 데이터로 등록).

  편집본(song-edit.html)에서 올린 파일 → 그림 창고 + uploads 줄(status wait) → 맥미니(conti_sync 가 1분마다 부름)가 처리:
    · 악보 그림·PDF : 글자 읽기(맥 Vision) → 악보를 줄(오선 + 가사) 단위로 나눔 → Claude 가 제목·코드·가사를 바로잡고
                      러시아어·영어 자막을 만듦 → 악보 DB(scores, 종류 '올림') + 곡별 PPT(두 줄씩 한 장, 「자막검수필요」)
                      이미 있는 곡이면 PPT 는 그대로 두고 악보만 더한다.
    · 곡 PPT(.pptx) : 예배 PPT 훑기와 같은 방법으로 곡을 나눠 등록. 자막이 없는 곡은 가사를 읽어 번역해 넣는다(「자막검수필요」).
    · 제목을 못 읽으면 status 'check' — 화면에서 제목을 넣고 「다시 처리」.

  python3 accomp/uploads.py            # 기다리는 것 처리
  python3 accomp/uploads.py --id 3     # 하나만(상태와 관계없이)
"""
from __future__ import annotations

import base64, datetime as dt, io, json, os, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import store as S  # noqa: E402

CLAUDE = str(Path.home() / ".local/bin/claude")
SW, SH, BAND = 1920, 1080, 0.20


# ── 공통 ───────────────────────────────────────────────────────
def claude_json(prompt: str, timeout: int = 600) -> dict:
    """claude -p (구독) → 답 속 JSON. ANTHROPIC_* 키는 넘기지 않는다(넘기면 API 과금 — 2026-09-11 사고)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) and k != "CLAUDE_CODE_OAUTH_TOKEN"}
    r = subprocess.run([CLAUDE, "-p", prompt, "--output-format", "text"], capture_output=True, text=True, timeout=timeout,
                       env=env, cwd=tempfile.gettempdir())
    t = r.stdout
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < a: raise RuntimeError(f"Claude 답에 JSON 없음: {(t or r.stderr)[:200]}")
    return json.loads(t[a:b + 1])


def ocr_images(ims) -> list[list[dict]]:
    import songbank as B
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, im in enumerate(ims):
            p = f"{tmp}/{i:03d}.png"; im.save(p); paths.append(p)
        got = B.ocr(paths)
        return [got.get(p, []) for p in paths]


def rows_of(lines: list[dict], H: int, y0: float = 0, y1: float = 1e9, korean: bool = True) -> list[str]:
    """글자 조각 → 같은 높이끼리 한 줄(왼쪽부터). y 는 0~1 비율, y0·y1 은 픽셀."""
    ls = [x for x in lines if y0 <= x["y"] * H < y1 and (not korean or re.search(r"[가-힣]", x["t"]))]
    ls.sort(key=lambda x: (x["y"], x["x"]))
    rows: list[list[dict]] = []
    for x in ls:
        if rows and abs(rows[-1][0]["y"] - x["y"]) < max(x["h"], 0.006) * 0.6: rows[-1].append(x)
        else: rows.append([x])
    return [" ".join(z["t"] for z in sorted(r, key=lambda z: z["x"])) for r in rows]


# ── 악보 나누기 ─────────────────────────────────────────────────
def staves(im) -> list[tuple[int, int, int, int]]:
    """오선 찾기 → [(위, 아래, 왼쪽, 오른쪽)] 픽셀. 한 줄로 길게 이어진 검은 가로줄 4~6개가 같은 간격으로 모인 것.
    (휴대폰 화면 캡처처럼 악보가 좁게 들어 있어도 되게 — 줄 길이는 그림 폭의 18% 넘으면 본다)"""
    import numpy as np
    g = np.asarray(im.convert("L"), dtype=np.uint8); H, W = g.shape
    dark = g < 215                                         # 캡처 악보는 오선이 옅은 회색
    cand = np.where(dark.mean(axis=1) > 0.15)[0]
    runs = {}
    for y in cand:                                         # 줄마다 가장 긴 검은 구간
        d = np.diff(np.concatenate(([0], dark[y].view(np.int8), [0])))
        st, en = np.where(d == 1)[0], np.where(d == -1)[0]
        k = int(np.argmax(en - st)); L = en[k] - st[k]
        if 0.18 * W < L < 0.995 * W: runs[int(y)] = (int(st[k]), int(en[k]))
    lines = []
    for y in sorted(runs):
        if lines and y - lines[-1][1] <= 2: lines[-1][1] = y; lines[-1][2].append(runs[y])
        else: lines.append([y, y, [runs[y]]])
    lines = [l for l in lines if l[1] - l[0] <= max(3, H * 0.004)]          # 굵은 테두리·막대는 오선이 아님
    if len(lines) < 4: return []
    mids = [(l[0] + l[1]) / 2 for l in lines]
    gaps = [b - a for a, b in zip(mids, mids[1:])]
    sp = float(np.median([x for x in gaps if x < H * 0.03] or [H * 0.01]))
    out, cur = [], [0]
    def close(c):
        if 4 <= len(c) <= 6:
            xs = [r for i in c for r in lines[i][2]]
            out.append((int(mids[c[0]]), int(mids[c[-1]]), min(r[0] for r in xs), max(r[1] for r in xs)))
    for i in range(1, len(lines)):
        if mids[i] - mids[i - 1] <= 1.6 * sp: cur.append(i)
        else: close(cur); cur = [i]
    close(cur)
    return out


def systems(im, lines: list[dict]) -> tuple[int, list[tuple[int, int]]]:
    """→ (머리글 끝, [(줄 위, 줄 아래)]). 줄 = 오선 + 그 아래 가사. 가사가 없는 오선(찬송가 낮은음자리표)은 앞 줄에 붙인다."""
    H = im.height
    st = staves(im)
    if not st: return 0, []
    kor = [x for x in lines if re.search(r"[가-힣]", x["t"])]
    def lyr_bottom(a, b):
        ys = [(x["y"] + x["h"]) * H for x in kor if a < x["y"] * H < b]
        return max(ys) if ys else None
    sh = st[0][1] - st[0][0]
    head = max(0, int(st[0][0] - 1.4 * sh))
    bands = []
    for i, (a, b, *_x) in enumerate(st):
        nxt = st[i + 1][0] if i + 1 < len(st) else H
        lb = lyr_bottom(b, nxt)
        if lb is None and bands:                              # 가사 없는 오선(찬송가 낮은음자리표) → 앞 줄에
            bands[-1][1] = min(nxt, b + int(0.6 * sh)); continue
        bands.append([a, int(lb + 0.15 * (nxt - lb)) if lb is not None else min(nxt, b + int(1.2 * sh))])
    out, top = [], head
    for a, b in bands:
        out.append((top, b)); top = b
    return head, out


def jpg(im) -> bytes:
    bio = io.BytesIO(); im.convert("RGB").save(bio, "JPEG", quality=90); return bio.getvalue()


def slide_of(crop, sub_lines: list[str]) -> dict:
    """악보 조각 → 곡 장(1920×1080, 아래 20% 는 자막 띠)."""
    aw, ah = SW, SH * (1 - BAND) - 10
    k = min(aw / crop.width, ah / crop.height)
    w, h = round(crop.width * k), round(crop.height * k)
    return {"img": base64.b64encode(jpg(crop)).decode(), "pic": [round((SW - w) / 2), round((ah - h) / 2) + 5, w, h],
            "sub": {"lines": [{"t": t} for t in sub_lines]} if sub_lines else None, "chips": [], "auto_sub": True}


PROMPT_SCORE = """다음은 한국 교회 찬양 악보를 맥 Vision 으로 읽은 글자입니다(틀린 글자가 섞여 있음).
머리글(제목 근처 글자): {head}
악보 위 코드 글자(앞에서부터): {chords}  ← 코드 표기가 머리글에 없으면 첫 코드·마지막 코드로 곡의 코드(조)를 정하세요
악보 줄마다 읽힌 가사(줄 = 오선 한 줄, 여러 절이면 여러 줄):
{body}
올린 사람이 적은 제목: {title} / 코드: {key} (비어 있으면 없음) / 파일 이름: {name}

할 일:
1) 곡 제목(한국어, 찬송가면 장 번호 없이 곡명)과 코드(G, A, Bb, F#m 처럼; 모르면 null)를 정하세요. 제목을 확신할 수 없으면 title 을 null 로.
2) 장마다 가사를 바로잡고(OCR 오류만 고침, 내용을 지어내지 말 것) 그 가사의 러시아어·영어 번역을 만드세요(예배 자막용, 뜻을 살린 자연스러운 문장).
   여러 절이면 절마다 번역하되 한 장의 ru·en 은 각각 3줄 안으로.
JSON 만 답하세요: {{"title": "...", "key": "G", "first_line": "첫 가사", "slides": [{{"ko": ["..."], "ru": ["..."], "en": ["..."]}}, ...]}}
slides 는 아래 장 순서·개수({n}장) 그대로."""


def do_score(row: dict, data: bytes) -> dict:
    from PIL import Image
    name = row["name"] or "악보"
    if data[:4] == b"%PDF":
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        pages = [Image.open(io.BytesIO(p.get_pixmap(dpi=170).tobytes("png"))).convert("RGB") for p in doc]
    else:
        im = Image.open(io.BytesIO(data))
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, "white"); im = im.convert("RGBA"); bg.paste(im, mask=im.split()[-1]); im = bg
        pages = [im.convert("RGB")]
    ocrs = ocr_images(pages)
    head_txt, groups = [], []                  # groups: (쪽, 위, 아래, 가사 줄들)
    for pi, (im, ls) in enumerate(zip(pages, ocrs)):
        head, bands = systems(im, ls)
        st = staves(im)
        if st:                                         # 악보 바깥(휴대폰 화면 테두리 등)은 잘라 낸다
            m = int(0.03 * im.width); x0 = max(0, min(t[2] for t in st) - m); x1 = min(im.width, max(t[3] for t in st) + m)
            if x1 - x0 < im.width * 0.9: im = pages[pi] = im.crop((x0, 0, x1, im.height))   # 글자 위치는 높이만 쓰므로 그대로
        if pi == 0:
            head_txt = rows_of(ls, im.height, 0, head or im.height * 0.18, korean=False)[:8]
        if not bands: bands = [(head, im.height)]
        for i in range(0, len(bands), 2):           # 두 줄씩 한 장
            a, b = bands[i][0], bands[min(i + 1, len(bands) - 1)][1]
            groups.append((pi, a, b, rows_of(ls, im.height, a, b)))
    body = "\n".join(f"[{k + 1}장] " + " / ".join(g[3]) for k, g in enumerate(groups))
    CH = re.compile(r"^[A-G][#b]?(m|maj7?|7|sus[24]?|add9|dim|aug|M7|m7|6|9)?(/[A-G][#b]?)?$")
    chords = [x["t"] for ls in ocrs for x in sorted(ls, key=lambda z: (z["y"], z["x"])) if CH.match(x["t"].strip())][:24]
    ans = claude_json(PROMPT_SCORE.format(chords=", ".join(chords) or "(없음)", head=" | ".join(head_txt), body=body, n=len(groups),
                                          title=row.get("title") or "", key=row.get("music_key") or "", name=name))
    import migrate
    nt, nk, _ = migrate.parse_score_name(Path(name).stem)    # 「주님여 이 손을 G.png」 같은 파일 이름도 단서로
    title = (row.get("title") or ans.get("title") or "").strip()
    key = (row.get("music_key") or ans.get("key") or nk or None)
    if not title:
        return {"status": "check", "note": "제목을 읽지 못했습니다 — 제목을 넣고 「다시 처리」를 눌러 주세요",
                "result": {"guess": head_txt[:3]}}
    # 악보 DB
    have = S.put_assets([(jpg(p), "jpg") for p in pages])
    for n, p in enumerate(pages, 1):
        h = S.digest(jpg(p))
        S.sql("""INSERT INTO scores(title,key,kind,source,ref,asset,page) VALUES(?,?,?,?,?,?,?)
                 ON CONFLICT(ref) DO UPDATE SET title=excluded.title, key=excluded.key""",
              title, key, "올림", f"올림: {name}", f"upload:{h}", h, n)
    res = {"title": title, "key": key, "pages": len(pages), "score": True}
    # 곡별 PPT — 이미 있는 곡이면 그대로
    exists = S.song_find(title, cut=0.9)
    if exists:
        res["ppt"] = f"이미 있는 곡 「{exists}」 — PPT 는 그대로"
        return {"status": "done", "note": f"악보 {len(pages)}쪽 등록 · {res['ppt']}", "result": res}
    sl = ans.get("slides") or []
    slides = []
    for k, (pi, a, b, _) in enumerate(groups):
        tr = sl[k] if k < len(sl) else {}
        slides.append(slide_of(pages[pi].crop((0, a, pages[pi].width, b)), (tr.get("ru") or [])[:3] + (tr.get("en") or [])[:3]))
    import migrate
    migrate.push_song({"title": title, "slides": slides, "date": dt.date.today().isoformat(), "kind": "올림", "file": name},
                      {"aliases": [], "uses": [{"date": dt.date.today().isoformat(), "kind": "올림", "file": name,
                                                "slides": [1, len(slides)], "header": title, "first": ans.get("first_line") or ""}],
                       "latest": {"langs": ["ru", "en"]}})
    res["ppt"] = f"곡별 PPT {len(slides)}장(자막검수필요)"
    return {"status": "done", "note": f"악보 {len(pages)}쪽 · {res['ppt']}", "result": res}


PROMPT_SUB = """다음은 한국 교회 찬양 PPT 의 장마다 악보 그림에서 읽은 가사입니다(틀린 글자 섞임). 곡: {title}
{body}
장마다 가사를 바로잡고(지어내지 말 것) 러시아어·영어 예배 자막(각 3줄 안)을 만드세요.
JSON 만: {{"slides": [{{"ru": ["..."], "en": ["..."]}}, ...]}} — {n}장 순서 그대로. 가사가 없는 장은 빈 목록."""


def do_pptx(row: dict, data: bytes) -> dict:
    from PIL import Image
    import songbank as B, songppt as P, migrate
    with tempfile.TemporaryDirectory() as tmp:
        px = Path(tmp) / "up.pptx"; px.write_bytes(data)
        D, _ = B.build_dictionary()
        if row.get("title"): D.add(*B.clean_title(row["title"]), prio=0)
        slides, groups = B.analyze(px, D, [row["title"]] if row.get("title") else None)
    if not groups and row.get("title"):                    # 머리글을 못 읽어도 제목을 받았으면 곡 장 전체를 한 곡으로
        ns = [s["n"] for s in slides if s["song"]]
        if ns: groups = [{"title": row["title"], "a": ns[0], "b": ns[-1], "header": "", "score": 1.0, "hymn": None}]
    if not groups:
        return {"status": "check", "note": "곡 장을 찾지 못했거나 제목을 읽지 못했습니다 — 제목을 넣고 「다시 처리」", "result": None}
    done, unsure = [], []
    for gr in groups:
        song = P.song_record(gr["title"], slides, gr["a"], gr["b"], f"올림: {row['name']} {gr['a']}~{gr['b']}장")
        if not any(s.get("sub") for s in song["slides"]):     # 자막 없는 곡 → 가사 읽어 번역
            ims = [Image.open(io.BytesIO(base64.b64decode(s["img"]))).convert("RGB") for s in song["slides"]]
            body = "\n".join(f"[{k + 1}장] " + " / ".join(rows_of(ls, im.height)) for k, (im, ls) in enumerate(zip(ims, ocr_images(ims))))
            ans = claude_json(PROMPT_SUB.format(title=gr["title"], body=body, n=len(ims)))
            for s, tr in zip(song["slides"], ans.get("slides") or []):
                t = (tr.get("ru") or [])[:3] + (tr.get("en") or [])[:3]
                if t: s["sub"] = {"lines": [{"t": x} for x in t]}; s["auto_sub"] = True
        song.update({"date": dt.date.today().isoformat(), "kind": "올림", "file": row["name"], "hymn": gr.get("hymn"),
                     "check": gr.get("score", 1) < 0.8})
        migrate.push_song(song, {"aliases": D.aliases(gr["title"]), "uses": [{"date": song["date"], "kind": "올림", "file": row["name"],
                                 "slides": [gr["a"], gr["b"]], "header": gr.get("header", ""), "first": gr.get("first", "")}],
                                 "latest": {"langs": B.langs(song)}})
        done.append(gr["title"]); (unsure.append(gr["title"]) if song["check"] else None)
    note = f"곡 {len(done)}개 등록: " + " · ".join(done) + (f" (제목 확인 필요: {' · '.join(unsure)})" if unsure else "")
    return {"status": "check" if unsure and len(unsure) == len(done) else "done", "note": note, "result": {"songs": done, "unsure": unsure}}


def process(row: dict) -> dict:
    with urllib.request.urlopen(row["url"], timeout=300) as r: data = r.read()
    if data[:2] == b"PK": return do_pptx(row, data)
    return do_score(row, data)


def run(only: int | None = None) -> None:
    rows = S.sql("SELECT * FROM uploads WHERE id=?", only) if only else S.sql("SELECT * FROM uploads WHERE status='wait' ORDER BY id LIMIT 5")
    for row in rows:
        S.sql("UPDATE uploads SET status='work', updated=CURRENT_TIMESTAMP WHERE id=?", int(row["id"]))
        try:
            out = process(row)
        except Exception as ex:  # noqa: BLE001
            out = {"status": "fail", "note": f"처리 실패: {str(ex)[:200]}", "result": None}
        S.sql("UPDATE uploads SET status=?, note=?, result=?, updated=CURRENT_TIMESTAMP WHERE id=?",
              out["status"], out["note"], json.dumps(out.get("result"), ensure_ascii=False), int(row["id"]))
        print(f"[올리기 {row['id']}] {row['name']}: {out['status']} — {out['note']}", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    run(int(a[a.index("--id") + 1]) if "--id" in a else None)
