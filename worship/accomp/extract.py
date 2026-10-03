#!/usr/bin/env python3
"""반주자·싱어용 악보 슬라이드(구글 슬라이드) → data/<날짜>.json + scores/<날짜>/*.png (2026-10-03 교장님 지시).

한 번 옮겨 두면 그 뒤로는 data JSON 을 고치고 build.py 로 HTML 을 다시 만든다.
  python3 accomp/extract.py <슬라이드 ID> [--date 2026-09-27]
"""
from __future__ import annotations
import argparse, html, json, re, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import prep  # noqa: E402  (vip7612 구글 토큰)

W, H = 10692000, 7560000


def box(e):
    t, s = e.get("transform", {}), e.get("size", {})
    return (t.get("translateX", 0) / W, t.get("translateY", 0) / H,
            s.get("width", {}).get("magnitude", 0) * t.get("scaleX", 1) / W,
            s.get("height", {}).get("magnitude", 0) * t.get("scaleY", 1) / H)


def plain(e) -> str:
    return "".join(r.get("textRun", {}).get("content", "") for r in e.get("shape", {}).get("text", {}).get("textElements", [])).strip()


def rich(e) -> str:
    """굵게·밑줄·빨강만 살려 HTML 로. 줄바꿈은 <br>."""
    out = []
    for r in e.get("shape", {}).get("text", {}).get("textElements", []):
        tr = r.get("textRun")
        if not tr: continue
        s, st = html.escape(tr["content"]), tr.get("style", {})
        rgb = st.get("foregroundColor", {}).get("opaqueColor", {}).get("rgbColor", {})
        if rgb.get("red", 0) > .8 and rgb.get("green", 0) < .3: s = f'<em class="red">{s}</em>'
        if st.get("bold"): s = f"<b>{s}</b>"
        if st.get("underline"): s = f"<u>{s}</u>"
        out.append(s)
    return re.sub(r"[\n\x0b]", "<br>", "".join(out)).strip().removesuffix("<br>")


def roster(slide) -> list[dict]:
    """섬김표 — 왼쪽·오른쪽 두 달. 위치로 칸을 맞춘다."""
    shapes = [(box(e), plain(e)) for e in slide["pageElements"] if "shape" in e]
    halves = []
    for x0, x1 in ((0, .5), (.5, 1)):
        S = [(b, t) for b, t in shapes if x0 <= b[0] + .001 < x1]
        title = next((t for b, t in S if b[1] < .02 and t), "")
        dates = sorted([(b[0], t) for b, t in S if .05 < b[1] < .1 and t], key=lambda x: x[0])
        cols = [x for x, _ in dates]
        labels = sorted([(b[1], t) for b, t in S if b[0] < x0 + .05 and b[1] > .1 and t], key=lambda x: x[0])
        ys = []
        for y in sorted(b[1] for b, t in S if b[1] > .1 and b[0] >= x0 + .08 and b[3] < .1):
            if not ys or y - ys[-1] > .02: ys.append(y)   # 0.29·0.30 처럼 살짝 어긋난 칸은 한 줄
        rows = []
        for y in ys:
            lab = [t for ly, t in labels if ly <= y + .015]
            role = lab[-1] if lab else ""
            cells = [""] * len(cols)
            for b, t in S:
                if abs(b[1] - y) < .015 and b[0] >= x0 + .08 and b[3] < .1:
                    i = min(range(len(cols)), key=lambda k: abs(cols[k] - b[0]))
                    cells[i] = t.replace("\n", "")
            rows.append({"role": role, "cells": cells})
        halves.append({"title": title, "dates": [t for _, t in dates], "rows": rows})
    return halves


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("sid"); ap.add_argument("--date")
    a = ap.parse_args()
    g = prep.G(prep.access_token())
    p = g.req("GET", f"https://slides.googleapis.com/v1/presentations/{a.sid}")
    date = a.date or re.search(r"(\d{4})\s?(\d{2})(\d{2})", p["title"]).expand(r"\1-\2-\3")
    sdir = HERE / "scores" / date; sdir.mkdir(parents=True, exist_ok=True)
    pages = []
    for n, s in enumerate(p["slides"], 1):
        els = s.get("pageElements", [])
        imgs = sorted([(box(e), e["image"]["contentUrl"]) for e in els if "image" in e and box(e)[0] > -.01], key=lambda x: x[0][0])
        shapes = [(box(e), e) for e in els if "shape" in e and plain(e)]
        texts = [plain(e) for _, e in shapes]
        if imgs:
            slots = []
            for side, (b, url) in zip(("L", "R"), [i for i in imgs if i[0][0] < .5][:1] + [i for i in imgs if i[0][0] >= .5][:1]):
                f = sdir / f"p{n:02d}{side}.png"
                f.write_bytes(urllib.request.urlopen(url, timeout=60).read())
                slots.append({"side": "R" if b[0] >= .5 else "L", "title": "", "img": str(f.relative_to(HERE))})
            pages.append({"type": "scores", "slots": slots})
        elif n == 1:
            pages.append({"type": "cover", "title": texts[0], "sub": texts[1], "date": texts[2]})
        elif any("섬김표" in t for t in texts):
            pages.append({"type": "roster", "months": roster(s)})
        elif any(t.startswith("설교본문") for t in texts):
            body = max(shapes, key=lambda x: x[0][3])[1]
            ref = next(t for t in texts if re.search(r"\d+:\d", t) and len(t) < 30)
            title = next(t for (b, e), t in zip(shapes, texts) if b[1] < .14 and t not in ("설교본문:", ref))
            pages.append({"type": "sermon_text", "ref": ref, "title": title, "body": rich(body)})
        elif len(shapes) == 2 and all(b[3] > .8 for b, _ in shapes):
            L, R = sorted(shapes, key=lambda x: x[0][0])
            pages.append({"type": "sermon_summary", "left": rich(L[1]), "right": rich(R[1])})
        else:
            head = min(shapes, key=lambda x: x[0][1]); body = max(shapes, key=lambda x: x[0][3])
            kind = "creed" if "사도신경" in plain(head[1]) else "recite"
            pages.append({"type": kind, "heading": rich(head[1]), "body": rich(body[1])})
    data = {"date": date, "title": p["title"], "source": f"https://docs.google.com/presentation/d/{a.sid}/edit", "pages": pages}
    out = HERE / "data" / f"{date}.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(out, len(pages), "쪽:", " · ".join(x["type"] for x in pages))


if __name__ == "__main__":
    main()
