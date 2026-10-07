#!/usr/bin/env python3
"""주보 PDF 의 예배순서 읽기 규칙 — 교회마다 다른 주보 꼴에서 순서·맡은 분·설교 제목·성경 본문을 찾는다 (2026-10-07 교장님).

PDF 를 kordoc 으로 글(표는 <table>)로 바꾼 뒤 아래 규칙을 차례로 쓴다. 규칙으로 덜 읽히면 Claude 가 읽고(같은 규칙을 지시),
어느 쪽이든 주보 원문에 그대로 있는 글자만 받는다(지어내지 않음).

 1. 줄 만들기   표는 칸 그대로, 표 밖 글줄은 점선·말줄임(…·····)·긴 빈칸으로 칸을 나눈다.
               PDF 는 글자 사이에 빈칸이 끼므로(「기 도」「정영선 목 사」) 순서 이름은 빈칸을 빼고 본다.
 2. 순서표 찾기  첫 칸이 순서 이름(아래 표)인 줄이 3개 넘게 모인 곳. 예배가 여럿(1부·2부·오후)이면 순서 이름이 가장 많은 곳,
               같으면 앞의 것. 그 사이의 모르는 짧은 이름(환영·파송 등)도 순서로 받는다. 맞는 줄 사이가 4줄 넘게 비면 끊는다.
 3. 칸 가르기   한 줄의 나머지 칸을 하나씩 본다.
               · 성경 본문  책 이름(66권·줄임말) + 장:절   예) 역대상28:1-10, 요 3:16, 시편 23편
               · 찬송       (새)찬송(가) 000장 / 000장      → 곡이라 순서 칸에 넣지 않는다
               · 맡은 분    이름 + 직분(목사·장로·권사·집사·전도사·선교사·성도·학생·청년·어린이·가정·부부…),
                            직분 + 이름(담임목사 홍길동), 다같이·회중·찬양대·인도자 …, 직분 없이 이름만(2~4자)
               · 제목       「」『』“” 안의 글, 또는 위에 해당하지 않는 나머지 글(설교 줄에서만 제목으로 쓴다)
 4. 이름 맞추기  NAMES 표 — 헌금→봉헌, 신앙고백→사도신경, 말씀→설교, 광고→교회소식, 축복기도→축도 …
               「찬양·찬송」은 자리로 가른다: 설교 뒤 → 찬양과 결단 / 봉독~설교 사이에 한 사람·팀이 맡으면 → 특송 / 그 밖 → 찬양과 경배
               예배인도·사회·반주·봉헌기도·헌금위원은 PPT 순서가 아니라 뺀다.
 5. 오늘의 말씀  순서표에 설교 제목·본문이 비면 「오늘의 말씀·설교·말씀」 머리 아래 「제목 (책 장:절)」에서 채운다.
               설교 줄에만 본문이 있고 성경봉독 줄에 없으면 봉독 본문으로 쓴다.
 6. 원문 대조   모든 값은 빈칸을 뺀 원문 안에 그대로 있어야 한다. 없으면 버린다.
"""
from __future__ import annotations
import html, json, os, re, subprocess, tempfile
from pathlib import Path

# ── 4. 순서 이름표 (빈칸 뺀 글 → PPT 순서 이름). 값이 None 이면 PPT 순서가 아니라 뺀다 ──
NAMES = {
    "성경암송": "성경암송", "암송": "성경암송", "말씀암송": "성경암송",
    "찬양과경배": "찬양과경배", "경배와찬양": "찬양과경배", "찬양예배": "찬양과경배", "경배찬양": "찬양과경배",
    "찬양": "찬양", "찬송": "찬양", "찬송가": "찬양", "회중찬송": "찬양",          # 자리로 가른다(4)
    "사도신경": "사도신경", "사도신조": "사도신경", "신앙고백": "사도신경", "신앙고백사도신경": "사도신경",
    "대표기도": "대표기도", "기도": "대표기도", "공중기도": "대표기도", "대표기도자": "대표기도",
    "교회소식": "교회소식", "광고": "교회소식", "교회광고": "교회소식", "알림": "교회소식", "교회알림": "교회소식",
    "봉헌": "봉헌", "헌금": "봉헌", "예물봉헌": "봉헌", "헌상": "봉헌",
    "성경봉독": "성경봉독", "봉독": "성경봉독", "말씀봉독": "성경봉독", "성경말씀": "성경봉독", "성경": "성경봉독",
    "특송": "특송", "특별찬양": "특송", "찬양대": "특송", "성가대": "특송", "찬양대찬양": "특송", "성가대찬양": "특송", "봉헌찬양": "특송",
    "설교": "설교", "말씀": "설교", "말씀선포": "설교", "설교말씀": "설교",
    "찬양과결단": "찬양과결단", "결단찬양": "찬양과결단", "헌신찬양": "찬양과결단", "결단의찬양": "찬양과결단",
    "축도": "축도", "축복기도": "축도", "축복선언": "축도",
    "예배의부름": "예배의 부름", "예배로의부름": "예배의 부름", "부름": "예배의 부름", "묵도": "묵도", "주기도문": "주기도문",
    "교독문": "교독문", "교독": "교독문", "환영": "환영", "새가족환영": "환영", "파송": "파송", "간증": "간증", "선교보고": "선교 보고",
    "예배인도": None, "인도": None, "사회": None, "사회자": None, "반주": None, "봉헌기도": None, "헌금기도": None, "헌금위원": None,
}
SHOW = {"찬양과경배": "찬양과 경배", "찬양과결단": "찬양과 결단"}

TAILS = ("담임목사|원로목사|부목사|목사|강도사|전도사|선교사|원로장로|시무장로|장로|은퇴권사|권사|안수집사|서리집사|집사|성도|"
         "형제|자매|청년|학생|어린이|어린이부|중고등부|청년부|청년회|가정|부부|교사|간사|사모|중창단|찬양팀|찬양대|성가대|합창단|워십팀|팀")
GROUP = r"(?:다같이|다함께|모두|회중|일동|인도자|사회자|찬양대|성가대|찬양팀|중창단|온성도|전교인|담임목사)"
WHO = re.compile(rf"^(?:[가-힣A-Za-z&·, ]{{1,24}}?\s*(?:{TAILS})|(?:담임목사|부목사|목사|장로|권사|집사|전도사)\s*[가-힣]{{2,4}}|{GROUP})$")
BOOKS = ("창세기|출애굽기|레위기|민수기|신명기|여호수아|사사기|룻기|사무엘상|사무엘하|열왕기상|열왕기하|역대상|역대하|에스라|느헤미야|에스더|욥기|"
         "시편|잠언|전도서|아가|이사야|예레미야애가|예레미야|에스겔|다니엘|호세아|요엘|아모스|오바댜|요나|미가|나훔|하박국|스바냐|학개|스가랴|말라기|"
         "마태복음|마가복음|누가복음|요한복음|사도행전|로마서|고린도전서|고린도후서|갈라디아서|에베소서|빌립보서|골로새서|데살로니가전서|데살로니가후서|"
         "디모데전서|디모데후서|디도서|빌레몬서|히브리서|야고보서|베드로전서|베드로후서|요한일서|요한이서|요한삼서|유다서|요한계시록|"
         "삼상|삼하|왕상|왕하|대상|대하|고전|고후|살전|살후|딤전|딤후|벧전|벧후|요일|요이|요삼|"
         "창|출|레|민|신|수|삿|룻|스|느|에|욥|시|잠|전|아|사|렘|애|겔|단|호|욜|암|옵|욘|미|나|합|습|학|슥|말|마|막|눅|요|행|롬|갈|엡|빌|골|딛|몬|히|약|유|계")
REF = re.compile(rf"({BOOKS})\s*(\d{{1,3}})\s*(?:[:：]\s*\d{{1,3}}(?:\s*[-~–]\s*\d{{1,3}}(?:\s*[:：]\s*\d{{1,3}})?)?|장(?:\s*\d{{1,3}}\s*(?:[-~–]\s*\d{{1,3}})?\s*절)?|편)")
HYMN = re.compile(r"(?:새\s*)?(?:찬송가?|찬)\s*\d{1,3}\s*장|^\s*\d{1,3}\s*장")
QUOTE = re.compile(r"[「『“\"']\s*(.+?)\s*[」』”\"']")
LEADER = re.compile(r"\s*(?:[·•∙⋅.]{2,}|…+|─+|-{3,}|_{3,}|\t|\s{3,})\s*")


def nospace(t: str) -> str:
    return re.sub(r"\s", "", t or "")


def clean(x: str) -> str:
    x = html.unescape(re.sub(r"\s*<br\s*/?>\s*", " ", x or "", flags=re.I))
    x = re.sub(r"<[^>]+>", "", x)
    return re.sub(r"\s+", " ", x).strip()


def fix_who(x: str) -> str:
    """맡은 분 띄어쓰기 — PDF 빈칸(「정영선 목 사」「올 랴 선교사」)·붙은 글(「김용준안수집사부부」)을 「이름 직분」으로."""
    x = clean(x)
    if nospace(x) in TAILS.split("|") or re.fullmatch(GROUP, nospace(x)): return nospace(x)   # 「담임목사」「다 같 이」 그대로
    if re.search(r"(?:^|\s)[가-힣](?:\s|$)", x): x = nospace(x)         # 한 글자 조각이 있으면 PDF 빈칸 → 붙인다
    m = re.fullmatch(r"(담임목사|원로목사|부목사|목사|장로|권사|집사|전도사)\s*([가-힣]{2,4})", x)
    if m: return f"{m.group(1)} {m.group(2)}"                          # 직분 + 이름(담임목사 홍길동)
    if " " not in x: x = re.sub(rf"^([가-힣]{{2,4}}?)({TAILS})", r"\1 \2", x)   # 이름에 붙은 직분
    x = re.sub(rf"(?<=[가-힣])({TAILS})$", r" \1", x) if not re.search(rf"(?:^|\s)({TAILS})$", x) else x   # 끝에 붙은 직분(부부·가정)
    return re.sub(r"\s+", " ", x).strip()


def name_of(cell: str) -> str | None | bool:
    """순서 이름 → PPT 순서 이름(모르면 False, 뺄 것이면 None)."""
    k = nospace(clean(cell))
    k = re.sub(r"^[\d①-⑳⓵-⓾.)\s]+", "", k)                              # 번호 「1.」「①」
    k = re.sub(r"[(（\[].*$", "", k)                                    # 「설교(말씀)」
    return NAMES.get(k, False)


def split_line(line: str) -> list[str]:
    """표 밖 글줄 한 줄 → 칸. 「기 도 ······ 이순자 권사」, 「말씀  「빛의 자녀」 (엡 5:8-14)  담임목사」."""
    line = clean(line)
    if not line: return []
    ns = nospace(line)
    for k in sorted((k for k in NAMES), key=len, reverse=True):          # 순서 이름이 줄 앞에(빈칸이 끼어도)
        if ns.startswith(k) and (len(ns) == len(k) or not re.match(r"[가-힣]", ns[len(k)]) or LEADER.match(line[1:]) or True):
            cut, n = 0, 0
            for i, ch in enumerate(line):
                if not ch.isspace(): n += 1
                if n == len(k): cut = i + 1; break
            head, rest = line[:cut], line[cut:]
            if rest and re.match(r"[가-힣]", rest) and not rest.startswith(" "): continue   # 「말씀암송」을 「말씀」으로 자르지 않게
            cells = [head] + [c for c in LEADER.split(rest) if c.strip()]
            if len(cells) == 2 and not _who_like(cells[1]):                                          # 「기도 이순자 권사」처럼 빈칸 하나로만 이어지면 끝의 맡은 분을 떼어 본다
                m = re.match(rf"^(.*?)\s*((?:[가-힣]{{2,4}}\s*(?:{TAILS}))|{GROUP})$", cells[1])
                if m and m.group(1).strip(): cells = [head, m.group(1), m.group(2)]
            return cells
    return [c for c in LEADER.split(line) if c.strip()]


def rows_of(md: str) -> list[list[str]]:
    """kordoc 글 → 줄(칸 목록). 표 안의 표도 줄로 편다."""
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", md, re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if any("<table" in c for c in cells): continue                   # 바깥 표 줄(안쪽 줄이 따로 잡힌다)
        out.append([c.strip() for c in cells])
    text = re.sub(r"<table>.*?</table>", "\n", md, flags=re.S)
    for ln in text.split("\n"):
        h = clean(ln.lstrip("#").strip())
        if not ln.strip().startswith("|") and re.search(r"예배|집회|모임", h) and len(nospace(h)) <= 24 and not name_of(split_line(h)[0] if split_line(h) else ""):
            out.append(["__예배__"]); continue                            # 「오후 예배 (14:00)」「2부 예배」 머리줄 — 순서표를 끊는다(2)
        if ln.strip().startswith("|"):                                   # 마크다운 표 줄 「| 기도 | 김철수 장로 |」
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells and not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c): out.append(cells)
            continue
        c = split_line(ln)
        if c: out.append(c)
    return out


def _who_like(c: str) -> bool:
    c2 = clean(c)
    if nospace(c2) in NAMES: return False                                # 「사도신경」처럼 내용 칸에 적힌 순서 이름
    return bool(WHO.match(nospace(c2)) or WHO.match(c2)) or bool(re.fullmatch(r"[가-힣]{2,4}", nospace(c2)) and len(nospace(c2)) <= 4)


def read_row(cells: list[str]) -> dict:
    """한 줄의 나머지 칸 → who·ref·title·hymn (3)."""
    got: dict = {}
    for c in cells:
        t = clean(c)
        if not t or t in (".", "-", "·"): continue
        m = REF.search(t)
        if m and "ref" not in got:
            got["ref"] = clean(m.group(0))
            rest = clean(t.replace(m.group(0), "").strip(" ()（）[]"))
            q = QUOTE.search(rest)
            if q: got.setdefault("title", q.group(1))
            elif rest and not _who_like(rest) and len(nospace(rest)) > 1: got.setdefault("text", rest)
            continue
        if HYMN.search(t): got.setdefault("hymn", clean(HYMN.search(t).group(0))); continue
        if "who" not in got and _who_like(t): got["who"] = fix_who(t); continue
        q = QUOTE.search(t)
        if q: got.setdefault("title", q.group(1)); continue
        got.setdefault("text", t)
    return got


def find_block(rows: list[list[str]]) -> list[list[str]]:
    """순서표 찾기 (2) — 순서 이름 줄이 모인 곳 중 가장 많은 곳."""
    hits = [i for i, r in enumerate(rows) if r and name_of(r[0]) not in (False,)]
    blocks, cur = [], []
    brk = [i for i, r in enumerate(rows) if r == ["__예배__"]]
    for i in hits:
        if cur and (i - cur[-1] > 4 or any(cur[-1] < b < i for b in brk)): blocks.append(cur); cur = []
        cur.append(i)
    if cur: blocks.append(cur)
    blocks = [b for b in blocks if sum(1 for i in b if name_of(rows[i][0])) >= 3]
    if not blocks: return []
    b = max(blocks, key=lambda b: (sum(1 for i in b if name_of(rows[i][0])), -b[0]))
    out = []
    for i in range(b[0], b[-1] + 1):
        r = rows[i]
        if not r: continue
        n = name_of(r[0])
        if n is False:                                                   # 사이에 낀 모르는 짧은 이름(환영·파송 등)
            k = nospace(clean(r[0]))
            if not (1 < len(k) <= 6 and re.fullmatch(r"[가-힣]+", k) and len(r) > 1): continue
        out.append(r)
    return out


def items_from_rows(rows: list[list[str]]) -> list[dict]:
    """순서표 줄 → 예배순서 줄(이름 맞추기 4, 칸 가르기 3)."""
    out, after_sermon, after_reading = [], False, False
    for r in rows:
        n = name_of(r[0])
        if n is None: continue
        if n is False: n = nospace(clean(r[0]))
        g = read_row(r[1:])
        if n == "찬양":
            single = g.get("who") and not re.fullmatch(GROUP, nospace(g["who"]))
            n = "찬양과결단" if after_sermon else ("특송" if after_reading and single else "찬양과경배")
        if n == "설교": after_sermon = True
        if n == "성경봉독": after_reading = True
        it = {"t": SHOW.get(n, n)}
        if g.get("who"): it["who"] = g["who"]
        if n == "성경봉독" and g.get("ref"): it["ref"] = g["ref"]
        if n == "설교":
            if g.get("title") or g.get("text"): it["title"] = g.get("title") or g["text"]
            if g.get("ref"): it["_ref"] = g["ref"]                        # 봉독 줄에 본문이 없으면 쓴다(5)
        out.append(it)
    sref = next((x.pop("_ref") for x in out if "_ref" in x), "")
    for x in out: x.pop("_ref", None)
    if sref:
        for x in out:
            if x["t"] == "성경봉독" and not x.get("ref"): x["ref"] = sref
    return out


def word(md: str) -> tuple[str, str]:
    """오늘의 말씀(5) — 「오늘의 말씀/설교/말씀」 머리 아래 「제목」「(책 장:절)」."""
    t = clean(md.replace("</td>", "\n").replace("</th>", "\n").replace("<br>", "\n"))
    t = re.sub(r"<[^>]+>", "\n", md.replace("<br>", "\n"))
    lines = [clean(x) for x in t.split("\n") if clean(x)]
    for i, ln in enumerate(lines):
        if re.fullmatch(r"(?:오늘의\s*말씀|설교\s*말씀|설교\s*요약|설교|말씀|오늘의\s*설교)", ln):
            nxt = lines[i + 1:i + 4]
            for j, x in enumerate(nxt):
                m = REF.search(x)
                if m:
                    title = clean(x.replace(m.group(0), "").strip(" ()（）")) or (nxt[j - 1] if j else "")
                    q = QUOTE.search(title)
                    return (q.group(1) if q else title)[:60], clean(m.group(0))
    return "", ""


def verify(items: list[dict], md: str) -> list[dict]:
    """원문 대조(6) — 빈칸을 뺀 원문 안에 없는 값은 버린다."""
    src = re.sub(r"[|\-]{1,}", "", nospace(clean(re.sub(r"<[^>]+>", " ", md.replace("<br>", " ")))))   # 표 칸 가름(|·---)은 빼고 대조
    src = src.replace("-", "")
    out = []
    for x in items:
        y = {"t": x["t"]}
        for f in ("who", "title", "ref"):
            if x.get(f) and nospace(x[f]).replace("-", "") in src: y[f] = x[f]
        out.append(y)
    return out


def fragmented(rows: list[list[str]]) -> bool:
    """PDF 에서 글자가 칸 사이로 쪼개진 순서표(「오세|훈집사」「다함|께」) — 규칙으로는 띄어쓰기를 되살릴 수 없다."""
    for r in rows:
        cs = [clean(c) for c in r[1:] if clean(c)]
        for a, b in zip(cs, cs[1:]):
            if re.fullmatch(r"[가-힣]{1,2}", a) and re.match(r"[가-힣]", b) and not re.fullmatch(GROUP, a): return True
    return False


def read(md: str, ask=None) -> tuple[list[dict], dict]:
    """주보 글 → (예배순서 줄, 읽은 방법).
    규칙으로 충분하면(순서 4개 이상·설교 있음·칸이 쪼개지지 않음) 규칙만. 아니면 Claude 에게 같은 규칙으로 묻고,
    칸이 쪼개진 주보는 Claude 값을 먼저(띄어쓰기를 살림), 아니면 규칙 값을 먼저 쓴다. 어느 쪽이든 원문 대조(6)."""
    rows = find_block(rows_of(md))
    items = items_from_rows(rows)
    frag = fragmented(rows)
    how = {"by": "rules", "rows": len(rows), "fragmented": frag}
    if frag or len(items) < 4 or not any(x["t"] == "설교" for x in items):
        try:
            got = (ask or ask_claude)(md)
            if got:
                items = merge_rules(got, items, prefer_llm=frag or len(items) < 4); how["by"] = "claude+rules"
        except Exception as e:
            how["claude_error"] = str(e)[:200]
    t, r = word(md)
    for x in items:
        if x["t"] == "설교" and t and not x.get("title"): x["title"] = t
        if x["t"] == "성경봉독" and r and not x.get("ref"): x["ref"] = r
    return verify(items, md), how


def merge_rules(llm: list[dict], rules: list[dict], prefer_llm: bool = False) -> list[dict]:
    """순서는 Claude 가 읽은 것. 값은 규칙 값을 먼저(prefer_llm 이면 Claude 값을 먼저) 쓰고 빈 칸은 다른 쪽으로 채운다."""
    by = {}
    for x in rules: by.setdefault(x["t"], x)
    out = []
    for x in llm:
        y = dict(x); r = by.get(x["t"], {})
        for f in ("who", "title", "ref"):
            if r.get(f) and (not prefer_llm or not y.get(f)): y[f] = r[f]
        out.append(y)
    return out


PROMPT = """아래는 어느 교회 주보 PDF 에서 뽑은 글입니다. 이 주보의 (주일 낮) 예배순서를 JSON 으로만 답하세요. 설명 글은 쓰지 마세요.

규칙
- 예배가 여럿이면(1부·2부·오후·수요) 주일 낮(1부) 예배 하나만.
- 순서마다 {{"name": 주보에 적힌 순서 이름 그대로, "who": 맡은 분, "title": 설교 제목(설교만), "ref": 성경 본문(성경봉독·설교만)}}.
- 값은 주보에 적힌 글자를 그대로 옮기고, 주보에 없으면 빈 글자("")로. 짐작해서 채우지 마세요.
- 찬송 번호(000장)·곡 이름은 넣지 마세요. 예배인도·사회·반주·헌금위원 줄은 빼세요.
- 맡은 분은 이름과 직분(예: "홍길동 장로", "담임목사", "다같이").

답 꼴: {{"order": [{{"name": "...", "who": "...", "title": "", "ref": ""}}]}}

주보 글:
{text}
"""


def ask_claude(md: str) -> list[dict]:
    """규칙으로 덜 읽힌 주보 — 맥미니 claude -p(구독)로 읽는다. API 키는 넘기지 않는다."""
    text = clean(re.sub(r"<[^>]+>", "\n", md.replace("<br>", "\n")))[:14000]
    text = "\n".join(x.strip() for x in re.sub(r"<[^>]+>", "\n", md.replace("<br>", "\n")).split("\n") if x.strip())[:14000]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) and k != "CLAUDE_CODE_OAUTH_TOKEN"}
    r = subprocess.run([str(Path.home() / ".local/bin/claude"), "-p", PROMPT.format(text=text), "--output-format", "text"],
                       capture_output=True, text=True, timeout=300, env=env, cwd=tempfile.gettempdir())
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if not m: raise RuntimeError(f"JSON 을 못 받음: {(r.stdout or r.stderr)[:200]}")
    return from_llm(json.loads(m.group(0)).get("order", []))


def from_llm(order: list[dict]) -> list[dict]:
    """Claude 답 → 예배순서 줄(이름 맞추기·찬양 자리 가르기는 규칙과 같게)."""
    rows = [[o.get("name", ""), o.get("who", ""), o.get("ref", ""), o.get("title", "")] for o in order if o.get("name")]
    items = items_from_rows([r if name_of(r[0]) is not False else r for r in rows])
    for it, o in zip([x for x in items], [o for o in order if o.get("name") and name_of(o["name"]) is not None]):
        if it["t"] == "설교" and o.get("title"): it["title"] = clean(o["title"])
        if it["t"] in ("성경봉독",) and o.get("ref"): it["ref"] = clean(o["ref"])
    return items
