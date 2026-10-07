#!/usr/bin/env python3
"""새벽·수요·금요 예배 악보집 바탕 (2026-10-07 교장님: 새벽예배도 [악보집 및 PPT 생성]).

주일은 weekly.open_week(템플릿·섬김표·암송·사도신경이 든 악보집). 그 밖의 날은 짧게:
  표지(예배 이름) · 말씀(예배순서의 본문·제목, 개역개정 본문) · 곡(도입·진행·적용)
"""
from __future__ import annotations
import datetime as dt, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIBLE = Path.home() / "dev/next_api_bot/worker/bible_lookup.py"


def service(date: str) -> str:
    """요일 → 예배 이름(api/wadmin.js·prep.html SVN 과 같게). 주일 외 수·금은 저녁 예배, 나머지는 새벽예배."""
    return {6: "주일예배", 2: "수요예배", 4: "금요예배"}.get(dt.date.fromisoformat(date).weekday(), "새벽예배")


def verses_html(ref: str) -> str:
    if not ref: return ""
    r = subprocess.run([sys.executable, str(BIBLE), ref], capture_output=True, text=True, timeout=60)
    if r.returncode != 0: return ""
    out = []
    for ln in r.stdout.splitlines()[1:]:
        m = re.match(r"\s*(\d+)\s+(.*)", ln)
        if m: out.append(f"<b class='vn'>{m.group(1)}</b> {m.group(2).strip()}")
    return "<br>".join(out)


def data_for(date: str, items: list[dict]) -> dict:
    """주일이 아닌 날의 악보집 data — 예배순서에서 본문·제목을 읽는다."""
    import reco_gen
    ref, title = reco_gen.source(items)
    d = dt.date.fromisoformat(date)
    name = service(date)
    pages = [{"type": "cover", "title": " ".join(name), "sub": "예배자 악보", "date": f"{d:%Y.%m.%d}", "church": "제곡교회"}]
    if ref or title:
        pages.append({"type": "sermon_text", "ref": ref, "title": title, "body": verses_html(ref)})
    pages += [{"type": "songs", "group": "intro"}, {"type": "songs", "group": "main"}, {"type": "songs", "group": "apply"}]
    return {"date": date, "title": f"{d:%Y %m%d} {name} 예배자 악보", "source": "", "service": name,
            "pages": pages, "songs": {"intro": [], "main": [], "apply": []}, "notices": []}


def ensure(date: str) -> str:
    """data/<날짜>.json 이 없으면 만든다. 있으면 그대로."""
    f = HERE / "data" / f"{date}.json"
    if f.exists():
        return refresh(date) if service(date) != "주일예배" else "있음"
    if service(date) == "주일예배":
        import weekly
        weekly.open_week(dt.date.fromisoformat(date)); return "주일 악보집 새로 엶"
    import order_sync
    row = order_sync.load(date)
    items = json.loads(row["items"]) if row and row.get("items") else []
    f.write_text(json.dumps(data_for(date, items), ensure_ascii=False, indent=1))
    return f"{service(date)} 악보집 새로 엶"


def refresh(date: str) -> str:
    """새벽·수요·금요 악보집의 말씀 쪽을 지금 예배순서(본문·제목)에 맞춘다 — 처음 만든 뒤 순서를 고쳐도 따라가게(2026-10-07)."""
    import order_sync, reco_gen
    f = HERE / "data" / f"{date}.json"
    d = json.loads(f.read_text())
    row = order_sync.load(date)
    ref, title = reco_gen.source(json.loads(row["items"]) if row and row.get("items") else [])
    st = next((p for p in d["pages"] if p["type"] == "sermon_text"), None)
    if not ref and not title:
        return "있음"
    if st and st.get("ref") == ref and st.get("title") == title:
        return "있음"
    new = {"type": "sermon_text", "ref": ref, "title": title, "body": verses_html(ref)}
    if st: st.update(new)
    else: d["pages"].insert(1, new)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    return f"말씀 쪽을 예배순서에 맞춤({ref} {title})".strip()
