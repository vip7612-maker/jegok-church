#!/usr/bin/env python3
"""말씀에 맞는 곡 추천 + 예배 방향 글 — 예배순서를 확정하면 성경 본문·설교 제목으로 (2026-10-07 교장님).

새벽·수요·금요·주일 모두. 예배순서의 성경봉독 본문(없으면 설교 줄 본문)과 설교(말씀) 제목을 읽고
  1. 본문(개역개정, next_api_bot/worker/bible_lookup.py)을 찾아
  2. 교회 곡 목록(곡 빠르기 표 song_tempo.json — 악보가 있는 곡)에서만 골라 빠른·중간·느린곡으로 추천하고
  3. 이런 방향으로 예배를 드리면 좋겠다는 글을 5줄 이내로 쓴다.
결과는 예배 DB wor_reco 에 둔다(다시 배포하지 않아도 예배준비 화면에 바로 보인다). 본문·제목이 바뀌면 다시 만든다.

  python3 accomp/reco_gen.py 2026-10-08      # 그 날 다시 만들기
"""
from __future__ import annotations
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TABLE = Path.home() / "dev/daily-briefing/report-site/jegok_worship/song_tempo.json"
BIBLE = Path.home() / "dev/next_api_bot/worker/bible_lookup.py"
CLAUDE = str(Path.home() / ".local/bin/claude")
CHURCH = "jegok"
TEMPOS = ("빠른곡", "중간곡", "느린곡")


def _db(stmts):
    import wadmin
    return wadmin.batch(stmts)


def ensure() -> None:
    _db([("CREATE TABLE IF NOT EXISTS wor_reco (church TEXT, date TEXT, src TEXT, data TEXT, updated TEXT, PRIMARY KEY (church, date))", [])])


def source(items: list[dict]) -> tuple[str, str]:
    """예배순서에서 (성경 본문, 설교 제목). 설교는 「말씀」 줄이어도 된다."""
    import order_sync as O
    ref = title = ""
    for x in items:
        c = O.canon(x.get("t", ""))
        if c == "성경봉독" and x.get("ref"): ref = ref or x["ref"]
        if c == "설교":
            title = title or x.get("title", ""); ref = ref or x.get("ref", "")
    return ref.strip(), title.strip()


def jubo_summary(date: str) -> str:
    """첨부한 주보의 설교 요약(「오늘의 말씀」 제목·본문 아래 글). HWP 는 jubo_form.parse 의 s_body, PDF 는 표 칸 안에서 찾는다."""
    J = HERE / "jubo"
    f = next((J / f"{date}.{x}" for x in ("hwp", "hwpx", "pdf") if (J / f"{date}.{x}").exists()), None)
    if not f: return ""
    try:
        import jubo_form
        md, _ = jubo_form.kordoc(f.read_bytes()); d = jubo_form.parse(md)
    except Exception:
        return ""
    body = " ".join(d.get("s_body") or [])
    if not body:
        m = re.search(r"오늘의\s*말씀\s*</th>\s*</tr>\s*<tr>\s*<td>(.*?)</td>", md, re.S)
        if m:
            parts = [x.strip() for x in re.split(r"<br\s*/?>", m.group(1))]
            k = next((i for i, x in enumerate(parts) if re.fullmatch(r"\(.*\)", x)), 0)
            body = " ".join(parts[k + 1:])
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)).strip()[:1800]


def bible(ref: str) -> str:
    if not ref: return ""
    r = subprocess.run([sys.executable, str(BIBLE), ref], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()[:4000] if r.returncode == 0 else ""


PROMPT = """제곡교회 예배 준비를 돕습니다. 아래 성경 본문과 설교 제목에 맞는 찬양을 교회 곡 목록에서만 골라 JSON 으로만 답하세요. 설명 글은 쓰지 마세요.

성경 본문: {ref}
설교 제목: {title}
본문(개역개정):
{text}

주보 설교 요약:
{summary}

규칙
- songs: 아래 「곡 목록」에 있는 제목만 글자 그대로. 16곡 안팎 — 빠른곡 4~5, 중간곡 6~7, 느린곡 4~5(목록에 적힌 빠르기 기준).
  도입(여는 찬양) → 말씀으로 들어가는 고백 → 결단·적용 흐름에 쓸 수 있게. why 는 10자 이내.
- theme: 본문과 제목에서 잡은 예배 주제 한 줄(30자 이내).
- guide: 예배 인도자에게 드리는 글. 이 본문과 제목으로 이런 방향으로 예배를 드리면 좋겠다는 내용을 5줄 이내(줄마다 40자 안팎, 줄바꿈 \\n).
  본문·제목·주보 설교 요약에 있는 내용만 근거로. 줄표(—)·이모지·꾸밈말 없이 담백하게.

답 꼴: {{"theme": "...", "guide": "첫째 줄\\n둘째 줄", "songs": [{{"title": "...", "why": "..."}}]}}

곡 목록(제목 · 빠르기 · 주제곡이면 *):
{songs}
"""


def table() -> dict:
    return json.loads(TABLE.read_text()) if TABLE.exists() else {}


def make(date: str, items: list[dict], run=None, summary: str = "") -> dict | None:
    """추천 만들기 — 본문·제목·주보 요약이 모두 없으면 None."""
    import publish
    ref, title = source(items)
    if not ref and not title and not summary: return None
    tb = table()
    lines = "\n".join(f"{v['t']} · {v['tempo']}{' *' if v.get('deep') else ''}" for v in tb.values())
    text = (run or _claude)(PROMPT.format(ref=ref or "(없음)", title=title or "(없음)", text=bible(ref) or "(본문을 찾지 못함 — 제목으로)", summary=summary or "(없음)", songs=lines))
    m = re.search(r"\{.*\}", text, re.S)
    if not m: raise RuntimeError(f"JSON 못 받음: {text[:200]}")
    d = json.loads(m.group(0))
    ccm, seen = [], set()
    for s in d.get("songs") or []:
        k = publish.song_key(s.get("title", ""))
        if k in tb and k not in seen:                                   # 목록에 있는 곡만(지어낸 제목은 버림)
            seen.add(k); v = tb[k]
            ccm.append({"title": v["t"], "tempo": v["tempo"], "deep": bool(v.get("deep")), "why": str(s.get("why", ""))[:14]})
    guide = "\n".join([x.strip() for x in str(d.get("guide", "")).split("\n") if x.strip()][:5])
    return {"ref": ref, "title": title, "summary": bool(summary), "theme": str(d.get("theme", ""))[:60], "guide": guide, "ccm": ccm, "hymns": [], "by": "reco_gen"}


def _claude(prompt: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) and k != "CLAUDE_CODE_OAUTH_TOKEN"}
    r = subprocess.run([CLAUDE, "-p", prompt, "--output-format", "text"], capture_output=True, text=True, timeout=600, env=env, cwd=tempfile.gettempdir())
    return r.stdout or r.stderr


def ensure_for(date: str, items: list[dict], force: bool = False) -> str:
    """본문·제목이 바뀌었을 때만 다시 만든다. force 면([추천곡에 반영]) 늘 다시 — 주보 설교 요약도 함께 읽는다."""
    import datetime as dt
    ensure()
    ref, title = source(items)
    summary = jubo_summary(date) if force else ""
    if not ref and not title and not summary: return f"{date} 본문·제목·주보 요약이 없어 추천 안 함"
    src = f"{ref}|{title}"
    cur = _db([("SELECT src FROM wor_reco WHERE church=? AND date=?", [CHURCH, date])])[0]
    if cur and cur[0]["src"] == src and not force: return f"{date} 추천 그대로({src})"
    d = make(date, items, summary=summary)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _db([("INSERT INTO wor_reco(church,date,src,data,updated) VALUES(?,?,?,?,?) ON CONFLICT(church,date) DO UPDATE SET src=excluded.src, data=excluded.data, updated=excluded.updated",
          [CHURCH, date, src, json.dumps(d, ensure_ascii=False), now])])
    return f"{date} 말씀에 맞는 곡 {len(d['ccm'])}곡 · 예배 방향 {len(d['guide'].splitlines())}줄 ({src}{' · 주보 요약' if summary else ''})"


if __name__ == "__main__":
    import order_sync as O
    date = sys.argv[1]
    row = O.load(date)
    print(ensure_for(date, json.loads(row["items"]) if row else [], force=True))
