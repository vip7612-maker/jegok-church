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


def save(prs, pptx: Path) -> None:
    """저장 전에 슬라이드 파일 이름을 순서대로 다시 매긴다 — 장을 빼고 더하다 보면 이름이 겹쳐 PPTX 가 깨진다."""
    from pptx.opc.packuri import PackURI
    parts = [s.part for s in prs.slides]
    for k, part in enumerate(parts, 1): part.partname = PackURI(f"/ppt/slides/tmp_slide{k}.xml")
    for k, part in enumerate(parts, 1): part.partname = PackURI(f"/ppt/slides/slide{k}.xml")
    prs.save(str(pptx))


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
    save(prs, pptx)
    return log


# ── 사도신경 장 (2026-10-03 교장님: 가독성 좋고 보기 쉽게 가운데 정렬로) ─────────────
CREED_FIX = [("본디오빌라도", "본디오 빌라도"), ("못박혀", "못 박혀"), ("судитьживых", "судить живых"), ("믿습니다.     아멘", "믿습니다. 아멘")]
INK = {"ko": ("FFFFFF", 58, True, "Noto Sans KR"), "ru": ("F6C76B", 40, True, "Arial"), "en": ("D6E2F5", 38, False, "Arial")}


def script(t: str) -> str:
    return "ko" if re.search(r"[가-힣]", t) else "ru" if re.search(r"[А-Яа-яЁё]", t) else "en"


def creed_slides(prs) -> list:
    """세 언어 사도신경 장 — 본문 글상자에 한글·러시아어·영어가 함께 있는 장. (장, 머리 글상자 또는 None, 본문)"""
    out = []
    for s in prs.slides:
        texts = [x for x in s.shapes if x.has_text_frame and x.text_frame.text.strip()]
        head = next((x for x in texts if "사도신경" in x.text_frame.text and "Апостольский" in x.text_frame.text and len(x.text_frame.text) < 80), None)
        body = next((x for x in texts if x is not head and re.search(r"[가-힣]", x.text_frame.text) and re.search(r"[А-Яа-я]", x.text_frame.text)
                     and re.search(r"[A-Za-z]{4}", x.text_frame.text)), None)
        if body: out.append((s, head, body))
    return out


KO_ENDS = ("와", "과", "며", "고", "서", "님", "들", "아", "어", "에", "가", ",")


# 사도신경은 글이 바뀌지 않는다 — 줄 나눔을 표로 정해 둔다(교장님이 정한 자리). 표에 없으면 아래 규칙으로.
CREED_KO = {
    "거기로부터 살아 있는 자와 죽은 자를 심판하러 오십니다.": ["거기로부터 살아 있는 자와 죽은 자를", "심판하러 오십니다."],   # 2026-10-03 교장님
}


def ko_lines(text: str, width_chars: float = 21) -> list[str]:
    """사도신경 한 마디(한국어) → 한 줄 또는 두 줄. 한 줄에 들어가면 그대로, 아니면 두 줄 길이가 비슷하고
    말이 끝나는 자리(…와·…아·…서·…님 …)에서 나눈다 (2026-10-03 교장님: 「거기로부터 살아 있는 자와 / 죽은 자를 심판하러 오십니다.」)."""
    t = re.sub(r"\s+", " ", text).strip()
    if t in CREED_KO: return list(CREED_KO[t])
    if len(t) <= width_chars: return [t]
    w = t.split(" "); best = None
    for i in range(1, len(w)):
        a, b = " ".join(w[:i]), " ".join(w[i:])
        score = max(len(a), len(b)) + (0 if w[i - 1].endswith(KO_ENDS) else 6)
        if best is None or score < best[0]: best = (score, [a, b])
    return best[1]


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
        for sh in list(s.shapes):                             # 사진 위 막: 진한 갈색 반투명(글자가 또렷하게)
            if sh.shape_type == 1 and sh.width > W * .9 and sh.height > H * .9 and not sh.text_frame.text.strip():
                _alpha_fill(sh, "2A1F1A", 78); sh.left, sh.top, sh.width, sh.height = 0, 0, W, H   # 화면을 꽉 덮게
            if sh.shape_type == 9: sh._element.getparent().remove(sh._element)       # 머리 아래 선은 뺀다
        if head is not None: head._element.getparent().remove(head._element)      # 「사도신경 · Апостольский … · Apostles’ Creed」 머리는 뺀다(교장님)
        body.left, body.width, body.top, body.height = int(W * .04), int(W * .92), int(H * .04), int(H * .92)   # 위아래 여백까지 본문에
        tf = body.text_frame; tf.clear(); tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        bp = tf._txBody.find(A + "bodyPr")
        for x in list(bp): bp.remove(x)                       # 자동 줄임 끄기(글자 크기는 위에서 정한 대로)
        first = True
        for i, sec in enumerate(secs):
            for j, k in enumerate(ko_lines(" ".join(sec["ko"]))):
                _para(tf, k, "ko", first, before=34 if (i and j == 0) else 0); first = False
            for j, t in enumerate(sec["ru"]): _para(tf, t, "ru", before=8 if j == 0 else 0)
            for j, t in enumerate(sec["en"]): _para(tf, t, "en", before=2 if j == 0 else 0)
        log.append(f"사도신경 장 다시 꾸밈: {secs[0]['ko'][0][:16]}… ({len(secs)}마디)")
    save(prs, pptx)
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
VERSE_LINE = re.compile(r"^\s*(?:(?:봉독대표|회중봉독|다함께 봉독)\s*\n)?\s*(\d+)\s+(?=[가-힣])")   # 「1   …」·옛 PPT 「1 …」 모두   # 앞에 봉독 단추 줄이 붙어 있어도


# 성경 봉독 — 절마다 위에 작은 단추(누가 읽는지) (2026-10-04 교장님 원칙)
#   첫 절 「봉독대표」 → 다음 절 「회중봉독」 → 번갈아. 마지막 절이 홀수 번째(1·3·5…)면 「다함께 봉독」.
#   전체가 3절 미만이면 모든 절 「다함께 봉독」.
READ_LABEL_FILL, READ_LABEL_TEXT = "F6C76B", "3B2A06"     # 봉독 장 바탕이 갈색이라 금빛 단추·짙은 글씨


def read_label(k: int, n: int) -> str:
    """k = 본문 안 몇 번째 절(0부터), n = 전체 절 수."""
    if n < 3: return "다함께 봉독"
    if k == n - 1 and k % 2 == 0: return "다함께 봉독"
    return "봉독대표" if k % 2 == 0 else "회중봉독"


def _label_para(tpl, label: str):
    """본문 문단 틀을 본떠 「 봉독대표 」 한 줄 — 금빛 바탕(형광) 짙은 굵은 글씨라 작은 단추처럼 보인다."""
    from lxml import etree
    q = copy.deepcopy(tpl)
    for r in q.findall(A + "r")[1:]: q.remove(r)
    r = q.find(A + "r"); r.find(A + "t").text = f" {label} "
    rp = r.find(A + "rPr")
    if rp is None: rp = etree.SubElement(r, A + "rPr"); r.remove(rp); r.insert(0, rp)
    rp.set("b", "1")
    for tag in ("solidFill", "highlight", "gradFill", "noFill"):
        for x in rp.findall(A + tag): rp.remove(x)
    fill = etree.Element(A + "solidFill"); etree.SubElement(fill, A + "srgbClr").set("val", READ_LABEL_TEXT)
    hl = etree.Element(A + "highlight"); etree.SubElement(hl, A + "srgbClr").set("val", READ_LABEL_FILL)
    ln = rp.find(A + "ln"); rp.insert(list(rp).index(ln) + 1 if ln is not None else 0, fill)
    after = [x for x in rp if etree.QName(x).localname in ("uLnTx", "uLn", "uFillTx", "uFill", "latin", "ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst")]
    if after: rp.insert(list(rp).index(after[0]), hl)
    else: rp.append(hl)
    return q


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
        _pt = lambda p: "".join(t.text or "" for t in p.iter(A + "t"))
        tpl = next((p for p in ps if p.find(A + "r") is not None and re.match(r"\s*\d", _pt(p))),       # 절 문단(단추 줄 말고)을 틀로
                   next(p for p in ps if p.find(A + "r") is not None)); blank = next((p for p in ps if p.find(A + "r") is None), None)
        for p in ps: txBody.remove(p)
        for j, v in enumerate(g):
            txBody.append(_label_para(tpl, read_label(v - a, b - a + 1)))      # 절 위에 누가 읽는지 작은 단추
            q = copy.deepcopy(tpl)
            for r in q.findall(A + "r")[1:]: q.remove(r)
            q.find(A + "r").find(A + "t").text = f"{v}   {text[v]}"
            txBody.append(q)
        from pptx.util import Pt
        for j, pa in enumerate(sh.text_frame.paragraphs):     # 둘째 절(의 단추) 앞은 한 줄쯤 띄우고, 단추와 절 사이는 살짝
            pa.space_before = Pt(36) if j == 2 else (Pt(4) if j % 2 else None)
    shapes = [body_shape(prs.slides[i]) for i in run]
    sz = best_size(shapes, 60)
    for x in shapes:
        set_size(x, sz)
        for j, pa in enumerate(x.text_frame.paragraphs):      # 단추 글씨는 본문의 절반쯤
            if j % 2 == 0:
                for r in pa.runs: r.font.size = Pt(max(18, round(sz * 0.5)))
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


def creed_cover(prs) -> list[str]:
    """사도신경 표지 장(「사도신경」 큰 제목 + 한글 전문) — 전문 글상자를 흰 바탕 폭으로 넓히고 한 문장 한 줄,
    제목 아래부터 흰 바탕 아래 끝 안에 들어가는 크기로(2026-10-03 교장님: 줄이 벗어나 넘친다)."""
    from pptx.util import Pt
    W, H = prs.slide_width, prs.slide_height; out = []
    for i, s in enumerate(prs.slides):
        texts = [x for x in s.shapes if x.has_text_frame and x.text_frame.text.strip()]
        if not any(x.text_frame.text.strip() == "사도신경" for x in texts): continue
        body = next((x for x in texts if "전능하신" in x.text_frame.text and not re.search(r"[А-Яа-я]", x.text_frame.text)
                     and len([p for p in x.text_frame.paragraphs if p.runs]) >= 6), None)
        if body is None: continue
        for pa in body.text_frame.paragraphs:
            for r in pa.runs: r.text = re.sub(r",(?=\S)", ", ", r.text)
            pa.line_spacing = 1.25; pa.space_before = None; pa.space_after = None
        body.left, body.width = int(W * .065), int(W * .60)            # 흰 바탕(오른쪽 사진 앞까지) 안
        body.top, body.height = int(H * .475), int(H * .44)            # 제목 밑 선 아래 ~ 흰 바탕 아래 끝 위
        bp = body.text_frame._txBody.find(A + "bodyPr")
        for x in list(bp): bp.remove(x)
        size = 30
        while size > 14 and not (fits(body, size) and all(_lines_needed("".join(r.text for r in pa.runs), size, _inner(body)[0]) <= 1
                                                          for pa in body.text_frame.paragraphs if pa.runs)):
            size -= 0.5
        set_size(body, size)
        out.append(f"{i + 1}장 사도신경 표지 전문: 한 문장 한 줄, {size:g}pt")
        break
    return out


# 한 줄로 보여야 하는 문구 — 글상자가 좁아 둘로 꺾이던 것 (2026-10-04 교장님)
ONE_LINE = ["성도 모두가 함께 마음을 모아 기도해 주시기 바랍니다", "하나님 아버지의 사랑과 성령님의 교통하심이"]


def keep_one_line(prs, phrases=ONE_LINE) -> list[str]:
    """그 문구가 든 글상자를 흰 바탕(화면 폭 6~70%) 안에서 가운데를 지킨 채 넓혀 문단마다 한 줄로. 그래도 넘치면 1pt씩(20pt 까지) 줄인다."""
    from pptx.util import Pt, Emu
    W = prs.slide_width; out = []
    keys = [re.sub(r"\s", "", x) for x in phrases]
    for i, s in enumerate(prs.slides):
        for sh in s.shapes:
            if not sh.has_text_frame: continue
            flat = re.sub(r"\s", "", sh.text_frame.text)
            if not any(k in flat for k in keys): continue
            lo, hi = W * 0.06, W * 0.70
            c = sh.left + sh.width / 2
            half = min(c - lo, hi - c)
            if half * 2 > sh.width:
                sh.left, sh.width = Emu(int(c - half)), Emu(int(half * 2))
            paras = [pa for pa in sh.text_frame.paragraphs if pa.text.strip()]
            w = _inner(sh)[0]
            size = max((r.font.size.pt for pa in paras for r in pa.runs if r.font.size), default=24)
            new = size
            while new > 20 and any(_lines_needed(pa.text.replace("\v", " ").strip(), new, w) > 1 for pa in paras): new -= 1
            if new < size:
                for pa in paras:
                    for r in pa.runs: r.font.size = Pt(new)
            out.append(f"{i + 1}장 한 줄로: 글상자 폭 {sh.width / W:.0%}" + (f", {size:.0f}→{new:.0f}pt" if new < size else ""))
    return out


READER_PT = 36       # 성경봉독 봉독자 이름 — 틀의 24pt 의 1.5배 (2026-10-04 교장님). 다시 돌려도 더 커지지 않게 고정값


def reader_size(prs) -> list[str]:
    """「성경 봉독」 표지 장의 봉독자 이름 글상자(본문 표기 아래 작은 글상자)를 READER_PT 로."""
    from pptx.util import Pt
    H = prs.slide_height; out = []
    for i, s in enumerate(prs.slides):
        ts = [x for x in s.shapes if x.has_text_frame and x.text_frame.text.strip()]
        if not any(re.sub(r"\s", "", x.text_frame.text) in ("성경봉독", "ScriptureReading") for x in ts): continue
        low = [x for x in ts if x.top > H * 0.62 and re.search(r"[가-힣]", x.text_frame.text) and len(x.text_frame.text) < 20]
        for sh in low:
            runs = [r for pa in sh.text_frame.paragraphs for r in pa.runs]
            if runs and all((r.font.size.pt if r.font.size else 0) < READER_PT for r in runs):
                for r in runs: r.font.size = Pt(READER_PT)
                out.append(f"{i + 1}장 봉독자 이름 「{sh.text_frame.text.strip()}」 {READER_PT}pt")
    return out


def layout(pptx: Path, date: str) -> list[str]:
    from pptx import Presentation
    prs = Presentation(str(pptx))
    log = reading(prs, date) + fit_ads(prs) + fit_recite(prs) + one_line(prs, "성경암송") + creed_cover(prs) + keep_one_line(prs) + reader_size(prs)
    save(prs, pptx)
    return log



def _light_bytes(pptx: Path) -> bytes:
    """구글 변환용 가벼운 사본 — 그림을 1600px·다시 압축(원본 PPT 는 그대로). 옛 PPT 는 그림이 커서
    「This file is too large to be exported」 로 막혔다(2026-09-27, 2026-10-04 교장님 소급 작업)."""
    import zipfile, io as _io
    from PIL import Image
    src = zipfile.ZipFile(pptx); out = _io.BytesIO(); dst = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for it in src.infolist():
        b = src.read(it.filename)
        if it.filename.startswith("ppt/media/") and it.file_size > 150_000 and it.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            try:
                im = Image.open(_io.BytesIO(b)); im.thumbnail((1600, 1600)); o = _io.BytesIO()
                if it.filename.lower().endswith(".png"): im.save(o, "PNG", optimize=True)
                else: im.convert("RGB").save(o, "JPEG", quality=82)
                if o.tell() < len(b): b = o.getvalue()
            except Exception:
                pass
        dst.writestr(it, b)
    dst.close(); return out.getvalue()


def google_pdf(pptx: Path) -> bytes:
    """pptx → 구글 슬라이드로 잠깐 바꿔 PDF(임시본은 지움). 너무 커서 내보내기가 막히면 장을 나눠 여러 번 내보내 이어 붙인다
    (쪽 순서는 그대로 — 넘침 검사·웹 PPT 가 쪽 번호로 장을 맞춘다). 2026-10-04 9/27 소급 작업에서."""
    import uuid, tempfile, fitz
    from pptx import Presentation
    sys.path.insert(0, str(HERE.parent)); import prep
    def one(data: bytes) -> bytes:
        g = prep.G(prep.access_token()); b = f"b{uuid.uuid4().hex}"
        meta = json.dumps({"name": "_임시 변환", "mimeType": "application/vnd.google-apps.presentation"}).encode()
        body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta + f"\r\n--{b}\r\nContent-Type: {prep.PPTX_MIME}\r\n\r\n".encode()
                + data + f"\r\n--{b}--".encode())
        f = g.req("POST", f"{prep.UPLOAD}/files?uploadType=multipart&fields=id", body, ctype=f"multipart/related; boundary={b}", timeout=600)
        try: return g.req("GET", f"{prep.DRIVE}/files/{f['id']}/export?mimeType=application/pdf", timeout=600)
        finally: g.req("DELETE", f"{prep.DRIVE}/files/{f['id']}")
    try:
        return one(_light_bytes(pptx))
    except RuntimeError as ex:
        if "exportSizeLimitExceeded" not in str(ex) and "too large" not in str(ex): raise
    n = len(Presentation(str(pptx)).slides)
    for parts in (2, 3, 4, 6):
        size = -(-n // parts); out = fitz.open(); ok = True
        with tempfile.TemporaryDirectory() as tmp:
            for a in range(0, n, size):
                prs = Presentation(str(pptx))
                for i in sorted(set(range(n)) - set(range(a, min(n, a + size))), reverse=True): drop(prs, i)
                part = Path(tmp) / f"p{a}.pptx"; save(prs, part)
                try:
                    out.insert_pdf(fitz.open(stream=one(_light_bytes(part)), filetype="pdf"))
                except RuntimeError as ex:
                    if "too large" in str(ex) or "exportSizeLimitExceeded" in str(ex): ok = False; break
                    raise
        if ok: return out.tobytes()
    raise RuntimeError("나눠 보내도 구글 내보내기 크기 한도를 넘습니다")


def render_check(pptx: Path, pdf: Path | None = None, fix: bool = True) -> list[str]:
    """구글 슬라이드로 바꿔 PDF 로 그려 보고, 글이 제 칸(또는 화면) 아래로 넘친 장을 비율대로 줄인다(최대 3번)."""
    import fitz, tempfile, uuid
    from pptx import Presentation
    from pptx.util import Pt
    sys.path.insert(0, str(HERE.parent)); import prep
    log = []
    for _ in range(3):
        raw = google_pdf(pptx)
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
        save(prs, pptx)
    return log


# ── 곡 장 넣기: 콘티 순서대로 찬양 자리에 곡별 PPT 의 장을 (2026-10-03 교장님: 내려받은 PPT 에도 악보가 있어야) ─────
SONG_TAG = "songppt|"


def _divider(slide) -> str | None:
    t = re.sub(r"\s", "", " ".join(x.text_frame.text for x in slide.shapes if x.has_text_frame))
    if ("찬양과경배" in t or "찬양과결단" in t) and "Praise&Worship" in t and len(t) < 160:
        return "결단" if "찬양과결단" in t else "경배"
    return None


def is_song_slide(slide) -> bool:
    return any(sh.name.startswith(SONG_TAG) for sh in slide.shapes)


def strip_songs(prs) -> int:
    n = 0
    for i in reversed(range(len(prs.slides))):
        if is_song_slide(prs.slides[i]): drop(prs, i); n += 1
    return n


def base_copy(pptx: Path, dst: Path) -> Path:
    """곡 장을 뺀 사본 — 구글 변환(PDF·넘침 검사)은 이것으로(곡 장까지 넣으면 구글 내보내기 크기 한도를 넘는다)."""
    from pptx import Presentation
    prs = Presentation(str(pptx)); strip_songs(prs); save(prs, dst)
    return dst


def to_pdf(src: Path, dst: Path) -> Path:
    """pptx → 구글 슬라이드로 잠깐 바꿔 PDF 로 내보내고 임시본은 지운다."""
    import uuid
    sys.path.insert(0, str(HERE.parent)); import prep
    g = prep.G(prep.access_token()); b = f"b{uuid.uuid4().hex}"
    meta = json.dumps({"name": "_임시 변환", "mimeType": "application/vnd.google-apps.presentation"}).encode()
    body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta + f"\r\n--{b}\r\nContent-Type: {prep.PPTX_MIME}\r\n\r\n".encode()
            + _light_bytes(src) + f"\r\n--{b}--".encode())
    f = g.req("POST", f"{prep.UPLOAD}/files?uploadType=multipart&fields=id", body, ctype=f"multipart/related; boundary={b}", timeout=600)
    try:
        dst.write_bytes(g.req("GET", f"{prep.DRIVE}/files/{f['id']}/export?mimeType=application/pdf", timeout=600))
    finally:
        g.req("DELETE", f"{prep.DRIVE}/files/{f['id']}")
    return dst


def songs(pptx: Path, date: str) -> list[str]:
    """찬양과경배·찬양과결단 표지마다 바로 뒤에 그 순서 곡의 장을 모두(악보 그림 + 자막 글상자).
    전에 넣은 곡 장(모양 이름 songppt|…)은 먼저 빼고 다시 넣는다 — 콘티가 바뀌어도 겹치지 않는다."""
    import base64, io
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Pt
    import songbank, songppt as SP
    prs = Presentation(str(pptx)); W, H = prs.slide_width, prs.slide_height; kx, ky = W / 1920, H / 1080
    strip_songs(prs)                                               # 예전에 넣은 곡 장 빼기
    for i in reversed(range(1, len(prs.slides))):                 # 같은 표지가 연달아 있으면 1장만(2026-10-07 교장님: 찬양과경배 표지는 1개, 곡은 그 아래)
        if _divider(prs.slides[i]) and _divider(prs.slides[i]) == _divider(prs.slides[i - 1]): drop(prs, i)
    import slides as SL
    try: d = json.loads((HERE / "data" / f"{date}.json").read_text()).get("songs", {})
    except Exception: d = {}
    groups = {g: [x.get("title", "") for x in d.get(g, [])] for g in ("intro", "main", "apply")}
    divs = [i for i, s in enumerate(prs.slides) if _divider(s)]
    plan = SL.song_plan([_divider(prs.slides[i]) for i in divs], groups)
    if sum(map(len, plan)) < sum(map(len, groups.values())):
        return [f"찬양 표지가 없어 곡 장을 넣지 않음(표지 {len(divs)}장)"]
    blank = next((l for l in prs.slide_layouts if l.name.upper() == "BLANK"), prs.slide_layouts[-1])
    import store
    log, shift = [], 0
    for di, title in ((di, t) for di, ts in zip(divs, plan) for t in ts):   # 표지 하나 아래 그 순서 곡을 차례로
        key = store.song_find(title)                              # 곡별 PPT 는 예배 DB + 그림 창고에서(로컬 사본 없이)
        song = store.song_load(key) if key else None
        if not song:
            log.append(f"「{title}」 곡별 PPT 없음 — 자리만 둠"); continue
        at = di + shift
        for j, sl in enumerate(song["slides"], 1):
            new = prs.slides.add_slide(blank)
            for ph in list(new.placeholders): ph._element.getparent().remove(ph._element)
            bg = new.background.fill; bg.solid(); bg.fore_color.rgb = RGBColor(255, 255, 255)
            x, y, w, h = sl["pic"]
            pic = new.shapes.add_picture(io.BytesIO(base64.b64decode(sl["img"])), int(x * kx), int(y * ky), int(w * kx), int(h * ky))
            pic.name = f"{SONG_TAG}{key}|{j}"
            lay = SP.sub_layout(sl.get("sub"))              # 자막 통일: 아래 띠 20% — 위 절반 러시아어(노랑)·아래 절반 영어(흰색)
            if lay:
                from pptx.enum.shapes import MSO_SHAPE
                bx, by, bw, bh = lay["box"]
                band = new.shapes.add_shape(MSO_SHAPE.RECTANGLE, int(bx * kx), int(by * ky), int(bw * kx), int(bh * ky))
                band.name = f"{SONG_TAG}{key}|{j}|band"; band.fill.solid(); band.fill.fore_color.rgb = RGBColor(0, 0, 0); band.line.fill.background()
                for k, ln in enumerate(lay["lines"]):
                    tb = new.shapes.add_textbox(int(ln["x"] * kx), int(ln["y"] * ky), int(ln["w"] * kx), int(ln["size"] * 1.12 * ky))
                    tb.name = f"{SONG_TAG}{key}|{j}|sub{k}"
                    tf = tb.text_frame; tf.word_wrap = False
                    bp = tf._txBody.find(A + "bodyPr")
                    for ins in ("lIns", "rIns", "tIns", "bIns"): bp.set(ins, "0")
                    pa = tf.paragraphs[0]; pa.alignment = PP_ALIGN.CENTER
                    r = pa.add_run(); r.text = ln["t"]; r.font.bold = True; r.font.name = "Arial"
                    r.font.size = Pt(ln["size"] * 0.75 * 0.96); r.font.color.rgb = RGBColor.from_string(ln["c"].lstrip("#"))
            lst = prs.slides._sldIdLst; last = list(lst)[-1]; lst.remove(last); list(lst)[at].addnext(last); at += 1
        shift += len(song["slides"])
        log.append(f"「{title}」 → {key} {len(song['slides'])}장")
    save(prs, pptx)
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
    from pptx import Presentation
    prs = Presentation(str(px)); n = strip_songs(prs); save(prs, px)
    if n: print(f"곡 장 {n}장 먼저 뺌(다시 넣음)")
    for line in recite(px, date) + creed(px) + layout(px, date) + render_check(px, px.with_suffix(".pdf")): print(line)
    for line in songs(px, date): print(line)
    if "--upload" in a: print("드라이브 갱신:", upload(px, date))
