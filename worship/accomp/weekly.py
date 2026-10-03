#!/usr/bin/env python3
"""새 주일 악보집 열기 + 구글 드라이브 올리기 (2026-10-03 교장님 지시).

「예배 준비하자」(prep.py) 때 구글 슬라이드 악보를 복사하던 것을 이것으로 바꾼다.
  1) data/<날짜>.json 이 없으면 지난주 것을 바탕으로 새로 연다 — 표지 날짜만 바꾸고
     설교본문·설교요약·악보·공지는 비운다(주보·악보가 오면 채운다). 암송·사도신경은 그대로(암송 절은 날짜로 저절로 넘어감).
  2) 섬김표 기본값·규칙 채우기(roster.py fill — 교장님이 정하신 교체는 그대로)
  3) build.py --share → https://report-site-kohl.vercel.app/jegok_worship_YYYYMMDD
  4) 그 주일 드라이브 폴더에 「YYYY MMDD 예배자 악보.html」 올리기(있으면 새 내용으로 덮어씀, 예전 이름 「반주자 및 싱어용 악보」면 이름도 바꿈)

  python3 accomp/weekly.py 2026-10-11            # 열기 + 게시 + 드라이브
  python3 accomp/weekly.py 2026-10-11 --upload   # 이미 연 주를 다시 게시하고 드라이브 파일만 갱신
"""
from __future__ import annotations
import copy, json, subprocess, sys, uuid
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import prep  # noqa: E402

HTML_MIME = "text/html"


def open_week(d: date) -> bool:
    """새로 열었으면 True, 이미 있으면 False."""
    f = HERE / "data" / f"{d.isoformat()}.json"
    if f.exists():
        return False
    prev = sorted(p for p in (HERE / "data").glob("2*.json") if p.stem < d.isoformat())
    if not prev:
        raise SystemExit("바탕이 될 지난 악보집이 없습니다")
    base = json.loads(prev[-1].read_text())
    pages = []
    for p in base["pages"]:
        p = copy.deepcopy(p)
        if p["type"] == "cover":
            p["date"] = f"{d:%Y.%m.%d}"
        elif p["type"] == "sermon_text":
            p.update(ref="", title="", body="")
        elif p["type"] == "sermon_summary":
            p.update(left="", right="", title="", ref="")
        elif p["type"] == "scores":
            continue                      # 옛 형식 악보 쪽은 버리고 곡 번호 형식으로
        pages.append(p)
    if not any(p["type"] == "songs" for p in pages):   # 옛 형식이면 곡 묶음 자리를 만든다
        i = next(k for k, p in enumerate(pages) if p["type"] == "creed")
        pages[i:i] = [{"type": "songs", "group": "intro"}]
        pages += [{"type": "songs", "group": "main"}, {"type": "songs", "group": "apply"}]
    data = {"date": d.isoformat(), "title": f"{d:%Y %m%d} 예배자 악보", "source": "",
            "pages": pages, "songs": {"intro": [], "main": [], "apply": []}, "notices": []}
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    subprocess.run([sys.executable, str(HERE / "roster.py"), "fill", f"{d.month}.{d.day}",
                    f"{(d + timedelta(weeks=5)).month}.{(d + timedelta(weeks=5)).day}"], capture_output=True)
    return True


def publish(d: date) -> str:
    out = subprocess.run([sys.executable, str(HERE / "build.py"), d.isoformat(), "--share"],
                         capture_output=True, text=True, check=True).stdout.strip().splitlines()
    return out[-1]


def week_folder(g: prep.G, d: date) -> dict | None:
    q = f"'{prep.WORK_FOLDER}' in parents and name contains '{d:%Y %m%d} 주일예배' and mimeType = '{prep.FOLDER_MIME}' and trashed = false"
    res = g.get(f"{prep.DRIVE}/files", q=q, fields="files(id,name,webViewLink)", includeItemsFromAllDrives="true", pageSize=5)
    files = res.get("files", []) if isinstance(res, dict) else []
    return files[0] if files else None


def upload_html(g: prep.G, folder_id: str, d: date) -> dict:
    name = f"{d:%Y %m%d} 예배자 악보.html"   # 2026-10-03 교장님: 「반주자 및 싱어용 악보」 → 「예배자 악보」
    data = (HERE / "out" / f"{d.isoformat()}.html").read_bytes()
    old = g.find_child(folder_id, name) or g.find_child(folder_id, f"{d:%Y %m%d} 반주자 및 싱어용 악보.html")   # 예전 이름이면 덮어쓰며 이름도 바꾼다
    boundary = f"b{uuid.uuid4().hex}"
    meta = json.dumps({"name": name} if old else {"name": name, "parents": [folder_id], "mimeType": HTML_MIME}).encode()
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta +
            f"\r\n--{boundary}\r\nContent-Type: {HTML_MIME}\r\n\r\n".encode() + data + f"\r\n--{boundary}--".encode())
    if old:
        url = f"{prep.UPLOAD}/files/{old['id']}?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink"
        return {**g.req("PATCH", url, body, ctype=f"multipart/related; boundary={boundary}", timeout=600), "status": "updated"}
    url = f"{prep.UPLOAD}/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink"
    return {**g.req("POST", url, body, ctype=f"multipart/related; boundary={boundary}", timeout=600), "status": "created"}


def setup(d: date, g: prep.G | None = None, folder_id: str | None = None) -> dict:
    """prep.py 가 부른다. 반환: {opened, url, drive: {name, webViewLink, status}}"""
    g = g or prep.G(prep.access_token())
    opened = open_week(d)
    url = publish(d)
    if not folder_id:
        fo = week_folder(g, d)
        folder_id = fo["id"] if fo else None
    drive = upload_html(g, folder_id, d) if folder_id else {"status": "no-folder"}
    return {"opened": opened, "url": url, "drive": drive}


if __name__ == "__main__":
    d = date.fromisoformat(sys.argv[1])
    if "--upload" not in sys.argv:
        print("새로 엶" if open_week(d) else "이미 있음")
    r = setup(d)
    print(r["url"]); print(r["drive"].get("webViewLink", r["drive"]["status"]))
