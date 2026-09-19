#!/usr/bin/env python3
"""제곡교회 주일예배 찬양 준비 — 사전 세팅.

"예배 준비하자 / 사전 준비해" 라고 하면 이 스크립트가 다음 주일 폴더와 파일을 만들어 둔다.
  1) 다음 주일(오늘이 일요일이면 오늘) 날짜 계산
  2) 구글 드라이브 「2026 예배찬양」(공유 드라이브) 안에 폴더 생성:  "2026 0920 주일예배 이경진"   (기존 폴더 이름 규칙)
  3) 「예배준비 템플릿」의 두 파일을 그 폴더로 복사, 이름의 0000 을 MMDD 로:
       - 구글 슬라이드 "2026 0000 반주자 및 싱어용 악보"  → 표지 "2026.00.00" → "2026.09.20"   (Slides API replaceAllText)
       - 파워포인트   "2026 0000 주일예배 PPT" (.pptx)     → 표지 "2026년  00월 00일" → "2026년  09월 20일" (XML 직접 수정 후 업로드)
  4) 결과(폴더·파일 링크) 출력. --notify 면 텔레그램(경진비서방)에도.
이미 만들어진 폴더/파일이 있으면 다시 만들지 않는다(멱등).

사용:  python3 prep.py                      # 다음 주일
       python3 prep.py --date 2026-10-04    # 특정 주일
       python3 prep.py --leader 정영화       # 인도자 이름 (기본 이경진)
       python3 prep.py --suffix 부활주일     # 폴더명 뒤에 붙임 → "2026 0405 주일예배 이경진 부활주일"
       python3 prep.py --dry-run            # 만들 이름·날짜만 보여줌
인증: ~/dev/daily-briefing/.env 의 GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN (drive 스코프). 표준 라이브러리만 사용.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ENV_FILES = [Path.home() / "dev" / "daily-briefing" / ".env", Path.home() / "dev" / "next_api_bot" / ".env.local"]

WORK_FOLDER = "1sRJ7X8heOaM5BmDa0WW6Jvs__O2upcpV"        # 2026 예배찬양 (공유 드라이브)
TEMPLATE_FOLDER = "13opyfTn8EhcMI2LMN2FBtyhVXi9_qagD"    # 예배준비 템플릿
TEMPLATES = {
    # id: (표시 이름 규칙(0000→MMDD), 종류)
    "1lFzyXmz5EFVQLlkqj3XncYAmZ4ibYWX4L2E3jGdD2EE": ("2026 0000 반주자 및 싱어용 악보", "slides"),
    "1E_9hpG6pYuzbsew0uXnaZb1wDBwmgqhT": ("2026 0000 주일예배 PPT", "pptx"),
}
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
SLIDES = "https://slides.googleapis.com/v1"
DEFAULT_LEADER = "이경진"


def log(msg: str) -> None:
    print(msg, flush=True)


# ── 날짜·이름 ─────────────────────────────────────────────────
def next_sunday(today: date | None = None) -> date:
    """오늘 이후 가장 가까운 일요일(오늘이 일요일이면 오늘)."""
    today = today or datetime.now(KST).date()
    return today + timedelta(days=(6 - today.weekday()) % 7)


def folder_name(d: date, leader: str = DEFAULT_LEADER, suffix: str = "") -> str:
    name = f"{d:%Y %m%d} 주일예배 {leader}"
    return f"{name} {suffix.strip()}" if suffix.strip() else name


def file_name(template_name: str, d: date) -> str:
    return template_name.replace("0000", f"{d:%m%d}").replace("2026", f"{d:%Y}", 1)


def slides_replacements(d: date) -> list[dict]:
    return [{"replaceAllText": {"containsText": {"text": "2026.00.00", "matchCase": True},
                                "replaceText": f"{d:%Y.%m.%d}"}}]


def patch_pptx_date(pptx_bytes: bytes, d: date) -> tuple[bytes, int]:
    """표지의 '2026년  00월 00일' — 런이 ['2026년  ','00','월 ','00','일 …'] 로 나뉘어 있어 문단 단위로 다룬다.
    '2026년' 이 든 문단 안의 <a:t>00</a:t> 를 순서대로 월·일로 바꾼다. (바뀐 런 수 반환)"""
    src = zipfile.ZipFile(io.BytesIO(pptx_bytes))
    out_buf = io.BytesIO()
    changed = 0
    mm, dd = f"{d:%m}", f"{d:%d}"
    with zipfile.ZipFile(out_buf, "w") as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if re.match(r"ppt/slides/slide\d+\.xml$", info.filename):
                text = data.decode("utf-8")
                def fix_para(m):
                    nonlocal changed
                    p = m.group(0)
                    if not re.search(r"20\d\d년", p):
                        return p
                    vals = iter([mm, dd])
                    def sub(mt):
                        nonlocal changed
                        v = next(vals, None)
                        if v is None:
                            return mt.group(0)
                        changed += 1
                        return f"<a:t>{v}</a:t>"
                    p = re.sub(r"<a:t>00</a:t>", sub, p)
                    # 연도가 다른 해면 연도도 맞춘다
                    p = re.sub(r"(<a:t>)20\d\d(년)", rf"\g<1>{d:%Y}\g<2>", p)
                    return p
                text = re.sub(r"<a:p>.*?</a:p>", fix_para, text, flags=re.S)
                data = text.encode("utf-8")
            # 압축 방식 유지(mimetype 류는 그대로)
            out.writestr(info, data)
    return out_buf.getvalue(), changed


# ── 구글 API ─────────────────────────────────────────────────
class G:
    def __init__(self, token: str):
        self.t = token

    def req(self, method: str, url: str, body=None, ctype="application/json", timeout=120):
        data = None
        if body is not None:
            data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.t}", **({"Content-Type": ctype} if data is not None else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw.decode()) if raw and r.headers.get_content_type() == "application/json" else raw
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {url.split('?')[0]} → HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")

    def get(self, url, **params):
        params.setdefault("supportsAllDrives", "true")
        return self.req("GET", url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params))

    def find_child(self, parent: str, name: str, mime: str | None = None) -> dict | None:
        q = f"'{parent}' in parents and name = '{name}' and trashed = false"
        if mime:
            q += f" and mimeType = '{mime}'"
        res = self.get(f"{DRIVE}/files", q=q, fields="files(id,name,mimeType,webViewLink)", includeItemsFromAllDrives="true", pageSize=5)
        files = res.get("files", []) if isinstance(res, dict) else []
        return files[0] if files else None

    def create_folder(self, parent: str, name: str) -> dict:
        return self.req("POST", f"{DRIVE}/files?supportsAllDrives=true&fields=id,name,webViewLink",
                        {"name": name, "mimeType": FOLDER_MIME, "parents": [parent]})

    def copy(self, file_id: str, parent: str, name: str) -> dict:
        return self.req("POST", f"{DRIVE}/files/{file_id}/copy?supportsAllDrives=true&fields=id,name,webViewLink",
                        {"name": name, "parents": [parent]})

    def download(self, file_id: str) -> bytes:
        return self.req("GET", f"{DRIVE}/files/{file_id}?alt=media&supportsAllDrives=true", timeout=300)

    def upload_pptx(self, parent: str, name: str, data: bytes) -> dict:
        boundary = f"b{uuid.uuid4().hex}"
        meta = json.dumps({"name": name, "parents": [parent], "mimeType": PPTX_MIME}).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta +
                f"\r\n--{boundary}\r\nContent-Type: {PPTX_MIME}\r\n\r\n".encode() + data + f"\r\n--{boundary}--".encode())
        return self.req("POST", f"{UPLOAD}/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink",
                        body, ctype=f"multipart/related; boundary={boundary}", timeout=600)

    def slides_batch(self, pres_id: str, requests: list[dict]) -> dict:
        return self.req("POST", f"{SLIDES}/presentations/{pres_id}:batchUpdate", {"requests": requests})


def load_env() -> None:
    for p in ENV_FILES:
        try:
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except FileNotFoundError:
            pass


def access_token() -> str:
    load_env()
    need = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"구글 인증 정보 없음: {', '.join(missing)} ({ENV_FILES[0]})")
    data = urllib.parse.urlencode({"client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                                   "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST"), timeout=30) as r:
        j = json.loads(r.read().decode())
    if "access_token" not in j:
        raise RuntimeError(f"구글 토큰 갱신 실패: {j.get('error')} — `node ~/dev/next_api_bot/scripts/google-auth.mjs` 로 재인증 필요")
    return j["access_token"]


# ── 본 작업 ───────────────────────────────────────────────────
def prepare(d: date, leader: str, suffix: str, dry_run: bool = False, g: G | None = None) -> dict:
    fname = folder_name(d, leader, suffix)
    plan = {"date": d.isoformat(), "folder": fname, "files": [file_name(n, d) for n, _ in TEMPLATES.values()]}
    if dry_run:
        return {**plan, "dry_run": True}
    g = g or G(access_token())

    folder = g.find_child(WORK_FOLDER, fname, FOLDER_MIME)
    if folder:
        log(f"📁 폴더 이미 있음: {fname}")
    else:
        folder = g.create_folder(WORK_FOLDER, fname)
        log(f"📁 폴더 생성: {fname}")
    fid = folder["id"]
    results = []
    for tid, (tname, kind) in TEMPLATES.items():
        name = file_name(tname, d)
        exists = g.find_child(fid, name)
        if exists:
            log(f"  ⏭ 이미 있음: {name}")
            results.append({"name": name, "link": exists.get("webViewLink"), "status": "exists"})
            continue
        if kind == "slides":
            f = g.copy(tid, fid, name)
            rep = g.slides_batch(f["id"], slides_replacements(d))
            n = sum(r.get("replaceAllText", {}).get("occurrencesChanged", 0) for r in rep.get("replies", []))
            log(f"  ✅ 슬라이드 복사: {name} (표지 날짜 {n}곳 → {d:%Y.%m.%d})")
            results.append({"name": name, "link": f.get("webViewLink"), "status": "copied", "date_edits": n})
        else:
            raw = g.download(tid)
            patched, n = patch_pptx_date(raw, d)
            f = g.upload_pptx(fid, name, patched)
            log(f"  ✅ PPT 복사: {name} ({len(patched)//1024}KB, 표지 날짜 런 {n}곳 → {d:%Y}년 {d:%m}월 {d:%d}일)")
            results.append({"name": name, "link": f.get("webViewLink"), "status": "copied", "date_edits": n})
    return {**plan, "folder_link": folder.get("webViewLink") or f"https://drive.google.com/drive/folders/{fid}", "results": results}


def summary(res: dict) -> str:
    d = date.fromisoformat(res["date"]); wd = "월화수목금토일"[d.weekday()]
    lines = [f"🎵 {d:%m/%d}({wd}) 주일예배 준비 세팅 완료" if not res.get("dry_run") else f"🎵 {d:%m/%d}({wd}) 준비 계획(dry-run)",
             f"📁 {res['folder']}"]
    if res.get("folder_link"):
        lines.append(res["folder_link"])
    for r in res.get("results", []):
        mark = "✅" if r["status"] == "copied" else "⏭"
        lines.append(f"{mark} {r['name']}" + (f" (표지 날짜 {r.get('date_edits',0)}곳 수정)" if r["status"] == "copied" else " — 이미 있음"))
        if r.get("link"):
            lines.append(f"   {r['link']}")
    if res.get("dry_run"):
        lines += [f"  · {n}" for n in res["files"]]
    return "\n".join(lines)


def notify(text: str) -> bool:
    env = Path.home() / "dev" / "daily-briefing" / ".env"
    tok = None
    try:
        for line in open(env, encoding="utf-8"):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"'); break
    except FileNotFoundError:
        pass
    if not tok:
        log("텔레그램 생략: 토큰 없음"); return False
    chat = os.environ.get("TELEGRAM_NOTIFY_CHAT", "8047286046")
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20) as r:
            return bool(json.loads(r.read().decode()).get("ok"))
    except Exception as e:  # noqa: BLE001
        log(f"텔레그램 실패: {e}"); return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="주일예배 찬양 준비 사전 세팅")
    ap.add_argument("--date", help="예배 날짜 YYYY-MM-DD (기본: 다음 주일)")
    ap.add_argument("--leader", default=DEFAULT_LEADER)
    ap.add_argument("--suffix", default="", help="폴더명 뒤에 붙일 말 (예: 부활주일)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--notify", action="store_true", help="결과를 텔레그램(경진비서방)으로도 보냄")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    d = date.fromisoformat(a.date) if a.date else next_sunday()
    if d.weekday() != 6:
        log(f"⚠️ {d} 는 일요일이 아닙니다 (그대로 진행)")
    try:
        res = prepare(d, a.leader, a.suffix, dry_run=a.dry_run)
    except Exception as e:  # noqa: BLE001
        log(f"❌ 실패: {e}")
        return 1
    text = summary(res)
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else "\n" + text)
    if a.notify and not a.dry_run:
        notify(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
