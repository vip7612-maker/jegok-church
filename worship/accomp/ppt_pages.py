#!/usr/bin/env python3
"""예배 PPT 「＋ 장 넣기」의 🎨 AI 디자인 페이지 만들기 (2026-10-04 교장님).

  발표자 보기에서 교회 소식·설교 뒤에 ＋ → 🎨 → 문구를 쓰면 ppt_pages 줄(status wait)이 생긴다.
  맥미니(conti_sync, 1분마다)가 가져가 Claude 로 **html 스킬 원칙**(양식 없는 문서 = 글만 늘어놓지 말고 도식을 섞는다,
  inline SVG/CSS, 내용 지어내지 않기)에 따라 1920×1080 한 장 HTML 을 만든다. 배경은 투명 — PPT 템플릿 배경 위에 얹힌다.

  python3 accomp/ppt_pages.py            # 기다리는 것 만들기
  python3 accomp/ppt_pages.py --id 3     # 하나만 다시
"""
from __future__ import annotations

import json, os, re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import store as S  # noqa: E402

CLAUDE = str(Path.home() / ".local/bin/claude")
SQL = "CREATE TABLE IF NOT EXISTS ppt_pages (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, sect TEXT, type TEXT, data TEXT, status TEXT, pos INTEGER, err TEXT, at TEXT)"

PROMPT = """제곡교회 주일예배 PPT 에 끼워 넣을 슬라이드 한 장을 HTML 로 만들어 주세요. ({where} 순서 뒤에 들어갑니다)

[이번 주 예배 플랫폼 자료 전체 — 주보 전문·설교·요약·암송·섬김표·찬양·공지·PPT 장별 글·추가 순서 자료. 이 자료를 늘 바탕으로 삼아 맥락에 맞게 만든다. 요청이 무엇을 가리키든(설교·소식·선교 보고 등) 여기서 구체 내용을 찾아 채운다]
{context}

[요청 — 이 장에 담을 것. 요청이 지시문이면 위 예배 자료에서 해당 내용(설교 제목·본문·요약 대지·소식 등)을 찾아 구체적으로 채운다.
 일반적인 도식이나 빈 틀로 때우지 않는다. 자료와 요청에 있는 것만 쓰고, 날짜·시간·장소·이름은 그대로, 지어내지 않는다]
제목: {title}
문구:
{body}

[교장님 html 스킬 원칙 — 양식 없는 문서]
- 글만 길게 늘어놓지 않는다. 내용에 맞는 **도식**을 섞는다: 순서·흐름 → 화살표로 잇는 단계 상자, 일정 → 타임라인,
  견줌 → 표, 핵심 숫자·날짜·장소 → 큰 카드. 도식은 inline SVG 나 CSS 상자로 직접 그린다(외부 라이브러리·외부 그림 금지).
- 화려한 장식·그라데이션·그림자·이모지 남발 금지. 차분하고 읽기 쉽게. word-break: keep-all.

[화면·테마 — 반드시 지킨다]
- 크기 1920×1080 고정: html, body {{ margin:0; width:1920px; height:1080px; overflow:hidden; background:transparent }}.
  배경은 **투명** — 뒤에 PPT 템플릿 배경(짙은 갈색 #6b5444 바탕)이 깔린다. 배경색·배경그림을 넣지 않는다.
- 색: 글자 흰색 #ffffff, 강조 금빛 #f6c76b, 크림 #efe6dd, 카드·도식 상자는 반투명 흰색 rgba(255,255,255,.10~.16) + 테두리 rgba(255,255,255,.35).
- 글꼴: <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
  font-family: 'Pretendard Variable', Pretendard, sans-serif.
- 예배당 화면에서 읽히게: 제목 76~92px 굵게, 본문 42~52px, 도식 안 글자 36px 이상. 여백 왼쪽·오른쪽 90px, 위 70px, 아래 70px.
- 모든 내용이 한 화면 안에 들어가야 한다(넘치지 않게 — 글이 많으면 글자를 조금 줄이거나 요약하지 말고 배치를 바꾼다).
- <script> 쓰지 않는다.

완성된 HTML 문서(<!doctype html> 부터 </html> 까지)만 답하세요."""


def week_context(date: str | None, skip_id: int | None = None) -> str:
    """예배 플랫폼에 있는 그 주 자료를 모두 모아 모델에 같이 준다 (2026-10-04 교장님: 「장 넣기 AI 디자인 페이지는
    이 플랫폼에 있는 모든 자료를 참고하는 것을 기본으로」). 찬양은 곡명만(가사는 넣지 않음).
      ① 악보집 데이터 — 설교 제목·본문·요약, 암송, 섬김표(그 주), 공지, 찬양 곡명, 추가 순서
      ② 주보 PDF 전문  ③ 추가 순서 자료 PDF(선교 보고 등)  ④ 예배 PPT 각 장의 글(순서·담당·교회 소식)
      ⑤ 현장에서 고친 PPT 글(ppt_news)  ⑥ 그 주에 이미 넣은 다른 장들"""
    if not date: return "(자료 없음)"
    strip = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(h or ""))).strip()
    out = []
    def add(title, text, cap):
        text = (text or "").strip()
        if text: out.append(f"■ {title}\n{text[:cap]}")
    # ① 악보집 데이터
    try:
        d = json.loads((HERE / "data" / f"{date}.json").read_text())
        for p in d.get("pages", []):
            t = p.get("type")
            if t == "sermon_text":
                add("설교", f"「{p.get('title','')}」 · 본문 {p.get('ref','')}\n{strip(p.get('body'))}", 2500)
            elif t == "sermon_summary":
                add("설교 요약(주보)", f"{strip(p.get('left'))} {strip(p.get('right'))}", 5000)
            elif t == "recite":
                add("암송 " + strip(p.get("heading")), strip(p.get("body")), 600)
            elif t == "roster":
                key = f"{int(date[5:7])}.{int(date[8:10])}"
                rows = []
                for m in p.get("months", []):
                    ds = m.get("dates", [])
                    if key in ds:
                        k = ds.index(key)
                        for r in m.get("rows", []):
                            c = r.get("cells", [])
                            if k < len(c) and c[k]: rows.append(f"{r.get('role','')}: {strip(c[k])}")
                add("이번 주 섬김(예배팀)", " / ".join(rows), 800)
        songs = d.get("songs", {})
        names = [f"{lab} {x.get('title','')}" for k, lab in (("intro", "도입"), ("main", "찬양"), ("apply", "적용")) for x in songs.get(k, [])]
        add("오늘 찬양(곡명)", " · ".join(names), 600)
        add("공지", " / ".join(map(strip, d.get("notices", []))), 1200)
        for x in d.get("ppt_extra", []):
            add("이번 주 추가 순서", f"{x.get('title','')} — {x.get('name','')}", 200)
    except Exception as ex:  # noqa: BLE001
        out.append(f"(악보집 데이터를 읽지 못함: {ex})")
    site = None
    try:
        import publish
        site = Path.home() / "dev/daily-briefing/report-site/d" / publish.sid_for(date)
    except Exception:  # noqa: BLE001
        pass
    try:
        import fitz
        # ② 주보 전문
        if site and (site / "jubo.pdf").exists():
            add("주보 전문", " ".join(pg.get_text() for pg in fitz.open(site / "jubo.pdf")), 5000)
        # ③ 추가 순서 자료(선교 보고 PDF 등)
        for f in sorted((HERE / "extra" / date).glob("*.pdf")) if (HERE / "extra" / date).exists() else []:
            add(f"추가 자료 「{f.stem}」", re.sub(r"\s+", " ", " ".join(pg.get_text() for pg in fitz.open(f))), 3000)
    except Exception:  # noqa: BLE001
        pass
    # ④ 예배 PPT 각 장의 글(곡 자막 제외)
    try:
        h = (site / "ppt.html").read_text() if site else ""
        m = re.search(r"const D=(\[.*?\]);\n", h, re.S)
        if m:
            seen, lines = set(), []
            for sl in json.loads(m.group(1)):
                if str(sl.get("img", "")).startswith("song_"): continue
                t = strip(" ".join(x.get("t", "") for x in sl.get("texts", [])))
                if t and t not in seen and not re.search(r"[А-Яа-я]", t): seen.add(t); lines.append(t[:300])
            add("예배 PPT 장별 글", "\n".join(lines), 6000)
    except Exception:  # noqa: BLE001
        pass
    # ⑤ 현장에서 고친 글 · ⑥ 이미 넣은 다른 장
    try:
        for r in S.sql("SELECT i, texts FROM ppt_news WHERE date=?", date):
            add(f"현장에서 고친 PPT {int(r['i'])+1}번째 장", " / ".join(json.loads(r["texts"] or "[]")), 600)
    except Exception:  # noqa: BLE001
        pass
    try:
        for r in S.sql("SELECT id, sect, type, data FROM ppt_pages WHERE date=? ORDER BY id", date):
            if skip_id and int(r["id"]) == int(skip_id): continue
            x = json.loads(r["data"] or "{}")
            add(f"이미 넣은 장({r['sect']}·{r['type']})", f"{x.get('title','') or x.get('ref','')} {x.get('body','')}".strip(), 300)
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(out)[:24000] or "(자료 없음)"


def make_html(title: str, body: str, where: str, date: str | None = None, skip_id: int | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) and k != "CLAUDE_CODE_OAUTH_TOKEN"}
    r = subprocess.run([CLAUDE, "-p", PROMPT.format(title=title or "(없음)", body=body or "(없음)", where=where, context=week_context(date, skip_id)), "--output-format", "text"],
                       capture_output=True, text=True, timeout=600, env=env, cwd=tempfile.gettempdir())
    t = r.stdout
    m = re.search(r"<!doctype html.*?</html>", t, re.S | re.I)
    if not m: raise RuntimeError(f"HTML 을 못 받음: {(t or r.stderr)[:200]}")
    h = m.group(0)
    h = re.sub(r"<script\b.*?</script\s*>", "", h, flags=re.S | re.I)          # 혹시 들어간 스크립트는 뺀다
    if "background:transparent" not in h.replace(" ", ""):                       # 배경은 꼭 투명(템플릿 유지)
        h = h.replace("</head>", "<style>html,body{background:transparent!important}</style></head>", 1)
    return h


def run(only: int | None = None) -> None:
    S.sql(SQL)
    rows = S.sql("SELECT * FROM ppt_pages WHERE id=?", only) if only else S.sql("SELECT * FROM ppt_pages WHERE type='html' AND status='wait' ORDER BY id LIMIT 3")
    for row in rows:
        i = int(row["id"]); d = json.loads(row["data"] or "{}")
        S.sql("UPDATE ppt_pages SET status='work' WHERE id=?", i)
        try:
            h = make_html(d.get("title", ""), d.get("body", ""), ({"news": "교회 소식", "reading": "성경 봉독", "special": "특송", "sermon": "설교"}.get(row["sect"]) or (row["sect"] or "")[2:] if str(row["sect"] or "").startswith("x:") else {"news": "교회 소식", "reading": "성경 봉독", "special": "특송", "sermon": "설교"}.get(row["sect"], "")), date=row.get("date"), skip_id=i)
            d["html"] = h
            S.sql("UPDATE ppt_pages SET data=?, status='ready', err=NULL WHERE id=?", json.dumps(d, ensure_ascii=False), i)
            print(f"[장 넣기 {i}] 만듦 — {d.get('title', '')}", flush=True)
        except Exception as ex:  # noqa: BLE001
            S.sql("UPDATE ppt_pages SET status='fail', err=? WHERE id=?", str(ex)[:300], i)
            print(f"[장 넣기 {i}] 실패 — {ex}", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    run(int(a[a.index("--id") + 1]) if "--id" in a else None)
