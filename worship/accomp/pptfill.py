#!/usr/bin/env python3
"""주일예배 PPT 채우기 — 예배자 악보(data/<날짜>.json)와 PPT 를 잇는다 (2026-10-03 교장님 지시).

성경암송: 예배자 악보 암송 쪽의 「이번 주 외울 절」(굵게·분홍 음영, recite.json 이 정함)까지 PPT 암송 장을 맞춘다.
  · 그 장(章)의 암송 장이 모자라면 마지막 암송 장을 본떠 한 절에 한 장씩 더하고(개역개정 본문)
  · 넘치면 뒤의 장을 빼고
  · 장마다 제목의 절 번호를 본문과 대조해 바로잡는다(내용은 13절인데 제목이 15:12 로 남은 장 등).

  python3 accomp/pptfill.py 2026-10-04            worship_ppt/<날짜>.pptx 를 고친다
  python3 accomp/pptfill.py 2026-10-04 --upload   + 드라이브의 그 주 「주일예배 PPT」를 같은 파일로 갱신
"""
from __future__ import annotations

import copy, json, re, subprocess, sys
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
BIBLE = Path.home() / "dev/next_api_bot/worker/bible_lookup.py"
TITLE = re.compile(r"^\s*([가-힣]+)\s*(\d+):(\d+)")
ENDS = ("니", "며", "고", "요", "면", "라", "서", "나", "여", "지", "되", "데")


def verses(book: str, ch: int, a: int, b: int) -> dict[int, str]:
    out = subprocess.run([sys.executable, str(BIBLE), f"{book} {ch}:{a}-{b}"], capture_output=True, text=True).stdout
    return {int(m[1]): m[2].strip() for m in re.finditer(r"^(\d+)\s{2,}(.+)$", out, re.M)}


def lines_of(text: str, width: int = 23) -> list[str]:
    """한 절 → 화면 줄들(기존 암송 장 모양). 어미(…니·…라·…고·…며)에서 마디를 끊고, 마디를 한 줄 23자 안에서 이어 붙인다.
    한 마디가 23자를 넘으면 낱말 사이에서 나눈다."""
    phrases, cur = [], []
    for w in text.split():
        cur.append(w)
        if w.endswith(ENDS): phrases.append(" ".join(cur)); cur = []
    if cur: phrases.append(" ".join(cur))
    parts = []
    for ph in phrases:
        while len(ph) > width:
            ws, line = ph.split(), ""
            while ws and len((line + " " + ws[0]).strip()) <= width: line = (line + " " + ws.pop(0)).strip()
            parts.append(line); ph = " ".join(ws)
        parts.append(ph)
    out = []
    for ph in parts:
        if out and len(out[-1]) + 1 + len(ph) <= width: out[-1] += " " + ph
        else: out.append(ph)
    return [l + " " for l in out[:-1]] + out[-1:]


def focus(date: str) -> list[tuple[str, int, int]]:
    """예배자 악보 암송 쪽 → [(책, 장, 이번 주 절)] (강조가 있는 쪽만)."""
    sys.path.insert(0, str(HERE)); import build
    d = json.loads((HERE / "data" / f"{date}.json").read_text())
    out = []
    for p in d["pages"]:
        if p["type"] != "recite": continue
        v = build.focus_verse(p, date)
        m = re.search(r"([가-힣]+?)\s*(\d+)\s*장", re.sub(r"<[^>]+>", "", p["heading"]))
        if v and m: out.append((m[1], int(m[2]), v))
    return out


def recite_slides(prs) -> list[tuple[int, str, int, int]]:
    """암송 장 — 첫 글상자가 「책 장:절」로 시작하는 장. (번호, 책, 장, 절)"""
    out = []
    for i, s in enumerate(prs.slides):
        sh = next((x for x in s.shapes if x.has_text_frame and x.text_frame.text.strip()), None)
        if not sh: continue
        m = TITLE.match(sh.text_frame.text)
        if m and len(s.shapes) <= 2: out.append((i, m[1], int(m[2]), int(m[3])))
    return out


def body_of(slide) -> str:
    t = slide.shapes[0].text_frame.text
    return re.sub(r"\s+", "", TITLE.sub("", t.replace("\x0b", "\n"), count=1))


def set_title(slide, book: str, ch: int, v: int) -> None:
    runs = slide.shapes[0].text_frame.paragraphs[0].runs
    t = "".join(r.text for r in runs)
    m = TITLE.match(t)
    # 제목은 runs 앞쪽 몇 개에 걸쳐 있을 수 있다(「요한복음 15:1」+「4」) — 첫 run 에 몰아 쓰고 나머지 제목 조각은 비운다
    need, k = len(m.group(0)), 0
    for r in runs:
        if need <= 0: break
        take = min(len(r.text), need); need -= take
        r.text = (f"{book} {ch}:{v}" if k == 0 else "") + r.text[take:]
        k += 1


def fill(slide, title: str, lines: list[str]) -> None:
    txBody = slide.shapes[0].text_frame._txBody
    ps = txBody.findall(A + "p")
    p0 = ps[0]; runs = p0.findall(A + "r")
    runs[0].find(A + "t").text = title
    for r in runs[1:-1]: p0.remove(r)
    runs[-1].find(A + "t").text = lines[0]
    tpl = next(p.find(A + "r") for p in ps[1:] + [p0] if p.find(A + "r") is not None)
    for i, pp in enumerate(ps[1:], 1):
        for r in pp.findall(A + "r"): pp.remove(r)
        if i < len(lines):
            r = copy.deepcopy(tpl); r.find(A + "t").text = lines[i]
            end = pp.find(A + "endParaRPr")
            end.addprevious(r) if end is not None else pp.append(r)
    for i in range(len(ps), len(lines)):
        q = copy.deepcopy(ps[-1])
        for r in q.findall(A + "r"): q.remove(r)
        r = copy.deepcopy(tpl); r.find(A + "t").text = lines[i]
        end = q.find(A + "endParaRPr")
        end.addprevious(r) if end is not None else q.append(r)
        txBody.append(q)


def dup_after(prs, src_idx: int):
    src = prs.slides[src_idx]
    new = prs.slides.add_slide(src.slide_layout)
    for sh in list(new.shapes): sh._element.getparent().remove(sh._element)
    for el in src.shapes._spTree.iterchildren():
        if el.tag.split("}")[-1] in ("sp", "pic", "grpSp", "cxnSp"):
            new.shapes._spTree.append(copy.deepcopy(el))
    if src._element.cSld.bg is not None:
        new._element.cSld.insert(0, copy.deepcopy(src._element.cSld.bg))
    lst = prs.slides._sldIdLst; ids = list(lst)
    last = ids[-1]; lst.remove(last); list(lst)[src_idx].addnext(last)
    return prs.slides[src_idx + 1]


def drop(prs, idx: int) -> None:
    lst = prs.slides._sldIdLst; sid = list(lst)[idx]
    prs.part.drop_rel(sid.rId); lst.remove(sid)


def recite(pptx: Path, date: str) -> list[str]:
    from pptx import Presentation
    prs = Presentation(str(pptx)); log = []
    for book, ch, want in focus(date):
        mine = [x for x in recite_slides(prs) if x[1] == book and x[2] == ch]
        if not mine: log.append(f"{book} {ch}장 암송 장이 PPT 에 없음 — 건너뜀"); continue
        text = verses(book, ch, 1, max(want, max(v for *_, v in mine)))
        for i, *_ , v in mine:                                          # 제목 절 번호를 본문과 대조
            b = body_of(prs.slides[i])
            best = max(text, key=lambda k: SequenceMatcher(None, b, re.sub(r"\s+", "", text[k])).ratio())
            if best != v and SequenceMatcher(None, b, re.sub(r"\s+", "", text[best])).ratio() > 0.8:
                set_title(prs.slides[i], book, ch, best); log.append(f"{i + 1}장 제목 {book} {ch}:{v} → {ch}:{best}")
        mine = [x for x in recite_slides(prs) if x[1] == book and x[2] == ch]
        have = max(v for *_, v in mine)
        while have > want:                                               # 넘치는 장 빼기
            idx = max(mine, key=lambda x: x[3])[0]; drop(prs, idx)
            log.append(f"{book} {ch}:{have} 장 뺌"); have -= 1
            mine = [x for x in recite_slides(prs) if x[1] == book and x[2] == ch]
        last = max(mine, key=lambda x: x[3])[0]
        for v in range(have + 1, want + 1):                              # 모자라는 장 더하기
            s = dup_after(prs, last); last += 1
            fill(s, f"{book} {ch}:{v}", lines_of(text[v]))
            log.append(f"{book} {ch}:{v} 장 더함 ({last + 1}장)")
        log.append(f"{book} {ch}장 암송: {want}절까지 맞춤")
    prs.save(str(pptx))
    return log


# ── 사도신경 장 (2026-10-03 교장님: 가독성 좋고 보기 쉽게 가운데 정렬로) ─────────────
CREED_FIX = [("본디오빌라도", "본디오 빌라도"), ("못박혀", "못 박혀"), ("судитьживых", "судить живых"), ("믿습니다.     아멘", "믿습니다. 아멘")]
INK = {"ko": ("FFFFFF", 52, True, "Noto Sans KR"), "ru": ("F6C76B", 30, True, "Arial"), "en": ("D6E2F5", 30, False, "Arial")}


def script(t: str) -> str:
    return "ko" if re.search(r"[가-힣]", t) else "ru" if re.search(r"[А-Яа-яЁё]", t) else "en"


def creed_slides(prs) -> list:
    """세 언어 사도신경 장 — 머리에 「사도신경」과 «Апостольский», 본문 글상자에 한글과 러시아어가 함께 있는 장."""
    out = []
    for s in prs.slides:
        texts = [x for x in s.shapes if x.has_text_frame and x.text_frame.text.strip()]
        head = next((x for x in texts if "사도신경" in x.text_frame.text and "Апостольский" in x.text_frame.text), None)
        body = next((x for x in texts if x is not head and re.search(r"[가-힣]", x.text_frame.text) and re.search(r"[А-Яа-я]", x.text_frame.text)), None)
        if head and body: out.append((s, head, body))
    return out


def _clean(t: str) -> str:
    t = re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip()
    for a, b in CREED_FIX: t = t.replace(a, b)
    t = re.sub(r"\s+([,.;])", r"\1", t)
    return re.sub(r"([,;])(?=[^\s\d])", r"\1 ", t)


def creed_sections(body) -> list[dict]:
    """본문 글상자 → [{ko:[줄…], ru:[줄…], en:[줄…]}] (한글 줄이 다시 나오면 새 마디). 원래 줄(조각) 단위를 살린다."""
    secs, cur = [], None
    for pa in body.text_frame.paragraphs:
        pieces = [_clean(r.text) for r in pa.runs if r.text.strip()]
        whole = _clean(" ".join(pieces))
        if not whole: continue
        k = script(whole)
        if k == "ko" and (cur is None or cur["ru"] or cur["en"]):
            cur = {"ko": [], "ru": [], "en": []}; secs.append(cur)
        if cur is None: continue
        if k == "ko": cur["ko"].append(whole)
        else: cur[k] += [x for x in pieces if len(x) > 2] or [whole]   # 조각이 줄 하나씩(「,」 같은 부스러기는 붙이지 않음)
    for sec in secs:
        for k in ("ru", "en"):                                         # 부스러기(쉼표만 따로 든 조각)는 앞 줄에
            sec[k] = [x for x in sec[k] if x not in (",", ".", ";")]
    return secs


def _alpha_fill(shape, hexcolor: str, alpha: int) -> None:
    from pptx.dml.color import RGBColor
    shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor.from_string(hexcolor)
    clr = shape.fill._xPr.find(A + "solidFill")[0]
    for x in clr.findall(A + "alpha"): clr.remove(x)
    el = clr.makeelement(A + "alpha", {"val": str(alpha * 1000)}); clr.append(el)
    shape.line.fill.background()


def _para(tf, text: str, kind: str, first: bool = False, before: int = 0):
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Pt
    pa = tf.paragraphs[0] if first else tf.add_paragraph()
    pa.alignment = PP_ALIGN.CENTER; pa.line_spacing = 1.08
    if before: pa.space_before = Pt(before)
    r = pa.add_run(); r.text = text
    c, size, bold, face = INK[kind]
    r.font.size = Pt(size); r.font.bold = bold; r.font.name = face; r.font.color.rgb = RGBColor.from_string(c)
    return pa


def creed(pptx: Path) -> list[str]:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Pt
    prs = Presentation(str(pptx)); W, H = prs.slide_width, prs.slide_height; log = []
    for s, head, body in creed_slides(prs):
        secs = creed_sections(body)
        if not secs: continue
        for sh in s.shapes:                                   # 사진 위 막: 진한 갈색 반투명(글자가 또렷하게)
            if sh.shape_type == 1 and sh.width > W * .9 and sh.height > H * .9 and not sh.text_frame.text.strip():
                _alpha_fill(sh, "2A1F1A", 78); sh.left, sh.top, sh.width, sh.height = 0, 0, W, H   # 화면을 꽉 덮게
            if sh.shape_type == 9:                            # 머리 아래 선: 가운데 짧은 금빛 선
                sh.left, sh.width, sh.top, sh.height = int(W * .38), int(W * .24), int(H * .135), 0
                sh.line.color.rgb = RGBColor.from_string("F6C76B"); sh.line.width = Pt(2)
        head.left, head.width, head.top, head.height = int(W * .04), int(W * .92), int(H * .03), int(H * .09)
        tf = head.text_frame; tf.clear(); tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        pa = tf.paragraphs[0]; pa.alignment = PP_ALIGN.CENTER
        for txt, size, col in (("사도신경", 46, "FFFFFF"), ("   Апостольский Символ веры · Apostles’ Creed", 24, "E8DCCB")):
            r = pa.add_run(); r.text = txt; r.font.size = Pt(size); r.font.bold = True; r.font.name = "Noto Sans KR"; r.font.color.rgb = RGBColor.from_string(col)
        body.left, body.width, body.top, body.height = int(W * .05), int(W * .90), int(H * .17), int(H * .80)
        tf = body.text_frame; tf.clear(); tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        bp = tf._txBody.find(A + "bodyPr")
        for x in list(bp): bp.remove(x)                       # 자동 줄임 끄기(글자 크기는 위에서 정한 대로)
        first = True
        for i, sec in enumerate(secs):
            for j, k in enumerate(sec["ko"]):
                _para(tf, k, "ko", first, before=34 if (i and j == 0) else 0); first = False
            for j, t in enumerate(sec["ru"]): _para(tf, t, "ru", before=8 if j == 0 else 0)
            for j, t in enumerate(sec["en"]): _para(tf, t, "en", before=2 if j == 0 else 0)
        log.append(f"사도신경 장 다시 꾸밈: {secs[0]['ko'][0][:16]}… ({len(secs)}마디)")
    prs.save(str(pptx))
    return log


# ── 글이 칸을 넘지 않게 (2026-10-03 교장님: 광고 페이지 글이 테두리를 넘치지 않도록) ─────────────
def _w(ch: str) -> float:
    """글자 폭(글자 크기 1 기준) — 구글 슬라이드가 쓰는 한글 글꼴보다 조금 넉넉하게 잡는다."""
    if re.match(r"[가-힣ㄱ-ㅎ]", ch): return 1.0
    if ch == " ": return 0.4
    if re.match(r"[0-9]", ch): return 0.58
    if re.match(r"[A-Za-zА-Яа-яЁё]", ch): return 0.62
    if ch in "“”‘’\"'(),.:;-~/&": return 0.38
    return 0.9


def _lines_needed(text: str, size: float, width: float) -> int:
    if not text.strip(): return 1
    n, cur = 0, 0.0
    for word in text.split(" "):
        w = sum(_w(c) for c in word) * size
        sp = _w(" ") * size if cur else 0
        if cur and cur + sp + w > width:
            n += 1; cur = w
            while cur > width: n += 1; cur -= width
        else:
            cur += sp + w
    return n + 1


def _inner(shape) -> tuple[float, float]:
    bp = shape.text_frame._txBody.find(A + "bodyPr")
    g = lambda k, d: int(bp.get(k, d)) / 12700
    return shape.width / 12700 - g("lIns", 91440) - g("rIns", 91440), shape.height / 12700 - g("tIns", 45720) - g("bIns", 45720)


def fits(shape, size: float) -> bool:
    w, h = _inner(shape)
    total = 0.0
    paras = list(shape.text_frame.paragraphs)
    while paras and not "".join(r.text for r in paras[-1].runs).strip(): paras.pop()   # 끝의 빈 문단은 안 보인다
    for pa in paras:                                 # 구글 슬라이드: 줄 높이 = 글자 × 1.2 × 문단 줄 간격(배수)
        ls = pa.line_spacing if isinstance(pa.line_spacing, float) else 1.0
        t = "".join(r.text for r in pa.runs).replace("\x0b", "\n")
        for part in t.split("\n"):
            total += _lines_needed(part, size, w) * size * 1.2 * ls
    return total <= h


def set_size(shape, size: float) -> None:
    from pptx.util import Pt
    for pa in shape.text_frame.paragraphs:
        for r in pa.runs: r.font.size = Pt(size)
        epr = pa._p.find(A + "endParaRPr")
        if epr is not None: epr.set("sz", str(int(size * 100)))


def best_size(shapes, top: float, low: float = 36) -> float:
    s = top
    while s > low and not all(fits(x, s) for x in shapes): s -= 1
    return s


def body_shape(slide):
    xs = [x for x in slide.shapes if x.has_text_frame and x.text_frame.text.strip()]
    return max(xs, key=lambda x: x.width * x.height) if xs else None


def section_slides(prs, start_word: str, stop_word: str) -> list:
    """「교회 소식」 표지 다음부터 「봉헌」 표지 전까지 같은, 큰 글상자 하나짜리 장들."""
    out, on = [], False
    for s in prs.slides:
        t = " ".join(x.text_frame.text for x in s.shapes if x.has_text_frame)
        if start_word in t and len(t) < 80: on = True; continue
        if on and stop_word in t and len(t) < 120: break
        if on: out.append(s)
    return out


def fit_ads(prs) -> list[str]:
    """교회 소식 장들 — 글이 칸을 넘지 않는 가장 큰 크기로, 모든 장을 같은 크기로(최대 60pt)."""
    shapes = [body_shape(s) for s in section_slides(prs, "Announcements", "Offering")]
    shapes = [x for x in shapes if x is not None]
    if not shapes: return []
    top = max((r.font.size.pt for x in shapes for pa in x.text_frame.paragraphs for r in pa.runs if r.font.size), default=60)
    sz = best_size(shapes, min(top, 60))
    for x in shapes: set_size(x, sz)
    return [f"교회 소식 {len(shapes)}장: 글자 {sz:.0f}pt 로 맞춤(칸 안에 다 들어감)"]


# ── 성경 봉독 본문 장: 한 장에 두 절씩 (2026-10-03 교장님) ─────────────
VERSE_LINE = re.compile(r"^\s*(\d+)\s{2,}")


def reading(prs, date: str) -> list[str]:
    """예배자 악보 설교 본문(data/<날짜>.json sermon_text 의 ref)을 봉독 장에 — 한 장에 두 절, 장 수를 맞춘다."""
    d = json.loads((HERE / "data" / f"{date}.json").read_text())
    st = next((p for p in d["pages"] if p["type"] == "sermon_text"), None)
    m = st and re.match(r"\s*([가-힣]+)\s*(\d+):(\d+)-(\d+)", st["ref"])
    if not m: return ["설교 본문 장절을 못 읽음 — 봉독 장 건너뜀"]
    book, ch, a, b = m[1], int(m[2]), int(m[3]), int(m[4])
    text = verses(book, ch, a, b)
    idx = [i for i, s in enumerate(prs.slides) if (x := body_shape(s)) is not None and VERSE_LINE.match(x.text_frame.text)]
    if not idx: return ["봉독 본문 장을 못 찾음"]
    run = [idx[0]]
    for i in idx[1:]:
        if i == run[-1] + 1: run.append(i)
    groups = [list(range(v, min(v + 1, b) + 1)) for v in range(a, b + 1, 2)]
    while len(run) > len(groups): drop(prs, run.pop())
    while len(run) < len(groups): dup_after(prs, run[-1]); run.append(run[-1] + 1)
    for i, g in zip(run, groups):
        sh = body_shape(prs.slides[i]); txBody = sh.text_frame._txBody
        ps = txBody.findall(A + "p")
        tpl = next(p for p in ps if p.find(A + "r") is not None); blank = next((p for p in ps if p.find(A + "r") is None), None)
        for p in ps: txBody.remove(p)
        for j, v in enumerate(g):
            q = copy.deepcopy(tpl)
            for r in q.findall(A + "r")[1:]: q.remove(r)
            q.find(A + "r").find(A + "t").text = f"{v}   {text[v]}"
            txBody.append(q)
        from pptx.util import Pt
        for j, pa in enumerate(sh.text_frame.paragraphs):     # 둘째 절 앞은 한 줄쯤 띄운다(빈 문단 대신)
            pa.space_before = Pt(36) if j else None
    shapes = [body_shape(prs.slides[i]) for i in run]
    sz = best_size(shapes, 60)
    for x in shapes: set_size(x, sz)
    return [f"성경 봉독 {book} {ch}:{a}-{b}: {len(run)}장(두 절씩), 글자 {sz:.0f}pt"]


def _height_actual(shape, k: float = 1.0) -> float:
    """문단·줄마다 실제 글자 크기(× k)로 잰 높이."""
    w, _ = _inner(shape); total = 0.0
    paras = list(shape.text_frame.paragraphs)
    while paras and not "".join(r.text for r in paras[-1].runs).strip(): paras.pop()
    known = [pa.line_spacing for pa in shape.text_frame.paragraphs if isinstance(pa.line_spacing, float)]
    for pa in paras:                                 # 줄 간격이 비어 있는 문단은 같은 상자의 줄 간격을 물려받는다(구글 렌더링)
        ls = pa.line_spacing if isinstance(pa.line_spacing, float) else (max(known) if known else 1.0)
        segs, cur = [], ["", None]
        for r in pa.runs:                                # 줄바꿈(\v)으로 나뉜 조각마다 그 조각의 글자 크기
            for j, part in enumerate(r.text.replace("\x0b", "\n").split("\n")):
                if j: segs.append(cur); cur = ["", None]
                cur[0] += part; cur[1] = cur[1] or (r.font.size.pt if r.font.size else 40)
        segs.append(cur)
        for t, sz in segs:
            sz = (sz or 40) * k
            total += _lines_needed(t, sz, w) * sz * 1.2 * ls
    return total


def fit_recite(prs) -> list[str]:
    """암송 장 — 실제로 넘치는 장만, 제목·본문 크기 비율은 그대로 두고 함께 줄인다."""
    from pptx.util import Pt
    out = []
    for i, *_ in recite_slides(prs):
        sh = prs.slides[i].shapes[0]; h = _inner(sh)[1]
        if _height_actual(sh) <= h: continue
        k = 1.0
        while k > .6 and _height_actual(sh, k) > h: k -= .02
        for pa in sh.text_frame.paragraphs:
            for r in pa.runs:
                if r.font.size: r.font.size = Pt(round(r.font.size.pt * k))
        out.append(f"{i + 1}장 암송 글자 {k * 100:.0f}% 로 줄임")
    return out


# ── 표지 장 문구는 한 문단 한 줄로 (2026-10-03 교장님: 「네 마음을 다하고 뜻을 다하고 힘을 다하여」는 한 줄에) ─────
def one_line(prs, word: str = "성경암송") -> list[str]:
    """그 순서 표지 장의 부제 글상자 — 문단마다 한 줄에 들어가는 크기로(넘으면 줄인다, 문단끼리 같은 크기)."""
    from pptx.util import Pt
    out = []
    for i, s in enumerate(prs.slides):
        texts = [x for x in s.shapes if x.has_text_frame and x.text_frame.text.strip()]
        if not any(x.text_frame.text.strip() == word for x in texts): continue
        for sh in texts:
            paras = [pa for pa in sh.text_frame.paragraphs if "".join(r.text for r in pa.runs).strip()]
            if len(paras) < 2 or any(len("".join(r.text for r in pa.runs)) < 8 for pa in paras): continue
            w = _inner(sh)[0]
            size = max(r.font.size.pt for pa in paras for r in pa.runs if r.font.size)
            new = size
            while new > 24 and any(_lines_needed("".join(r.text for r in pa.runs).strip(), new, w) > 1 for pa in paras): new -= 1
            new = min(size, new - 1) if new < size else size              # 렌더링 글꼴 차이를 생각해 1pt 더 여유
            if new < size:
                for pa in paras:
                    for r in pa.runs: r.font.size = Pt(new)
                out.append(f"{i + 1}장 「{word}」 부제: 문단마다 한 줄로 {size:.0f}→{new:.0f}pt")
        break
    return out


def layout(pptx: Path, date: str) -> list[str]:
    from pptx import Presentation
    prs = Presentation(str(pptx))
    log = reading(prs, date) + fit_ads(prs) + fit_recite(prs) + one_line(prs, "성경암송")
    prs.save(str(pptx))
    return log


def render_check(pptx: Path, pdf: Path | None = None, fix: bool = True) -> list[str]:
    """구글 슬라이드로 바꿔 PDF 로 그려 보고, 글이 제 칸(또는 화면) 아래로 넘친 장을 비율대로 줄인다(최대 3번)."""
    import fitz, tempfile, uuid
    from pptx import Presentation
    from pptx.util import Pt
    sys.path.insert(0, str(HERE.parent)); import prep
    log = []
    for _ in range(3):
        g = prep.G(prep.access_token()); b = f"b{uuid.uuid4().hex}"
        meta = json.dumps({"name": "_임시 넘침 검사", "mimeType": "application/vnd.google-apps.presentation"}).encode()
        body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta + f"\r\n--{b}\r\nContent-Type: {prep.PPTX_MIME}\r\n\r\n".encode()
                + pptx.read_bytes() + f"\r\n--{b}--".encode())
        f = g.req("POST", f"{prep.UPLOAD}/files?uploadType=multipart&fields=id", body, ctype=f"multipart/related; boundary={b}", timeout=600)
        try:
            raw = g.req("GET", f"{prep.DRIVE}/files/{f['id']}/export?mimeType=application/pdf", timeout=600)
        finally:
            g.req("DELETE", f"{prep.DRIVE}/files/{f['id']}")
        if pdf: pdf.write_bytes(raw)
        doc = fitz.open(stream=raw, filetype="pdf"); prs = Presentation(str(pptx))
        kx = doc[0].rect.width / (prs.slide_width / 12700); over = []
        for i, s in enumerate(prs.slides):
            sh = body_shape(s)
            if sh is None or sh.height < prs.slide_height * .5: continue          # 큰 본문 글상자만(표지 장 제외)
            x0, y0 = sh.left / 12700 * kx, sh.top / 12700 * kx
            x1, y1 = x0 + sh.width / 12700 * kx, min(y0 + sh.height / 12700 * kx, doc[i].rect.height)
            ys = [l["bbox"] for bl in doc[i].get_text("dict")["blocks"] if bl["type"] == 0 for l in bl["lines"]
                  if "".join(sp["text"] for sp in l["spans"]).strip() and x0 - 4 <= (l["bbox"][0] + l["bbox"][2]) / 2 <= x1 + 4 and l["bbox"][1] >= y0 - 4]
            if ys and max(y[3] for y in ys) > y1 + 2:
                bot = max(y[3] for y in ys); top = min(y[1] for y in ys)
                over.append((i, (y1 - top) / (bot - top)))
        if not over or not fix:
            log.append("넘치는 장 없음" if not over else "넘침: " + ", ".join(f"{i + 1}장" for i, _ in over)); break
        for i, k in over:
            sh = body_shape(prs.slides[i])
            for pa in sh.text_frame.paragraphs:
                for r in pa.runs:
                    if r.font.size: r.font.size = Pt(int(r.font.size.pt * k * 0.98))
            log.append(f"{i + 1}장 글이 넘쳐 {k * 98:.0f}% 로 줄임")
        prs.save(str(pptx))
    return log


def upload(pptx: Path, date: str) -> str:
    """드라이브의 그 주 「…주일예배 PPT」(.pptx)를 같은 파일로 갱신(판 기록은 드라이브에 남는다)."""
    import datetime as dt
    sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
    import prep, weekly
    g = prep.G(prep.access_token()); fo = weekly.week_folder(g, dt.date.fromisoformat(date))
    r = g.get(f"{prep.DRIVE}/files", q=f"'{fo['id']}' in parents and trashed=false and name contains '주일예배 PPT'",
              fields="files(id,name,mimeType,modifiedTime)", includeItemsFromAllDrives="true")
    f = next(x for x in sorted(r["files"], key=lambda x: x["modifiedTime"], reverse=True) if x["mimeType"].endswith("presentationml.presentation"))
    g.req("PATCH", f"{prep.UPLOAD}/files/{f['id']}?uploadType=media&supportsAllDrives=true", pptx.read_bytes(),
          ctype=prep.PPTX_MIME, timeout=600)
    return f["name"]


if __name__ == "__main__":
    a = sys.argv[1:]; date = a[0]
    px = HERE / "worship_ppt" / f"{date}.pptx"
    for line in recite(px, date) + creed(px) + layout(px, date) + render_check(px): print(line)
    if "--upload" in a: print("드라이브 갱신:", upload(px, date))
