#!/usr/bin/env python3
"""합심기도 PPT — 노션 「공동기도제목」 DB 의 금요기도회 기도제목을 합심기도 표지 뒤에 장으로 (2026-10-07 교장님).

그 예배 날짜와 같거나 그 전의 가장 최근 기도제목지(모임=금요기도회, 교회=제곡교회)를 읽는다.
노션 「## 제목」은 굵은 머리 줄(번호를 붙임), 「- 목록」은 그 아래 줄. 장 꾸미기는 교회 소식 장과 같다(ppt_tpl.pages).
기도제목에는 사람 이름이 들어 있어, 노션 이 DB 밖(지식창고 등)으로는 옮기지 않는다 — PPT 화면에만 쓴다.

  python3 accomp/prayer.py 2026-10-09      # 그 날 쓸 기도제목 줄 보기
"""
from __future__ import annotations
import importlib.util, re, sys
from pathlib import Path

NP = Path.home() / "dev/daily-briefing/notion_prayer.py"


def _np():
    spec = importlib.util.spec_from_file_location("notion_prayer", NP)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _text(b: dict) -> str:
    t = b.get(b["type"], {}).get("rich_text", [])
    return "".join(x.get("plain_text") or x.get("text", {}).get("content", "") for x in t).strip()


def lines_from_blocks(blocks: list[dict]) -> list[str]:
    """노션 블록 → 장에 쓸 줄. 머리(##)는 「1. 제목」(굵게), 목록은 「· 내용」."""
    out, n = [], 0
    for b in blocks:
        t = _text(b)
        if not t: continue
        if b["type"] in ("heading_1", "heading_2", "heading_3"):
            n += 1; out.append(t if re.match(r"\d+\.", t) else f"{n}. {t}")
        elif b["type"] in ("bulleted_list_item", "numbered_list_item", "to_do"):
            out.append("· " + t.lstrip())
        else:
            out.append(t)
    return out


def latest(day: str, kind: str = "금요기도회", church: str = "제곡교회") -> tuple[str, list[str]]:
    """그 날과 같거나 그 전의 가장 최근 기도제목지 → (날짜, 줄). 없으면 ("", [])."""
    np_ = _np(); tok = np_.token(); conf = np_.cfg(tok)
    res = np_.api("POST", f"/databases/{conf['prayer_database_id']}/query", tok, {
        "page_size": 1, "sorts": [{"property": "날짜", "direction": "descending"}],
        "filter": {"and": [{"property": "모임", "select": {"equals": kind}}, {"property": "교회", "select": {"equals": church}},
                           {"property": "날짜", "date": {"on_or_before": day}}]}})
    hit = (res.get("results") or [None])[0]
    if not hit: return "", []
    when = ((hit["properties"].get("날짜") or {}).get("date") or {}).get("start", "")
    blocks, cur = [], None
    while True:
        q = f"/blocks/{hit['id']}/children?page_size=100" + (f"&start_cursor={cur}" if cur else "")
        r = np_.api("GET", q, tok); blocks += r.get("results", [])
        if not r.get("has_more"): break
        cur = r.get("next_cursor")
    return when, lines_from_blocks(blocks)


if __name__ == "__main__":
    w, L = latest(sys.argv[1])
    print(w); print("\n".join(L))
