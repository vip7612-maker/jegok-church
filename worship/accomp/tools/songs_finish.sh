#!/bin/zsh
# 곡 올리기 + 실패 PPT 다시 읽기가 끝나면 → 새로 찾은 곡까지 한 번 더 올리고 → 교장님 텔레그램으로 결과 (2026-10-05)
cd ~/dev/jegok-church/worship/accomp
while pgrep -f "migrate.py songs" >/dev/null || pgrep -f "songbank.py scan" >/dev/null; do sleep 60; done
/usr/local/bin/python3 -u migrate.py songs --new --small >> songppt/migrate_all.log 2>&1
/usr/local/bin/python3 - <<'PY'
import sys, re, json
sys.path.insert(0, "/Users/kj.lee/dev/daily-briefing"); sys.path.insert(0, ".")
import mail_watch, store as S
st = S.stats()
r = open("songppt/scan_retry.log").read()
ok = len(re.findall(r"곡 새로", r)); bad = re.findall(r"\] (\S+) .*?: 실패 (\w+): (.{0,60})", r)
fail = len(re.findall(r"✗", open("songppt/migrate_all.log").read()))
auto = S.sql("SELECT SUM(auto_sub) a FROM song_slides")[0]["a"]
t = (f"🎼 제곡교회 찬양 PPT 데이터 올리기 끝났습니다.\n\n"
     f"• 플랫폼 곡: {st['곡']}곡 · {st['곡 장']}장\n"
     f"• 그림 창고: {st['용량MB']}MB\n"
     f"• 실패했던 PPT 10개 → 다시 읽음 {ok}개" + (f" · 여전히 실패 {len(bad)}개 ({', '.join(b[0] for b in bad)})" if bad else "") + "\n"
     + (f"• 올리다 실패한 곡 {fail}개(로그 남김)\n" if fail else "")
     + f"• AI 번역 자막 검토 필요 {auto}장\n\n"
     "https://report-site-kohl.vercel.app/jegok_worship/song.html")
mail_watch.telegram(t)
PY
