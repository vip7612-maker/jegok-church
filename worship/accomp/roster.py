#!/usr/bin/env python3
"""예배팀 섬김표 고치기 — roster.json 하나 (2026-10-03 교장님 지시).

  python3 accomp/roster.py show [10.4]                 # 그 주부터 6주
  python3 accomp/roster.py set  9.27 인도자 홍길동      # 바꾸기 (여러 명은 쉼표: "김태헌,허성란")
  python3 accomp/roster.py add  10.11 방송실 홍길동     # 더하기
  python3 accomp/roster.py rm   10.11 방송실 김성준     # 빼기 (이름 없이 쓰면 그 칸 비우기)
  python3 accomp/roster.py copy 11.1 11.8              # 한 주 편성을 다른 주로 그대로
  python3 accomp/roster.py support add 홍길동 | support rm 홍길동   # 지원팀(날짜 없는 명단)
  python3 accomp/roster.py role add 미디어 자막         # 역할 줄 추가 (role rm 자막)
  python3 accomp/roster.py fill 10.4 [11.29]            # 기본값·규칙 채우기 (인도자 이경진·드럼 정상진, 매월 넷째 주 드럼 정영화)
기본값(defaults)과 다른 이름은 악보집에서 색을 달리해 보인다 — "바뀐 사람"을 한눈에 (2026-10-03 교장님 지시).
뒤에 --share 를 붙이면 이 날짜가 들어가는 악보집을 다시 만들어 링크에 올린다.
"""
from __future__ import annotations
import datetime as dt, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
F = HERE / "roster.json"
ALIAS = {"인도": "인도자", "메인": "메인KB", "메인건반": "메인KB", "세컨": "세컨KB", "세컨건반": "세컨KB",
         "방송": "방송실", "단상": "단상싱어", "회중": "회중싱어", "싱어": "단상싱어"}


def day(s: str) -> str:
    s = s.replace("/", ".").replace("-", ".").rstrip(".")
    p = [int(x) for x in s.split(".")]
    if len(p) == 3: return dt.date(*p).isoformat()
    today = dt.date.today(); y = today.year + (1 if p[0] < today.month - 6 else 0)
    return dt.date(y, p[0], p[1]).isoformat()


def role(R: dict, r: str) -> str:
    r = ALIAS.get(r, r)
    if r not in [x for g in R["groups"] for x in g["roles"]]:
        sys.exit(f"[확인] '{r}' 역할이 없습니다 — 있는 역할: " + ", ".join(x for g in R["groups"] for x in g["roles"]))
    return r


def nth_sunday(x: str) -> int:
    return (int(x[8:]) - 1) // 7 + 1


def expected(R: dict, x: str, role: str) -> list[str]:
    """그 주 그 역할의 '평소' 편성 — 규칙(매월 n째 주) 우선, 없으면 기본값."""
    for r in R.get("rules", []):
        if r["role"] == role and nth_sunday(x) == r["nth"]: return r["names"]
    return R.get("defaults", {}).get(role, [])


def fill(R: dict, a: str, b: str | None) -> list[str]:
    """기본값이 있는 역할만 채운다. 이미 기본값과 다른 사람(교장님이 정하신 교체)은 그대로 둔다."""
    d0 = dt.date.fromisoformat(day(a)); d1 = dt.date.fromisoformat(day(b)) if b else d0 + dt.timedelta(weeks=8)
    out = []
    while d0 <= d1:
        x = d0.isoformat(); w = R["weeks"].setdefault(x, {})
        for role, base in R.get("defaults", {}).items():
            cur = w.get(role, [])
            if not cur or cur == base or any(cur == r["names"] for r in R.get("rules", []) if r["role"] == role):
                w[role] = expected(R, x, role)
        out.append(x); d0 += dt.timedelta(weeks=1)
    return out


def show(R: dict, start: str | None) -> None:
    d0 = dt.date.fromisoformat(start) if start else dt.date.today() + dt.timedelta(days=(6 - dt.date.today().weekday()) % 7)
    for k in range(6):
        x = (d0 + dt.timedelta(weeks=k)).isoformat(); w = R["weeks"].get(x, {})
        print(f"■ {int(x[5:7])}.{int(x[8:])}")
        for g in R["groups"]:
            for r in g["roles"]:
                print(f"  {r}: {', '.join(w.get(r, [])) or '—'}")
    print("지원팀: " + ", ".join(R.get("support", [])))


def rebuild(changed: list[str]) -> None:
    """바뀐 날짜가 6주 창에 들어가는 악보집만 다시 만들어 올린다."""
    for f in sorted((HERE / "data").glob("2*.json")):
        d0 = dt.date.fromisoformat(f.stem)
        if any(d0 <= dt.date.fromisoformat(c) < d0 + dt.timedelta(weeks=6) for c in changed):
            out = subprocess.run([sys.executable, str(HERE / "build.py"), f.stem, "--share"], capture_output=True, text=True).stdout.split()
            print(f"다시 올림: {f.stem} {out[-1] if out else ''}")


def main() -> int:
    a = [x for x in sys.argv[1:] if x != "--share"]
    R = json.loads(F.read_text()); cmd = a[0] if a else "show"; changed = []
    if cmd == "show":
        show(R, day(a[1]) if len(a) > 1 else None); return 0
    if cmd == "support":
        L = R.setdefault("support", [])
        if a[1] == "add" and a[2] not in L: L.append(a[2])
        if a[1] == "rm" and a[2] in L: L.remove(a[2])
        changed = list(R["weeks"])
        print("지원팀: " + ", ".join(L))
    elif cmd == "role":
        g = next(x for x in R["groups"] if x["name"] == a[2] or a[1] == "rm")
        if a[1] == "add": g["roles"].append(a[3])
        else:
            for x in R["groups"]: x["roles"] = [r for r in x["roles"] if r != a[2]]
        changed = list(R["weeks"])
    elif cmd == "fill":
        changed = fill(R, a[1], a[2] if len(a) > 2 else None)
        for x in changed:
            w = R["weeks"][x]; print(f"{int(x[5:7])}.{int(x[8:])} " + " · ".join(f"{r} {', '.join(w.get(r, []))}" for r in R.get("defaults", {})))
    elif cmd == "copy":
        R["weeks"][day(a[2])] = json.loads(json.dumps(R["weeks"].get(day(a[1]), {})))
        changed = [day(a[2])]
    else:
        x, r = day(a[1]), role(R, a[2]); w = R["weeks"].setdefault(x, {})
        names = [n.strip() for n in " ".join(a[3:]).split(",") if n.strip()]
        if cmd == "set": w[r] = names
        elif cmd == "add": w[r] = w.get(r, []) + [n for n in names if n not in w.get(r, [])]
        elif cmd == "rm": w[r] = [n for n in w.get(r, []) if n not in names] if names else []
        changed = [x]
        print(f"{int(x[5:7])}.{int(x[8:])} {r}: {', '.join(w[r]) or '—'}")
    R["weeks"] = dict(sorted(R["weeks"].items()))
    F.write_text(json.dumps(R, ensure_ascii=False, indent=1))
    if "--share" in sys.argv: rebuild(changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
