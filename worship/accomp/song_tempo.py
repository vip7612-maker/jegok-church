#!/usr/bin/env python3
"""곡 빠르기 표 — 예배준비 화면 추천의 [전체·빠른곡·중간곡·느린곡·주제곡] 나누기 (2026-10-07 교장님).

  빠르기  콘티 추천(conti.py)이 매긴 값이 있으면 그것(여러 번이면 많이 나온 쪽), 없으면 Claude 가 한 번 매긴다.
  주제곡  깊이가 있어 여러 번 반복해 불러도 좋은 곡(교장님 정의) — Claude 가 한 번 가른다.
  고친 값  표에서 by 를 "manual" 로 두면 다시 돌려도 덮어쓰지 않는다.

표: report-site/jegok_worship/song_tempo.json  { 곡 열쇠(publish.song_key): {"t": 제목, "tempo": "빠른곡|중간곡|느린곡", "deep": bool, "by": "reco|claude|manual"} }

  python3 accomp/song_tempo.py            # 표에 없는 곡만 매긴다(publish.index_page 가 게시 때 부른다)
  python3 accomp/song_tempo.py --dry-run  # 매길 곡 수만
"""
from __future__ import annotations
import glob, json, os, re, subprocess, sys, tempfile, urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = Path.home() / "dev/daily-briefing/report-site/jegok_worship"
TABLE = SITE / "song_tempo.json"
TEMPOS = ("빠른곡", "중간곡", "느린곡")
CLAUDE = str(Path.home() / ".local/bin/claude")


def key(t: str) -> str:
    import publish
    return publish.song_key(t)


def from_reco() -> dict[str, tuple[str, str]]:
    """콘티 추천에 나온 곡의 빠르기 — 여러 주에 다르게 적혔으면 많이 나온 쪽."""
    seen: dict[str, Counter] = {}; title: dict[str, str] = {}
    for f in glob.glob(str(SITE / "reco" / "*.json")) + glob.glob(str(HERE.parent / "out" / "*-conti.json")):
        try: d = json.loads(Path(f).read_text())
        except Exception: continue
        d = d.get("rec", d) if isinstance(d, dict) else {}
        for g in ("ccm", "hymns"):
            for x in d.get(g) or []:
                if x.get("tempo") in TEMPOS and x.get("title"):
                    k = key(x["title"]); seen.setdefault(k, Counter())[x["tempo"]] += 1; title.setdefault(k, x["title"])
    return {k: (title[k], c.most_common(1)[0][0]) for k, c in seen.items()}


def all_titles() -> dict[str, str]:
    out = {}
    try:
        for s in json.load(urllib.request.urlopen("https://worship-desk.vercel.app/api/worship?songs=1", timeout=30)):
            if s.get("title"): out.setdefault(key(s["title"]), s["title"])
    except Exception as e:
        print("곡 목록 못 읽음:", e, file=sys.stderr)
    for k, (t, _) in from_reco().items(): out.setdefault(k, t)
    return out


PROMPT = """한국 교회 예배 찬양(CCM·새찬송가) 제목 목록입니다. 곡마다 빠르기와 주제곡 여부를 JSON 배열로만 답하세요. 설명은 쓰지 마세요.

- tempo: "빠른곡"(경쾌·박수·선포), "중간곡"(보통 걸음·고백), "느린곡"(묵상·기도·잔잔함) 중 하나. 예배에서 흔히 부르는 빠르기로.
- deep: 주제곡이면 true — 가사와 고백이 깊어 예배 중 여러 번 반복해 불러도 좋은 곡(묵상·헌신·고백의 깊이). 가볍게 여는 곡·어린이 율동곡은 false.
- 모르는 곡이면 제목의 말투와 가사 뜻으로 가장 그럴듯하게 고르되, "t" 는 아래 제목을 글자 그대로.

답 꼴: [{{"t": "제목", "tempo": "중간곡", "deep": true}}]

제목:
{titles}
"""


def classify(titles: list[str], run=None) -> dict[str, dict]:
    """Claude(맥미니 구독)에게 100곡씩. API 키는 넘기지 않는다."""
    out = {}
    for i in range(0, len(titles), 100):
        part = titles[i:i + 100]
        text = (run or _claude)(PROMPT.format(titles="\n".join(part)))
        m = re.search(r"\[.*\]", text, re.S)
        if not m: raise RuntimeError(f"JSON 못 받음: {text[:200]}")
        want = {key(t): t for t in part}
        for x in json.loads(m.group(0)):
            k = key(x.get("t", ""))
            if k in want and x.get("tempo") in TEMPOS:
                out[k] = {"t": want[k], "tempo": x["tempo"], "deep": bool(x.get("deep"))}
    return out


def _claude(prompt: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) and k != "CLAUDE_CODE_OAUTH_TOKEN"}
    r = subprocess.run([CLAUDE, "-p", prompt, "--output-format", "text"], capture_output=True, text=True, timeout=600, env=env, cwd=tempfile.gettempdir())
    return r.stdout or r.stderr


def build(table: dict, titles: dict[str, str], reco: dict[str, tuple[str, str]], cls: dict[str, dict]) -> dict:
    """표 합치기 — manual 은 그대로, 빠르기는 추천 값이 먼저, 주제곡은 Claude 값."""
    out = dict(table)
    for k, t in titles.items():
        old = out.get(k, {})
        if old.get("by") == "manual": continue
        c = cls.get(k) or {}
        tempo, by = (reco[k][1], "reco") if k in reco else (c.get("tempo") or old.get("tempo"), "claude")
        if not tempo: continue
        out[k] = {"t": old.get("t") or t, "tempo": tempo, "deep": bool(c["deep"]) if "deep" in c else bool(old.get("deep")), "by": by}
    return out


def update(dry: bool = False, run=None) -> str:
    table = json.loads(TABLE.read_text()) if TABLE.exists() else {}
    titles, reco = all_titles(), from_reco()
    todo = [t for k, t in titles.items() if k not in table]
    if dry: return f"표 {len(table)}곡 · 새로 매길 곡 {len(todo)}"
    cls = classify(todo, run) if todo else {}
    table = build(table, titles, reco, cls)
    # 추천 값이 새로 생긴 곡은 빠르기를 추천 값으로 맞춘다(manual 제외)
    for k, (t, tempo) in reco.items():
        if k in table and table[k].get("by") == "claude": table[k].update(tempo=tempo, by="reco")
    TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=0))
    return f"곡 빠르기 표 {len(table)}곡(새로 {len(cls)}) · 주제곡 {sum(1 for v in table.values() if v.get('deep'))}"


if __name__ == "__main__":
    print(update("--dry-run" in sys.argv))
