#!/usr/bin/env python3
"""예배 구분 — 교회마다 관리자 화면에서 만들고 지우는 예배(주일예배1부·청년예배·새벽예배 …) (2026-10-07 교장님).

예배 한 번 = 「때(occ)」.  날짜만(YYYY-MM-DD) 또는 날짜-예배열쇠(YYYY-MM-DD-youth).
  · 처음부터 있던 네 가지(sun·wed·fri·dawn, legacy)는 날짜만 쓴다 — 10/8·10/11 자료·주소가 그대로 열린다.
  · 새로 만든 예배는 늘 날짜-열쇠. 같은 날 예배가 여럿이어도 준비·콘티·악보집·PPT 가 따로 간다.
주소는 YYYYMMDD 또는 YYYYMMDD-열쇠(/jegok/20261011-youth/).

표: 예배 DB wor_svc (church, id, name, days, time, place, tpl, ord, legacy, active)
  days = 요일 숫자 묶음(일0 월1 … 토6, 예: "12345"), time = "HH:MM", tpl = 그 예배 기본 예배순서 템플릿 이름(wor_tpl)
"""
from __future__ import annotations
import datetime as dt, re

CHURCH = "jegok"
OCC = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-([a-z0-9]{1,16}))?$")
D8 = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:-([a-z0-9]{1,16}))?$")
# 처음 있던 네 가지 — api/wadmin.js SEED_SVCS 와 같아야 한다
DEFAULT = [
    {"id": "sun", "name": "주일예배", "days": "0", "time": "10:30", "place": "", "tpl": "", "ord": 1, "legacy": 1},
    {"id": "wed", "name": "수요예배", "days": "3", "time": "19:30", "place": "", "tpl": "", "ord": 2, "legacy": 1},
    {"id": "fri", "name": "금요예배", "days": "5", "time": "19:30", "place": "", "tpl": "", "ord": 3, "legacy": 1},
    {"id": "dawn", "name": "새벽예배", "days": "12345", "time": "05:00", "place": "", "tpl": "", "ord": 4, "legacy": 1},
]
_cache: dict[str, list[dict]] = {}


def services(church: str = CHURCH, fresh: bool = False) -> list[dict]:
    """그 교회 예배 목록(쓰는 것만, 순서대로). DB 가 안 닿으면 처음 네 가지."""
    if church in _cache and not fresh: return _cache[church]
    out = []
    try:
        import wadmin
        rows = wadmin.batch([("SELECT id,name,days,time,place,tpl,ord,legacy FROM wor_svc WHERE church=? AND COALESCE(active,1)=1 ORDER BY ord, id", [church])])[0]
        out = [{**r, "ord": int(r.get("ord") or 0), "legacy": int(r.get("legacy") or 0), "days": r.get("days") or "",
                "time": r.get("time") or "", "place": r.get("place") or "", "tpl": r.get("tpl") or ""} for r in rows]
    except Exception:
        out = []
    _cache[church] = out or [dict(x) for x in DEFAULT]
    return _cache[church]


def split(occ: str) -> tuple[str, str | None]:
    m = OCC.match(str(occ or ""))
    if not m: raise ValueError(f"예배 때가 아님: {occ!r}")
    return m.group(1), m.group(2)


def ymd(occ: str) -> str:
    return split(occ)[0]


def wday(day: str) -> int:
    """일0 월1 … 토6 (JS getUTCDay 와 같게)."""
    return (dt.date.fromisoformat(day).weekday() + 1) % 7


def service_of(occ: str, svcs: list[dict] | None = None) -> dict:
    """그 때의 예배. 열쇠가 없으면 그 요일의 처음 예배(legacy 먼저), 그 요일 예배가 없으면 처음 네 가지 규칙."""
    svcs = svcs if svcs is not None else services()
    day, sid = split(occ)
    if sid:
        s = next((x for x in svcs if x["id"] == sid), None)
        return s or {"id": sid, "name": sid, "days": "", "time": "", "place": "", "tpl": "", "ord": 99, "legacy": 0}
    w = str(wday(day))
    on = [x for x in svcs if w in x.get("days", "")]
    on.sort(key=lambda x: (-int(x.get("legacy") or 0), int(x.get("ord") or 0)))
    if on: return on[0]
    return next(x for x in DEFAULT if w in x["days"] or x["id"] == "dawn")


def occ_of(day: str, sid: str, svcs: list[dict] | None = None) -> str:
    """날짜 + 예배 → 때. 처음 네 가지(legacy)는 날짜만."""
    svcs = svcs if svcs is not None else services()
    s = next((x for x in svcs if x["id"] == sid), None)
    return day if s and s.get("legacy") else f"{day}-{sid}"


def name(occ: str, svcs: list[dict] | None = None) -> str:
    return service_of(occ, svcs)["name"]


def d8(occ: str) -> str:
    day, sid = split(occ)
    return day.replace("-", "") + (f"-{sid}" if sid else "")


def from_d8(s: str) -> str:
    m = D8.match(str(s or ""))
    if not m: raise ValueError(f"주소의 날짜가 아님: {s!r}")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" + (f"-{m.group(4)}" if m.group(4) else "")


def occs_on(day: str, svcs: list[dict] | None = None) -> list[str]:
    """그 날 드리는 예배들의 때(순서대로)."""
    svcs = svcs if svcs is not None else services()
    w = str(wday(day))
    return [occ_of(day, x["id"], svcs) for x in sorted(svcs, key=lambda x: x["ord"]) if w in x.get("days", "")]
