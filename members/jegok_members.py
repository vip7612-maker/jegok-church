#!/usr/bin/env python3
"""제곡교회 성도 명부 — 2025.12 교인주소현황(구글문서) + 교장님 주소록(개인·해밀) 을 한곳에 (2026-10-05 교장님 지시).

  · 원본 명부: private/members.json (개인정보 — 커밋·노션 지식창고 업로드 금지)
  · 주소록: 두 계정 모두 「⛪ 제곡교회」 그룹. 이미 있는 연락처는 그룹 표시만, 없던 분은 새로 만듦(소속 "제곡교회", 메모에 직분·구역·주소·가족)
  · 노션: 「⛪ 제곡교회 성도 명부」 DB (교장님 워크스페이스, 공유 안 함)

  python3 jegok_members.py contacts [--dry]   # 주소록 그룹 표시·추가
  python3 jegok_members.py notion             # 노션 DB 만들기/갱신
"""
import json, os, sys, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/dev/daily-briefing/contacts_cleanup")); import addrbook as ab
sys.path.insert(0, os.path.expanduser("~/dev/daily-briefing")); import notion_prayer as N
DATA = os.path.join(HERE, "private/members.json")
GROUP = "⛪ 제곡교회"
NOT_MEMBER = ("레미콘", "팬션", "슈퍼", "명성교회", "제곡유스2023")

def load(): return json.load(open(DATA, encoding="utf-8"))
def save(d): json.dump(d, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def group_rn(acct):
    for g in ab.api(acct, "GET", "/contactGroups?pageSize=200").get("contactGroups", []):
        if g.get("name") == GROUP: return g["resourceName"]
    return ab.api(acct, "POST", "/contactGroups", {"contactGroup": {"name": GROUP}})["resourceName"]

def memo(r):
    s = f"제곡교회 {r['title']} · {r['area']} · {r['addr']}".strip(" ·")
    if r.get("family"): s += f" · 가족: {r['family']}"
    return s + "  [2025.12 교인주소현황]"

def cmd_contacts(dry):
    d = load(); out = []
    extra_ph = [p for e in d["extra_contacts"] if not any(k in e["name"] for k in NOT_MEMBER) for p in e["phones"]]
    for acct in ab.ACCOUNTS:
        g = "(dry)" if dry else group_rn(acct)
        idx = {}
        for p in ab.fetch_all(acct):
            for x in p.get("phoneNumbers", []):
                n = ab.norm_phone(x.get("value"))
                if n: idx.setdefault(n, p["resourceName"])
        tag, new = [], []
        for r in d["records"]:
            n = ab.norm_phone(r["phone"]) if r["phone"] else None
            if not n: continue
            (tag if n in idx else new).append((r, idx.get(n)))
        tag += [(None, idx[ab.norm_phone(p)]) for p in extra_ph if ab.norm_phone(p) in idx]
        if not dry:
            if new:
                body = {"contacts": [{"contactPerson": {
                    "names": [{"unstructuredName": f"{r['name']} {r['title']} 제곡교회"}],
                    "phoneNumbers": [{"value": r["phone"], "type": "mobile"}],
                    "organizations": [{"name": "제곡교회", "title": r["title"]}],
                    "addresses": [{"formattedValue": r["addr"]}] if r["addr"] else [],
                    "biographies": [{"value": memo(r), "contentType": "TEXT_PLAIN"}],
                    "memberships": [{"contactGroupMembership": {"contactGroupResourceName": g}}]}} for r, _ in new],
                    "readMask": "names"}
                ab.api(acct, "POST", "/people:batchCreateContacts", body)
            rns = sorted({rn for _, rn in tag})
            for i in range(0, len(rns), 500):
                ab.api(acct, "POST", f"/{g}/members:modify", {"resourceNamesToAdd": rns[i:i+500]})
        out.append(f"{acct}: 그룹 표시 {len({rn for _, rn in tag})} · 새로 만듦 {len(new)} ({', '.join(r['name'] for r,_ in new)})")
    print("\n".join(out))

def cmd_notion():
    d = load(); cfg = json.load(open(N.CONFIG)); tok = N.token()
    db = cfg.get("jegok_members_database_id")
    if not db:
        r = N.api("POST", "/databases", tok, {"parent": {"type": "page_id", "page_id": cfg["page_id"]},
            "icon": {"type": "emoji", "emoji": "⛪"}, "title": N.rt("⛪ 제곡교회 성도 명부"),
            "properties": {"이름": {"title": {}}, "번호": {"number": {}}, "직분": {"select": {}}, "구역": {"select": {}},
                "주소": {"rich_text": {}}, "전화": {"phone_number": {}}, "가족": {"rich_text": {}},
                "출처": {"select": {"options": [{"name": "2025.12 교인주소현황"}, {"name": "주소록에만"}]}},
                "주소록": {"select": {"options": [{"name": "있음"}, {"name": "새로 추가"}, {"name": "전화 없음"}, {"name": "확인 필요"}]}},
                "메모": {"rich_text": {}}}})
        db = r["id"]; cfg["jegok_members_database_id"] = db; cfg["jegok_members_db_url"] = r["url"].replace("www.notion.so", "app.notion.com/p")
        json.dump(cfg, open(N.CONFIG, "w"), ensure_ascii=False, indent=2)
    exist = {}
    cur = None
    while True:
        q = N.api("POST", f"/databases/{db}/query", tok, {"start_cursor": cur} if cur else {})
        for p in q["results"]: exist["".join(t["plain_text"] for t in p["properties"]["이름"]["title"])] = p["id"]
        if not q.get("has_more"): break
        cur = q["next_cursor"]
    rows = []
    for r in d["records"]:
        st = {"phone": "있음", "name": "확인 필요", "none": "새로 추가"}[r["match"]] if r["phone"] else "전화 없음"
        rows.append((f"{r['name']} {r['title']}", {"번호": {"number": r["no"]}, "직분": {"select": {"name": r["title"] or "-"}},
            "구역": {"select": {"name": r["area"]}}, "주소": {"rich_text": N.rt(r["addr"])}, "전화": {"phone_number": r["phone"] or None},
            "가족": {"rich_text": N.rt(r["family"])}, "출처": {"select": {"name": "2025.12 교인주소현황"}}, "주소록": {"select": {"name": st}},
            "메모": {"rich_text": N.rt("주소록 이름: " + ", ".join(c["name"] for c in r.get("contacts", [])) if r["match"] == "name" else "")}}))
    for e in d["extra_contacts"]:
        if any(k in e["name"] for k in NOT_MEMBER): continue
        rows.append((e["name"], {"전화": {"phone_number": (e["phones"] or [None])[0]}, "출처": {"select": {"name": "주소록에만"}},
            "주소록": {"select": {"name": "있음"}}, "메모": {"rich_text": N.rt("12월 명단에 없음 — 가족·청소년·새가족인지 확인")}}))
    for name, props in rows:
        props["이름"] = {"title": N.rt(name)}
        if name in exist: N.api("PATCH", f"/pages/{exist[name]}", tok, {"properties": props})
        else: N.api("POST", "/pages", tok, {"parent": {"database_id": db}, "properties": props})
    print(len(rows), cfg["jegok_members_db_url"])

if __name__ == "__main__":
    c = sys.argv[1]
    if c == "contacts": cmd_contacts("--dry" in sys.argv)
    elif c == "notion": cmd_notion()
