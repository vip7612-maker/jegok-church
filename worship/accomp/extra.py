#!/usr/bin/env python3
"""그 주에만 끼우는 특별 순서(선교 보고·간증·임직식…) — data/<날짜>.json 의 ppt_extra 를 고친다 (2026-10-04 교장님).
여기서 만든 순서는 예배 PPT 목차에 들어가고 발표자 보기에서 늘 「＋ 장 넣기」가 붙는다(slides.py XSECTS).

  python3 accomp/extra.py add 2026-10-11 "선교 보고" --name "디마 선교사" [--label "Mission Report"] [--after 특송] [--pdf 보고.pdf] [--share]
  python3 accomp/extra.py rm 2026-10-11 "선교 보고" [--share]
  python3 accomp/extra.py list 2026-10-11
--after 는 그 순서 표지 바로 뒤(대표기도·교회소식·봉헌·성경봉독·특송·설교·찬양과결단, 기본 특송). --pdf 는 accomp/extra/<날짜>/ 안 파일.
"""
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AFTER = {"대표기도": "Prayer", "교회소식": "Announcements", "봉헌": "Offering", "성경봉독": "ScriptureReading",
         "특송": "SpecialPraise", "설교": "Sermon", "찬양과결단": "찬양과결단", "선교보고": "MissionReport"}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["add", "rm", "list"]); ap.add_argument("date")
    ap.add_argument("title", nargs="?"); ap.add_argument("--name", default=""); ap.add_argument("--label", default="")
    ap.add_argument("--after", default="특송"); ap.add_argument("--pdf"); ap.add_argument("--share", action="store_true")
    a = ap.parse_args()
    f = HERE / "data" / f"{a.date}.json"; d = json.loads(f.read_text())
    ex = d.setdefault("ppt_extra", [])
    if a.cmd == "list":
        for x in ex: print(f"• {x['title']} · {x.get('name','')} (뒤: {x['after']}{' · PDF ' + x['pdf'] if x.get('pdf') else ''})")
        if not ex: print("특별 순서 없음")
        return
    if not a.title: sys.exit("순서 이름을 주세요")
    ex[:] = [x for x in ex if x.get("title") != a.title]
    if a.cmd == "add":
        k = a.after.replace(" ", "")
        x = {"after": AFTER.get(k, k), "base": "ScriptureReading", "label": a.label or a.title, "title": a.title, "name": a.name}
        if a.pdf: x["pdf"] = a.pdf
        ex.append(x)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    print(("➕ " if a.cmd == "add" else "➖ ") + a.title, "— 발표자 보기에 ＋ 장 넣기가 붙습니다" if a.cmd == "add" else "")
    if a.share: subprocess.run([sys.executable, str(HERE / "build.py"), a.date, "--share"], cwd=HERE.parent, check=True)

if __name__ == "__main__":
    main()
