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

[내용 — 이 글에 있는 것만 쓴다. 날짜·시간·장소·이름은 그대로, 지어내지 않는다]
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


def make_html(title: str, body: str, where: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) and k != "CLAUDE_CODE_OAUTH_TOKEN"}
    r = subprocess.run([CLAUDE, "-p", PROMPT.format(title=title or "(없음)", body=body or "(없음)", where=where), "--output-format", "text"],
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
            h = make_html(d.get("title", ""), d.get("body", ""), {"news": "교회 소식", "sermon": "설교"}.get(row["sect"], ""))
            d["html"] = h
            S.sql("UPDATE ppt_pages SET data=?, status='ready', err=NULL WHERE id=?", json.dumps(d, ensure_ascii=False), i)
            print(f"[장 넣기 {i}] 만듦 — {d.get('title', '')}", flush=True)
        except Exception as ex:  # noqa: BLE001
            S.sql("UPDATE ppt_pages SET status='fail', err=? WHERE id=?", str(ex)[:300], i)
            print(f"[장 넣기 {i}] 실패 — {ex}", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    run(int(a[a.index("--id") + 1]) if "--id" in a else None)
