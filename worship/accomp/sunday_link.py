#!/usr/bin/env python3
"""주일 08:30 — 그 주 악보집 링크를 교장님 텔레그램으로 (2026-10-04 교장님 지시: 예배 잘 드리라는 말과 함께).

launchd com.nextra.jegok-sunday-link (매주 일 08:30). --dry 면 보내지 않고 찍기만.
그 주 쪽이 아직 안 올라와 있으면(404) 모음 주소를 보낸다.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://report-site-kohl.vercel.app"
BOT_ENV = os.path.expanduser("~/dev/next_api_bot/.env.local")


def env():
    out = {}
    for line in open(BOT_ENV, encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return out


def alive(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def main():
    d = date.today()
    url = f"https://worship-desk.vercel.app/jegok/{d:%Y%m%d}"   # 2026-10-07 새 주소
    if not alive(url + "/"):
        url = "https://worship-desk.vercel.app/jegok/"
    sermon = ""
    try:
        data = json.load(open(os.path.join(HERE, "data", f"{d:%Y-%m-%d}.json"), encoding="utf-8"))
        st = next((p for p in data["pages"] if p.get("type") == "sermon_text"), None)
        if st and st.get("title"):
            sermon = f"\n📖 오늘 말씀 · {st['title']} ({st.get('ref', '')})"
    except Exception:  # noqa: BLE001
        pass
    text = (f"🙏 교장님, 오늘도 은혜로운 주일 예배 드리세요.\n"
            f"준비하신 찬양 위에 하나님께서 함께하시길 기도합니다.{sermon}\n\n"
            f"🎼 오늘 예배 악보집\n{url}")
    if "--dry" in sys.argv:
        print(text)
        return
    e = env()
    data = urllib.parse.urlencode({"chat_id": e["ALLOWED_CHAT_IDS"].split(",")[0].strip(), "text": text,
                                   "disable_web_page_preview": "false"}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{e['TELEGRAM_BOT_TOKEN']}/sendMessage", data,
                                timeout=20) as r:
        print(d, "sent", json.load(r).get("ok"))


if __name__ == "__main__":
    main()
