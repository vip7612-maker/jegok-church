#!/usr/bin/env python3
"""악보 넣기·빼기 — 도입곡 / 1·2·3 … / 적용송 (2026-10-03 교장님 지시).

쪽 번호를 몰라도 곡 번호로 부른다. 넣고 빼면 번호와 쪽이 저절로 다시 매겨진다.
  python3 accomp/score.py list   2026-10-04
  python3 accomp/score.py add    2026-10-04 3 악보.png --title "곡 제목"   # 3번 자리에 끼워 넣기(뒤 번호는 하나씩 밀림)
  python3 accomp/score.py add    2026-10-04 끝 악보.png --title "…"      # 본곡 맨 뒤에
  python3 accomp/score.py set    2026-10-04 3 악보.png [--title "…"]    # 3번 악보 바꾸기
  python3 accomp/score.py add    2026-10-04 도입곡 악보.png             # 도입곡 / 적용송 도 같은 식(set 은 첫 곡을 바꿈)
  python3 accomp/score.py title  2026-10-04 3 "새 제목"
  python3 accomp/score.py rm     2026-10-04 3
  python3 accomp/score.py move   2026-10-04 5 2                           # 5번을 2번 자리로
뒤에 --share 를 붙이면 만들어 바로 링크에 올린다.
"""
from __future__ import annotations
import json, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = {"도입곡": "intro", "도입": "intro", "intro": "intro", "적용송": "apply", "적용": "apply", "apply": "apply"}


def where(arg: str) -> tuple[str, int | None]:
    """'3' → (main, 2) · '끝' → (main, None) · '도입곡' → (intro, 0)."""
    if arg in NAMES: return NAMES[arg], 0
    if arg in ("끝", "end", "마지막"): return "main", None
    return "main", int(arg.rstrip("번")) - 1


def copy_img(date: str, src: str) -> str:
    d = HERE / "scores" / date; d.mkdir(parents=True, exist_ok=True)
    dst = d / f"s{int(time.time() * 1000)}{Path(src).suffix.lower() or '.png'}"
    shutil.copy(src, dst)
    return str(dst.relative_to(HERE))


def show(data: dict) -> None:
    S = data.get("songs", {})
    for g, name in (("intro", "도입곡"), ("main", None), ("apply", "적용송")):
        for i, s in enumerate(S.get(g, [])):
            print(f"{name or f'{i + 1}번'} · {s.get('title') or '제목 미정'}{'' if s.get('img') else ' (악보 없음)'}")


def main() -> int:
    a = [x for x in sys.argv[1:] if x != "--share"]
    title = None
    if "--title" in a:
        i = a.index("--title"); title = a[i + 1]; a = a[:i] + a[i + 2:]
    cmd, date = a[0], a[1]
    f = HERE / "data" / f"{date}.json"; data = json.loads(f.read_text())
    S = data.setdefault("songs", {"intro": [], "main": [], "apply": []})
    if cmd != "list":
        g, i = where(a[2]); L = S.setdefault(g, [])
        if cmd == "add":
            item = {"title": title or "", "img": copy_img(date, a[3])}
            L.insert(len(L) if i is None else i, item)
        elif cmd == "set":
            L[i or 0]["img"] = copy_img(date, a[3])
            if title: L[i or 0]["title"] = title
        elif cmd == "title":
            L[i or 0]["title"] = a[3]
        elif cmd == "rm":
            L.pop(i or 0)
        elif cmd == "move":
            L.insert(int(a[3].rstrip("번")) - 1, L.pop(i))
        f.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    show(data)
    if cmd != "list":
        args = [sys.executable, str(HERE / "build.py"), date] + (["--share"] if "--share" in sys.argv else [])
        print(subprocess.run(args, capture_output=True, text=True).stdout.strip().splitlines()[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
