#!/usr/bin/env python3
"""주보 HWP → 예배 콘티 추천 (제곡교회 주일 찬양예배).

교장님이 주보 HWP 를 올리면:
  1) 예배 날짜 확인(파일명 20260920… 또는 다음 주일) → 그 주일 폴더(prep.py 규칙) 찾기/생성
  2) HWP 를 폴더에 `YYYYMMDD 주일 주보.hwp` 로 저장, PDF 도 함께 저장
       - PDF 를 같이 주면(--pdf) 그대로, 없으면 hwp5html+크롬으로 자동 변환(레이아웃 근사, 이름에 표시)
  3) 본문 읽기(kordoc → Markdown) → 설교 제목·성경 본문·설교 요약 추출
  4) Claude(장기 토큰) 가 교회 레퍼토리(콘티 기록 문서 285곡·코드)를 우선으로
       CCM 20곡(빠른 6·중간 8·느린 6) + 찬송가 10곡(빠른 3·중간 4·느린 3) 을 설교 주제에 맞춰 추천
  5) 곡마다 yt-dlp 로 유튜브 링크 확보 → 지정 형식으로 출력, 폴더에 `YYYYMMDD 콘티 추천` 구글문서로도 저장
  6) --notify 면 텔레그램(경진비서방)에 발송

사용:  python3 conti.py 주보.hwp|주보.pdf [--pdf 주보.pdf] [--date 2026-09-20] [--leader 이경진] [--dry-run] [--notify]
       --dry-run : 드라이브 업로드·텔레그램 없이 변환+추천만 (out/ 에 결과)
       --no-youtube : 링크 검색 생략(빠른 확인용)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prep  # noqa: E402  — 날짜·폴더·구글 API 재사용

sys.path.insert(0, str(Path.home() / "dev" / "next_api_bot" / "worker"))
try:
    import bible_lookup  # noqa: E402  — 개역개정 본문(worker/data/bible_krv.json). 없으면 본문 없이 진행
except Exception:  # noqa: BLE001
    bible_lookup = None

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
VENV = HERE.parent / ".venv"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CLAUDE_BOT = os.path.expanduser("~/bin/claude-bot")
REPERTOIRE_DOC = "1nF0M6jVozi02m8alxC1pel-H7LWazpHPM-gcW_xLiqg"   # 콘티 기록 2026 2025 2024 (구글 문서)
REPERTOIRE_JSON = HERE / "repertoire.json"
DIST_CCM = {"빠른곡": 6, "중간곡": 8, "느린곡": 6}
DIST_HYMN = {"빠른곡": 3, "중간곡": 4, "느린곡": 3}
TEMPOS = ["빠른곡", "중간곡", "느린곡"]
HWP_MIME = "application/x-hwp"
PDF_MIME = "application/pdf"


def log(msg: str) -> None:
    print(msg, flush=True)


# ── 날짜 ─────────────────────────────────────────────────────
def date_from_filename(name: str) -> date | None:
    m = re.search(r"(20\d{2})[ ._-]?(\d{2})[ ._-]?(\d{2})", Path(name).stem)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ── 변환·추출 ────────────────────────────────────────────────
def hwp_to_markdown(hwp: Path, workdir: Path) -> str:
    """HWP·HWPX·PDF 무엇이든 kordoc 이 Markdown 으로 (이름은 역사적 이유로 hwp_)."""
    out = workdir / "jubo.md"
    r = subprocess.run(["npx", "-y", "kordoc@^4", str(hwp), "-o", str(out)], capture_output=True, text=True, timeout=600)
    if not out.exists():
        raise RuntimeError(f"kordoc 변환 실패: {(r.stderr or r.stdout)[-300:]}")
    return out.read_text(encoding="utf-8", errors="replace")


def hwp_to_pdf(hwp: Path, pdf: Path) -> Path:
    """hwp5html → xhtml → 크롬 print-to-pdf. 레이아웃은 근사(원본 편집 프로그램의 PDF 가 더 정확)."""
    hwp5html = VENV / "bin" / "hwp5html"
    if not hwp5html.exists():
        raise RuntimeError(f"hwp5html 없음 — {VENV} 에 `pip install -r worship/requirements-hwp.txt`")
    html_dir = pdf.parent / (pdf.stem + "_html")
    shutil.rmtree(html_dir, ignore_errors=True)
    subprocess.run([str(hwp5html), str(hwp), "--output", str(html_dir)], capture_output=True, text=True, timeout=300)
    index = html_dir / "index.xhtml"
    if not index.exists():
        raise RuntimeError("hwp5html 출력 없음")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", index.as_uri()],
                   capture_output=True, text=True, timeout=180)
    if not pdf.exists() or pdf.stat().st_size < 10_000:
        raise RuntimeError("PDF 생성 실패")
    shutil.rmtree(html_dir, ignore_errors=True)
    return pdf


def _plain(md: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", "\n", md)
    text = re.sub(r"</t[dh]>", " | ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return [re.sub(r"\s+", " ", l).strip(" |") for l in text.splitlines()]


def parse_sermon(md: str) -> dict:
    """주보 Markdown → {title, scripture, summary, points}. '오늘의 말씀' 절을 기준으로 읽는다."""
    lines = [l for l in _plain(md) if l]
    title = scripture = ""
    # 순서표의 '설교' 행: 설교 | 정영선 목사 | ... | 귀향(歸鄕) 공동체
    for l in lines:
        if l.startswith("설교"):
            cells = [c.strip() for c in l.split("|") if c.strip()]
            if len(cells) >= 3:
                title = cells[-1]
            break
    summary: list[str] = []
    if "오늘의 말씀" in lines:
        i = lines.index("오늘의 말씀") + 1
        block = []
        while i < len(lines) and not re.match(r"^(샘터모임|교회소식|광고|알림|①)", lines[i]):
            block.append(lines[i]); i += 1
        if block:
            if not title:
                title = block[0]
            for b in block[:3]:
                m = re.match(r"^\(?([가-힣]+\s*\d+(?::\d+(?:-\d+)?)?(?:[,;]\s*\d+(?::\d+)?(?:-\d+)?)*)\)?$", b)
                if m:
                    scripture = m.group(1); break
            summary = [b for b in block if b != title and b.strip("()") != scripture]
    points = [s for s in summary if re.match(r"^(첫째|둘째|셋째|넷째|다섯째|\d\.|[①②③④⑤])", s)]
    return {"title": title, "scripture": scripture, "summary": "\n".join(summary), "points": points}


# ── 레퍼토리 ─────────────────────────────────────────────────
SONG_RE = re.compile(r"^\*\s*(.+?)\s+([A-G](?:b|#)?m?(?:\s*→\s*[A-G](?:b|#)?m?)?)\s*(\(.+\))?\s*$")


def parse_repertoire(text: str) -> dict:
    """콘티 기록 문서(텍스트) → {곡: {count, keys{코드:횟수}, alt[]}}."""
    songs: dict = {}
    for raw in text.splitlines():
        m = SONG_RE.match(raw.strip())
        if not m:
            continue
        title, key, alt = m.group(1).strip(), m.group(2).replace(" ", ""), m.group(3)
        base = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
        e = songs.setdefault(base, {"count": 0, "keys": {}, "alt": []})
        e["count"] += 1
        e["keys"][key] = e["keys"].get(key, 0) + 1
        for a in re.findall(r"\(([^)]+)\)", title) + ([alt.strip("()")] if alt else []):
            if a not in e["alt"]:
                e["alt"].append(a)
    return dict(sorted(songs.items(), key=lambda kv: -kv[1]["count"]))


def refresh_repertoire(g: prep.G | None) -> dict:
    """가능하면 구글 문서를 다시 읽어 최신화, 실패하면 저장된 JSON."""
    if g:
        try:
            raw = g.req("GET", f"{prep.DRIVE}/files/{REPERTOIRE_DOC}/export?mimeType=text/plain&supportsAllDrives=true")
            rep = parse_repertoire(raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw))
            if len(rep) > 50:
                REPERTOIRE_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
                return rep
        except Exception as e:  # noqa: BLE001
            log(f"레퍼토리 갱신 실패(저장본 사용): {e}")
    try:
        return json.loads(REPERTOIRE_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def main_key(entry: dict) -> str:
    keys = entry.get("keys") or {}
    return max(keys, key=keys.get) if keys else ""


# ── Claude 추천 ──────────────────────────────────────────────
PROMPT = """너는 한국 교회 찬양 인도자를 돕는 예배 기획자다. 아래 설교 정보에 맞는 주일 찬양 콘티 후보를 고른다.

[설교]
제목: {title}
본문: {scripture}
요약:
{summary}

[이 교회가 자주 부르는 곡 — 제목 [주 코드] (부른 횟수)]  ※ 이 목록을 최우선으로 고르고, 부족하면 널리 불리는 CCM 을 추가한다
{repertoire}

규칙
- CCM 정확히 20곡: 빠른곡 6 · 중간곡 8 · 느린곡 6.
- 찬송가(새찬송가)는 **후보 18곡**: 빠른곡 7 · 중간곡 6 · 느린곡 5 (장수는 유튜브 제목으로 우리가 검증해 3·4·3 으로 고르니 넉넉히).
- 설교 주제(위 요약의 핵심 메시지·본문 정서)와 부합하는 곡만. 도입-메인-적용 흐름에 쓸 수 있게 고른다.
- 코드(key)는 목록에 있는 곡은 목록의 코드, 없는 곡은 일반적으로 부르는 코드(예: G, A, D, E, C, F, Bb).
- 찬송가는 새찬송가 장수(no)와 첫 줄 제목을 적는다. 장수가 조금 불확실해도 후보로 넣는다(검증은 우리가 한다).
- 존재하지 않는 곡을 지어내지 않는다. 각 곡에 유튜브 검색어(search)를 붙인다: 곡 제목 + 대표 아티스트/찬양팀 이름(알면).
도구는 쓰지 말고 아는 지식으로 바로 답한다. 출력은 JSON 하나만 (설명·코드펜스 없이, 첫 글자가 {{):
{{"theme":"한 줄 주제","ccm":[{{"title":"…","key":"G","tempo":"빠른곡|중간곡|느린곡","search":"…","why":"10자 내"}}],
 "hymns":[{{"no":305,"title":"…","key":"G","tempo":"…","search":"새찬송가 305장 …"}}]}}"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def recommend(sermon: dict, repertoire: dict, timeout: int = 300) -> dict:
    rep_lines = [f"{t} [{main_key(e)}] ({e['count']})" for t, e in list(repertoire.items())[:220]]
    prompt = PROMPT.format(title=sermon["title"] or "(제목 미확인)", scripture=sermon["scripture"] or "(본문 미확인)",
                           summary=(sermon["summary"] or "(요약 없음)")[:3000], repertoire="\n".join(rep_lines) or "(없음)")
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
    OUT.mkdir(exist_ok=True)
    last = ""
    for attempt in (1, 2):
        p = prompt if attempt == 1 else prompt + "\n\n(직전 응답이 JSON 이 아니었다. 이번엔 반드시 { 로 시작하는 JSON 객체 하나만 출력한다.)"
        r = subprocess.run([CLAUDE_BOT, "-p", p, "--output-format", "text", "--tools", "", "--no-session-persistence"],
                           capture_output=True, text=True, timeout=timeout, env=env, cwd=tempfile.gettempdir())
        (OUT / f"claude_raw_{attempt}.txt").write_text(f"rc={r.returncode}\n--stdout--\n{r.stdout}\n--stderr--\n{r.stderr}", encoding="utf-8")
        if r.returncode != 0:
            raise RuntimeError(f"Claude 실패 rc={r.returncode}: {r.stderr.strip()[:200]}")
        last = r.stdout
        try:
            return normalize(_extract_json(r.stdout))
        except (json.JSONDecodeError, ValueError) as e:
            log(f"   Claude 응답이 JSON 이 아님(시도 {attempt}): {e} — 앞부분: {r.stdout.strip()[:120]!r}")
    raise RuntimeError(f"Claude 가 JSON 을 주지 않음 (out/claude_raw_*.txt 참고). 마지막 응답: {last.strip()[:150]!r}")


def normalize(data: dict) -> dict:
    """tempo 표기 정리 + 개수 검증(부족하면 그대로 두고 카운트를 보고)."""
    def fix(items, dist):
        out = []
        for it in items or []:
            t = str(it.get("tempo", "")).strip()
            t = {"빠름": "빠른곡", "빠른": "빠른곡", "fast": "빠른곡", "중간": "중간곡", "medium": "중간곡", "보통": "중간곡",
                 "느림": "느린곡", "느린": "느린곡", "slow": "느린곡"}.get(t.lower() if t.isascii() else t, t)
            if t not in TEMPOS:
                continue
            it = {**it, "tempo": t, "title": str(it.get("title", "")).strip(), "key": str(it.get("key", "")).strip().replace("코드", "")}
            if it["title"]:
                out.append(it)
        # 정원 초과분은 잘라낸다
        kept, seen = [], {t: 0 for t in TEMPOS}
        for it in out:
            if seen[it["tempo"]] < dist[it["tempo"]]:
                kept.append(it); seen[it["tempo"]] += 1
        return kept, seen
    ccm, c_seen = fix(data.get("ccm"), DIST_CCM)
    hymns, h_seen = fix(data.get("hymns"), {t: 99 for t in TEMPOS})   # 후보는 전부 보관 → verify_hymns 뒤 trim
    return {"theme": data.get("theme", ""), "ccm": ccm, "hymns": hymns, "counts": {"ccm": c_seen, "hymns": h_seen},
            "short": {k: DIST_CCM[k] - c_seen[k] for k in TEMPOS if c_seen[k] < DIST_CCM[k]}}


def trim(items: list[dict], dist: dict) -> tuple[list[dict], dict]:
    """정원(dist)대로 템포별로 자른다. dist 에 없는 템포는 정원 0 (부분 정원으로 호출돼도 안전)."""
    kept, seen = [], {t: 0 for t in TEMPOS}
    for it in items:
        if seen[it["tempo"]] < dist.get(it["tempo"], 0):
            kept.append(it); seen[it["tempo"]] += 1
    return kept, {k: dist.get(k, 0) - seen[k] for k in TEMPOS if seen[k] < dist.get(k, 0)}


def _tokens(title: str) -> list[str]:
    return [w for w in re.sub(r"[^\w가-힣 ]", " ", title).split() if len(w) >= 2]


def verify_hymns(hymns: list[dict], workers: int = 5) -> list[dict]:
    """새찬송가 장수 검증: 유튜브 '새찬송가 N장' 검색 제목에 N 과 제목 낱말이 함께 나오면 통과 + 그 영상 링크 사용."""
    def one(h):
        no = h.get("no")
        if not no:
            return None
        try:
            rows = yt_search(f"새찬송가 {no}장 {h['title']}", n=4)
        except Exception:  # noqa: BLE001
            return None
        toks = _tokens(h["title"])
        for r in rows:
            t = r["title"].replace(" ", "")
            if re.search(rf"(?<!\d){int(no)}(?!\d)", r["title"]) and sum(1 for w in toks if w.replace(" ", "") in t) >= max(1, min(2, len(toks))):
                return {**h, "url": r["url"], "verified": True}
        return None
    with cf.ThreadPoolExecutor(workers) as ex:
        out = [v for v in ex.map(one, hymns) if v]
    return out


# ── 유튜브 ───────────────────────────────────────────────────
def yt_search(query: str, n: int = 3, timeout: int = 40) -> list[dict]:
    r = subprocess.run(["yt-dlp", "--flat-playlist", "--no-warnings", "--print", "%(title)s\t%(webpage_url)s\t%(duration)s", f"ytsearch{n}:{query}"],
                       capture_output=True, text=True, timeout=timeout)
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                dur = float(parts[2]) if len(parts) > 2 and parts[2] not in ("NA", "") else 0
            except ValueError:
                dur = 0
            rows.append({"title": parts[0], "url": parts[1], "duration": dur})
    return rows


def pick_video(rows: list[dict]) -> str:
    """2~9분짜리(전곡 연주·라이브)를 우선, 없으면 첫 결과."""
    for r in rows:
        if 110 <= r["duration"] <= 560:
            return r["url"]
    return rows[0]["url"] if rows else ""


def attach_links(rec: dict, workers: int = 5) -> dict:
    items = [it for it in rec["ccm"] + rec["hymns"] if not it.get("url")]
    def one(it):
        q = it.get("search") or (f"새찬송가 {it.get('no')}장 {it['title']}" if "no" in it else f"{it['title']} 찬양")
        try:
            return pick_video(yt_search(q))
        except Exception:  # noqa: BLE001
            return ""
    with cf.ThreadPoolExecutor(workers) as ex:
        for it, url in zip(items, ex.map(one, items)):
            it["url"] = url
    return rec


# ── 출력 ─────────────────────────────────────────────────────
def format_text(d: date, sermon: dict, rec: dict) -> str:
    wd = "월화수목금토일"[d.weekday()]
    head = [f"🎵 {d.month}/{d.day}({wd}) 주일예배 콘티 추천", f"설교 「{sermon['title'] or '-'}」 ({sermon['scripture'] or '본문 미확인'})"]
    if rec.get("theme"):
        head.append(f"주제: {rec['theme']}")
    def block(items, label):
        out = [f"\n[{label}]"]
        for t in TEMPOS:
            rows = [it for it in items if it["tempo"] == t]
            out.append(f"\n<{t}>")
            for i, it in enumerate(rows, 1):
                no = f"{it['no']}장 " if it.get("no") else ""
                key = f" {it['key']}코드" if it.get("key") else ""
                url = f" {it['url']}" if it.get("url") else " (링크 못 찾음)"
                out.append(f"{i}. {no}{it['title']}{key}{url}\n   악보: {sheet_url(it)}")
        return out
    lines = head + block(rec["ccm"], f"CCM {len(rec['ccm'])}곡") + block(rec["hymns"], f"찬송가 {len(rec['hymns'])}곡")
    if rec.get("short"):
        lines.append("\n※ 정원 미달: " + ", ".join(f"{k} {v}곡" for k, v in rec["short"].items()))
    return "\n".join(lines).strip()


def _h(s: str) -> str:
    return html.escape(str(s), quote=True)


def sheet_url(it: dict) -> str:
    """구글 이미지 검색 '곡명 악보' (찬송가는 '새찬송가 N장 곡명 악보')."""
    q = (f"새찬송가 {it['no']}장 " if it.get("no") else "") + f"{it['title']} 악보"
    return "https://www.google.com/search?tbm=isch&q=" + urllib.parse.quote_plus(q)


def scripture_text(ref: str) -> str:
    """주보에서 읽은 본문 표기('역대상 9:1-44') → 개역개정 본문(머리글 + '절   본문' 줄). 못 찾으면 빈 문자열."""
    if not ref or bible_lookup is None:
        return ""
    try:
        return bible_lookup.render(ref) or ""
    except Exception:  # noqa: BLE001
        return ""


def format_html(d: date, sermon: dict, rec: dict, folder_link: str = "", with_scripture: bool = False) -> str:
    """제목에 링크를 심은 HTML (텔레그램 parse_mode=HTML 과 구글문서 변환 공용). 한 줄 = 한 곡.
    with_scripture=True(구글문서용)면 맨 위에 주보에서 파악한 성경 본문을 그대로 적는다(2026-09-19 지시)."""
    wd = "월화수목금토일"[d.weekday()]
    out = [f"🎵 <b>{d.month}/{d.day}({wd}) 주일예배 콘티 추천</b>",
           f"설교 「{_h(sermon.get('title') or '-')}」 ({_h(sermon.get('scripture') or '본문 미확인')})"]
    if with_scripture:
        body = scripture_text(sermon.get("scripture") or "")
        if body:
            head, _, verses_ = body.partition("\n")
            out += ["", f"📖 <b>{_h(head)}</b>"] + [_h(l) for l in verses_.split("\n")] + [""]
    if rec.get("theme"):
        out.append(f"주제: {_h(rec['theme'])}")
    def block(items, label):
        out.append(f"\n<b>[{label}]</b>")
        for t in TEMPOS:
            rows = [it for it in items if it["tempo"] == t]
            out.append(f"\n&lt;{t}&gt;")
            for i, it in enumerate(rows, 1):
                no = f"{it['no']}장 " if it.get("no") else ""
                name = f"{no}{_h(it['title'])}"
                link = f'<a href="{_h(it["url"])}">{name}</a>' if it.get("url") else f"{name} (링크 못 찾음)"
                key = f" {_h(it['key'])}코드" if it.get("key") else ""
                out.append(f'{i}. {link}{key}, <a href="{_h(sheet_url(it))}">악보</a>')
    block(rec["ccm"], f"CCM {len(rec['ccm'])}곡")
    block(rec["hymns"], f"찬송가 {len(rec['hymns'])}곡")
    if rec.get("short"):
        out.append("\n※ 정원 미달: " + ", ".join(f"{k} {v}곡" for k, v in rec["short"].items()))
    if folder_link:
        out.append(f'\n📁 <a href="{_h(folder_link)}">2026 {d:%m%d} 주일예배 폴더</a>')
    return "\n".join(out).strip()


def html_to_gdoc(html_body: str) -> bytes:
    """텔레그램용 HTML 을 구글문서 변환용 HTML 문서로 (줄바꿈 → <br>)."""
    body = html_body.replace("\n", "<br>\n")
    return f'<html><head><meta charset="utf-8"></head><body style="font-family:sans-serif;line-height:1.6">{body}</body></html>'.encode("utf-8")


def telegram_html(text_html: str) -> bool:
    """parse_mode=HTML 로 발송 (제목 링크). 4096자 제한 → 줄 단위로 나눔. 토큰은 daily-briefing/.env."""
    env = Path.home() / "dev" / "daily-briefing" / ".env"
    tok = None
    try:
        for line in open(env, encoding="utf-8"):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"'); break
    except FileNotFoundError:
        pass
    if not tok:
        log("텔레그램 생략: 토큰 없음"); return False
    chat = os.environ.get("TELEGRAM_NOTIFY_CHAT", "8047286046")
    ok_all = True
    for chunk in telegram_chunks(text_html, 3800):
        data = urllib.parse.urlencode({"chat_id": chat, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=30) as r:
                ok = bool(json.loads(r.read().decode()).get("ok"))
        except urllib.error.HTTPError as e:
            log(f"텔레그램 HTML 실패: {e.code} {e.read().decode(errors='replace')[:200]}"); ok = False
        except Exception as e:  # noqa: BLE001
            log(f"텔레그램 실패: {e}"); ok = False
        ok_all = ok_all and ok
    return ok_all


def replace_gdoc(g: prep.G, file_id: str, html_bytes: bytes) -> dict:
    """기존 구글문서 내용을 HTML 로 교체 (media 업로드 → 구글이 변환)."""
    return g.req("PATCH", f"{prep.UPLOAD}/files/{file_id}?uploadType=media&supportsAllDrives=true&fields=id,name,webViewLink",
                 html_bytes, ctype="text/html", timeout=300)


def telegram_chunks(text: str, limit: int = 3900) -> list[str]:
    chunks, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) + 1 > limit:
            chunks.append(cur); cur = para
        else:
            cur = (cur + "\n" + para) if cur else para
    if cur:
        chunks.append(cur)
    return chunks


# ── 드라이브 저장 ────────────────────────────────────────────
def upload_file(g: prep.G, parent: str, name: str, data: bytes, mime: str, convert_to: str | None = None) -> dict:
    boundary = f"b{uuid.uuid4().hex}"
    meta = {"name": name, "parents": [parent]}
    if convert_to:
        meta["mimeType"] = convert_to
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + json.dumps(meta).encode() +
            f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode() + data + f"\r\n--{boundary}--".encode())
    return g.req("POST", f"{prep.UPLOAD}/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink",
                 body, ctype=f"multipart/related; boundary={boundary}", timeout=600)


def save_to_folder(g: prep.G, folder_id: str, name: str, path: Path | None = None, data: bytes | None = None,
                   mime: str = "application/octet-stream", convert_to: str | None = None) -> dict:
    exists = g.find_child(folder_id, name)
    if exists:
        return {"name": name, "link": exists.get("webViewLink"), "status": "exists"}
    f = upload_file(g, folder_id, name, data if data is not None else path.read_bytes(), mime, convert_to)
    return {"name": name, "link": f.get("webViewLink"), "status": "uploaded"}


# ── 실행 ─────────────────────────────────────────────────────
def run(hwp: Path, pdf: Path | None, d: date, leader: str, dry_run: bool, no_youtube: bool, notify: bool,
        redo: bool = False, from_cache: bool = False) -> int:
    OUT.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="conti-"))
    g = None if dry_run else prep.G(prep.access_token())
    ymd = f"{d:%Y%m%d}"
    cache = OUT / f"{ymd}-conti.json"

    if from_cache and cache.exists():
        c = json.loads(cache.read_text(encoding="utf-8"))
        sermon, rec = c["sermon"], c["rec"]
        log(f"♻️ 직전 추천 재사용: {cache.name} (CCM {len(rec['ccm'])} · 찬송가 {len(rec['hymns'])})")
        return finish(g, d, leader, hwp, pdf, sermon, rec, ymd, dry_run, notify, redo, cached=True)

    log(f"📖 주보 읽기: {hwp.name}")
    md = hwp_to_markdown(hwp, work)
    sermon = parse_sermon(md)
    log(f"   설교 「{sermon['title']}」 {sermon['scripture']} · 요약 {len(sermon['summary'])}자 · 대지 {len(sermon['points'])}개")
    if not sermon["summary"]:
        log("   ⚠️ '오늘의 말씀' 요약을 찾지 못했습니다 — 본문 전체를 요약 대신 사용")
        sermon["summary"] = "\n".join(_plain(md))[:3000]

    pdf_note = ""
    is_pdf_input = hwp.suffix.lower() == ".pdf"
    if is_pdf_input and pdf is None:      # PDF 만 받은 경우: 변환 없이 그 PDF 를 저장
        pdf = hwp
    if pdf is None:
        try:
            pdf = hwp_to_pdf(hwp, work / f"{ymd} 주일 주보.pdf")
            pdf_note = " (자동변환·레이아웃 근사)"
            log(f"   PDF 자동 변환 {pdf.stat().st_size // 1024}KB{pdf_note}")
        except Exception as e:  # noqa: BLE001
            log(f"   PDF 변환 실패: {e}")
            pdf = None

    rep = refresh_repertoire(g)
    log(f"🎼 레퍼토리 {len(rep)}곡 · Claude 추천 요청…")
    rec = recommend(sermon, rep)
    log(f"   CCM {len(rec['ccm'])} · 찬송가 후보 {len(rec['hymns'])}" + (f" · CCM 미달 {rec['short']}" if rec["short"] else ""))
    if not no_youtube:
        log("▶ 찬송가 장수 검증(유튜브 제목)…")
        verified = verify_hymns(rec["hymns"])
        log(f"   검증 통과 {len(verified)}/{len(rec['hymns'])}")
        kept, h_short = trim(verified, DIST_HYMN)
        if h_short:   # 검증 못 한 후보로 채우되 표시를 남긴다 (링크는 제목으로 검색)
            vno = {h.get("no") for h in kept}
            extra = [{**h, "title": h["title"] + " (장수 확인 필요)"} for h in rec["hymns"] if h.get("no") not in vno]
            filler, h_short = trim([h for h in extra if h["tempo"] in h_short], h_short)
            kept += filler
            kept, h_short = trim(kept, DIST_HYMN)
        rec["hymns"] = kept
        if h_short:
            rec["short"] = {**rec["short"], **{f"찬송가 {k}": v for k, v in h_short.items()}}
        log("▶ 유튜브 링크 검색…")
        attach_links(rec)
    else:
        rec["hymns"], _ = trim(rec["hymns"], DIST_HYMN)
        missing = sum(1 for it in rec["ccm"] + rec["hymns"] if not it.get("url"))
        log(f"   링크 {len(rec['ccm']) + len(rec['hymns']) - missing}/{len(rec['ccm']) + len(rec['hymns'])} 확보")
    shutil.rmtree(work, ignore_errors=True)
    return finish(g, d, leader, hwp, pdf, sermon, rec, ymd, dry_run, notify, redo)


def finish(g, d: date, leader: str, hwp: Path, pdf: Path | None, sermon: dict, rec: dict, ymd: str,
           dry_run: bool, notify: bool, redo: bool, cached: bool = False) -> int:
    """형식 만들기 → 드라이브 저장(주보·PDF·콘티 문서) → 텔레그램. (수집·추천 뒤, 또는 --from-cache 에서)"""
    text = format_text(d, sermon, rec)
    (OUT / f"{ymd}-conti.txt").write_text(text, encoding="utf-8")
    if not cached:
        (OUT / f"{ymd}-conti.json").write_text(json.dumps({"sermon": sermon, "rec": rec}, ensure_ascii=False, indent=1), encoding="utf-8")
    is_pdf_input = hwp.suffix.lower() == ".pdf"
    pdf_note = "" if (pdf is None or is_pdf_input or pdf.name.endswith(f"{ymd} 주일 주보.pdf")) else " (자동변환·레이아웃 근사)"

    saved = []
    if g:
        fname = prep.folder_name(d, leader)
        folder = g.find_child(prep.WORK_FOLDER, fname, prep.FOLDER_MIME) or g.create_folder(prep.WORK_FOLDER, fname)
        fid = folder["id"]
        if hwp.exists() and not is_pdf_input:
            saved.append(save_to_folder(g, fid, f"{ymd} 주일 주보{hwp.suffix.lower()}", path=hwp, mime=HWP_MIME))
        if pdf and pdf.exists():
            saved.append(save_to_folder(g, fid, f"{ymd} 주일 주보{pdf_note}.pdf", path=pdf, mime=PDF_MIME))
        folder_link = folder.get("webViewLink") or f"https://drive.google.com/drive/folders/{fid}"
        doc_html = html_to_gdoc(format_html(d, sermon, rec, folder_link, with_scripture=True))   # 문서 맨 위에 성경 본문
        existing = g.find_child(fid, f"{ymd} 콘티 추천")
        if existing and redo:
            r = replace_gdoc(g, existing["id"], doc_html)
            saved.append({"name": f"{ymd} 콘티 추천", "link": r.get("webViewLink") or existing.get("webViewLink"), "status": "replaced"})
        elif existing:
            saved.append({"name": f"{ymd} 콘티 추천", "link": existing.get("webViewLink"), "status": "exists"})
        else:
            saved.append(save_to_folder(g, fid, f"{ymd} 콘티 추천", data=doc_html, mime="text/html",
                                        convert_to="application/vnd.google-apps.document"))
        for s_ in saved:
            mark = {"uploaded": "✅", "replaced": "♻️", "exists": "⏭"}[s_["status"]]
            log(f"   {mark} {s_['name']} → {s_['link']}")
        text += f"\n\n📁 {fname}\n{folder_link}"
    else:
        folder_link = ""
        log(f"DRY-RUN — 업로드·텔레그램 생략. 결과: {OUT / (ymd + '-conti.txt')}")

    html_msg = format_html(d, sermon, rec, folder_link)
    (OUT / f"{ymd}-conti.html").write_text(html_msg, encoding="utf-8")
    if notify and not dry_run:
        ok = telegram_html(html_msg)
        log(f"텔레그램 {'발송 완료' if ok else '발송 실패'} (제목 링크, HTML)")
        print(f"\n✅ {d.month}/{d.day} 콘티 추천 {len(rec['ccm']) + len(rec['hymns'])}곡을 텔레그램으로 보냈습니다. 폴더: {folder_link}")
    else:
        print("\n" + text)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="주보 HWP → 콘티 추천")
    ap.add_argument("hwp", help="주보 파일 — .hwp/.hwpx 또는 .pdf (PDF 만 있으면 그대로 저장하고 본문만 읽는다)")
    ap.add_argument("--pdf", help="한글에서 내보낸 PDF (HWP 와 함께 받았을 때; 자동변환 대신 사용)")
    ap.add_argument("--date"); ap.add_argument("--leader", default=prep.DEFAULT_LEADER)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--no-youtube", action="store_true")
    ap.add_argument("--notify", action="store_true", help="텔레그램(경진비서방)으로 발송 — 곡 제목에 링크(HTML)")
    ap.add_argument("--redo", action="store_true", help="이미 있는 '콘티 추천' 문서를 새 추천으로 덮어쓴다")
    ap.add_argument("--from-cache", action="store_true", help="직전 추천(out/YYYYMMDD-conti.json)을 그대로 써서 형식·저장·발송만 다시 한다")
    a = ap.parse_args(argv)
    hwp = Path(a.hwp).expanduser()
    if not hwp.exists():
        log(f"❌ 파일 없음: {hwp}"); return 1
    d = date.fromisoformat(a.date) if a.date else (date_from_filename(hwp.name) or prep.next_sunday())
    try:
        return run(hwp, Path(a.pdf).expanduser() if a.pdf else None, d, a.leader, a.dry_run, a.no_youtube, a.notify, redo=a.redo, from_cache=a.from_cache)
    except Exception as e:  # noqa: BLE001
        log(f"❌ 실패: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
