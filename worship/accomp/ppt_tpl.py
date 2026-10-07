#!/usr/bin/env python3
"""예배 PPT 템플릿 — 한 번 만든 예배 PPT(2026-10-04)를 틀로 두고 날짜마다 새로 찍는다 (2026-10-03 교장님 지시).

드라이브에서 그 주 PPT 를 불러오지 않는다. 틀(accomp/ppt_template/: 장마다 배경 그림 + 글자 위치)을 복사해
  · 표지 날짜
  · 대표기도·봉헌·특송 맡은 분, 성경봉독(본문·봉독자) + 봉독 본문 장(개역개정), 설교 제목·설교자
  · 교회 소식 장
을 그 주 주보(accomp/jubo/<날짜>.hwp — jubo_in.py 가 둔다)로 바꿔 채우고, 찬양 자리에는 그 주 악보집 곡 틀(slides.add_song_frames)을 끼운다.
주보가 아직 없으면 날짜만 바꾸고 맡은 분·설교·봉독·소식 칸은 비워 둔다(지난주 이름이 남지 않게).
성경암송·사도신경·축도·마침 장은 틀 그대로.

  /usr/local/bin/python3 accomp/ppt_tpl.py save [worship_ppt/2026-10-04.pdf]   # 틀 만들기(한 번)
  /usr/local/bin/python3 accomp/ppt_tpl.py make 2026-10-11                     # 그 주 ppt.html (build.py --share 가 부른다)
"""
from __future__ import annotations
import copy, json, re, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
def _tpl_dir(n: int | None = None) -> Path:
    """예배 템플릿 N 의 PPT 틀(templates/template<N>/ppt). 번호가 없으면 지금 템플릿(templates/current.txt). 2026-10-03 교장님 지시."""
    cur = HERE / "templates" / "current.txt"
    n = n or (int(cur.read_text().strip().replace("template", "")) if cur.exists() else 0)
    d = HERE / "templates" / f"template{n}" / "ppt"
    return d if n and (d.exists() or cur.exists()) else HERE / "ppt_template"


TPL = _tpl_dir(int(sys.argv[sys.argv.index("--tpl") + 1]) if "--tpl" in sys.argv else None)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
BIBLE = Path.home() / "dev/next_api_bot/worker/bible_lookup.py"
KEYS = {"prayer": "Prayer", "news": "Announcements", "offering": "Offering", "reading": "ScriptureReading",
        "special": "SpecialPraise", "sermon": "Sermon"}


def flat(s: dict) -> str:
    return re.sub(r"\s", "", s["plain"])


def save(pdf: Path) -> None:
    import slides
    if TPL.exists(): shutil.rmtree(TPL)
    S = slides.parse(pdf, TPL)
    roles = {}
    for k, s in enumerate(S):
        for role, key in KEYS.items():
            if flat(s).startswith(key) or (key in flat(s)[:20] and role not in roles):
                roles.setdefault(role, k)
    # 봉독 본문 장 = 성경봉독 다음부터 특송 앞까지, 소식 장 = 교회소식 다음부터 봉헌 앞까지(그 사이 다른 표지가 나오기 전)
    roles["verse_bg"] = S[roles["reading"] + 1]["img"]
    roles["news_bg"] = S[roles["news"] + 1]["img"]
    drop = list(range(roles["reading"] + 1, roles["special"])) + list(range(roles["news"] + 1, roles["offering"]))
    keep = [s for k, s in enumerate(S) if k not in drop]
    for f in TPL.glob("*.jpg"):
        if f.name not in {s["img"] for s in keep} | {roles["verse_bg"], roles["news_bg"]}: f.unlink()
    (TPL / "slides.json").write_text(json.dumps({"source": pdf.name, "bg": {"verse_bg": roles["verse_bg"], "news_bg": roles["news_bg"]}, "slides": keep}, ensure_ascii=False))
    print(f"틀 저장: {len(S)}장 중 {len(keep)}장(봉독 본문·교회 소식 장은 주마다 새로) → {TPL}")


# ── 글자 줄 나누기 (틀 글꼴 크기에 맞춘 대략 폭) ─────────────────────────────
def text_w(s: str, size: float) -> float:
    w = 0.0
    for ch in s:
        w += size * (0.3 if ch == " " else 0.55 if ord(ch) < 0x1100 else 0.8)
    return w


def wrap(s: str, size: float, maxw: float = 1340) -> list[str]:
    out, cur = [], ""
    for word in s.split(" "):
        t = (cur + " " + word) if cur else word
        if text_w(t, size) <= maxw or not cur: cur = t
        else: out.append(cur); cur = word
    if cur: out.append(cur)
    return out


def pages(blocks: list[list[tuple[str, bool]]], size: float, step: int, gap: int, top: int = 55, bottom: int = 760) -> list[list[dict]]:
    """blocks = [[(줄, 굵게), …], …] → 장마다 글자 목록. 한 덩어리가 장을 넘으면 다음 장으로."""
    out, cur, y = [], [], top
    for b in blocks:
        need = len(b) * step
        if cur and y + need > bottom:
            out.append(cur); cur, y = [], top
        for ln, bold in b:
            if y + step > bottom + step and cur:
                out.append(cur); cur, y = [], top
            if ln.startswith("\x00"):                      # 봉독 단추(봉독대표·회중봉독·다함께 봉독) — 금빛 작은 단추, 절 바로 위
                lab = ln[1:]; ls = round(size * 0.5)
                cur.append({"x": 45, "y": y, "w": int(len(lab) * ls * 1.05) + 30, "h": ls, "s": ls, "c": "#3b2a06", "bg": "#f6c76b", "b": True, "t": lab, "a": "l"})
                y += ls + 18; continue
            cur.append({"x": 45, "y": y, "w": 1350, "h": int(size), "s": size, "c": "#ffffff", "b": bold, "t": ln, "a": "l"})
            y += step
        y += gap
    if cur: out.append(cur)
    return out


def verse_blocks(ref: str) -> list[list[tuple[str, bool]]]:
    r = subprocess.run([sys.executable, str(BIBLE), ref], capture_output=True, text=True)
    blocks = []
    for ln in r.stdout.splitlines()[1:]:
        m = re.match(r"\s*(\d+(?:-\d+)?)\s+(.*)", ln)
        if m:
            ls = wrap(f"{m.group(1)} {m.group(2).strip()}", 60)
            blocks.append([(x, i == 0) for i, x in enumerate(ls)])
    import pptfill                                         # 절마다 위에 누가 읽는지 — 원칙은 pptfill.read_label 하나 (2026-10-04 교장님)
    return [[("\x00" + pptfill.read_label(k, len(blocks)), True)] + b for k, b in enumerate(blocks)]


def news_blocks(lines: list[str]) -> list[list[tuple[str, bool]]]:
    blocks, cur = [], []
    for ln in lines:
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if not ln: continue
        if re.match(r"\d+\.", ln) and cur: blocks.append(cur); cur = []
        cur += [(x, bool(re.match(r"\d+\.", ln))) for x in wrap(ln, 53)]
    if cur: blocks.append(cur)
    return blocks


# ── 주보에서 읽기 ─────────────────────────────────────────────────────────
def jubo_info(date: str) -> dict:
    J = HERE / "jubo"
    h = next((J / f"{date}{x}" for x in (".hwp", ".hwpx") if (J / f"{date}{x}").exists()), None)
    if not h:
        return {}
    import jubo_form
    md, _ = jubo_form.kordoc(h.read_bytes()); d = jubo_form.parse(md)
    info = {"news": d.get("news", [])}
    for r in d.get("order", []):
        k = re.sub(r"\s", "", r[0]) if r else ""
        who = r[1].strip() if len(r) > 1 else ""; extra = r[3].strip() if len(r) > 3 else ""
        if k == "기도": info["prayer"] = who
        elif k == "봉헌": info["offering"] = who
        elif k == "성경봉독": info["reading"] = (who, extra)
        elif k == "찬양" and "special" not in info and who != "다같이": info["special"] = who
        elif k == "설교": info["sermon"] = (who, extra)
    return info


def set_main(s: dict, val: str, size_min: float = 40) -> None:
    """표지 장의 맡은 분(가운데 큰 갈색 글자) 바꾸기."""
    for t in s["texts"]:
        if t["s"] >= size_min and t["s"] < 100 and t["c"] != "#efe6dd":
            cx = t["x"] + t["w"] / 2   # 틀 글자의 가운데를 그대로(왼쪽 맞춤 틀이면 왼쪽 끝을 그대로)
            t["t"] = val; t["w"] = int(text_w(val, t["s"])) + 4
            if t.get("a") != "l": t["x"] = int(cx - t["w"] / 2)
            return


def set_small(s: dict, val: str) -> None:
    for t in s["texts"]:
        if 20 <= t["s"] < 40 and t["y"] > 520:   # 봉독자 이름은 36pt(틀 24pt 의 1.5배, 2026-10-04 교장님)
            cx = t["x"] + t["w"] / 2   # 틀 글자의 가운데를 그대로(왼쪽 맞춤 틀이면 왼쪽 끝을 그대로)
            t["t"] = val; t["w"] = int(text_w(val, t["s"])) + 4
            if t.get("a") != "l": t["x"] = int(cx - t["w"] / 2)
            return


def make(date: str, sid: str) -> Path:
    import slides, publish
    T = json.loads((TPL / "slides.json").read_text())
    S = copy.deepcopy(T["slides"])
    info = jubo_info(date)
    y, m, d = date.split("-")
    import order_sync                                   # 예배순서(예배준비 화면)가 기준 — 맡은 분·제목·본문은 순서 값이 주보보다 먼저 (2026-10-07 교장님)
    row = order_sync.load(date) if y != "2000" else None
    items = json.loads(row["items"]) if row and row.get("items") else None
    if items: info = order_sync.order_info(items, info)
    import weekday
    svc = "주일예배" if y == "2000" else weekday.service(date)
    out_slides = []
    for s in S:
        f = flat(s)
        if s is S[0]:
            for t in s["texts"]:
                if svc != "주일예배" and isinstance(t.get("t"), str) and re.sub(r"\s", "", t["t"]) == "주일예배":   # 새벽·수요·금요 표지
                    t["t"] = svc; s["plain"] = re.sub(r"주\s*일\s*예\s*배", svc, s["plain"])   # 목차도 그 이름으로
                if re.search(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일", t["t"]):
                    t["t"] = re.sub(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일", "○○○○년 ○○월 ○○일" if y == "2000" else f"{y}년 {m}월 {d}일", t["t"])
        if f.startswith(KEYS["prayer"]):
            set_main(s, info.get("prayer", ""))
        elif f.startswith(KEYS["offering"]):
            set_main(s, info.get("offering", ""))
        elif f.startswith(KEYS["special"]):
            set_main(s, info.get("special", ""))
        elif f.startswith(KEYS["sermon"]):
            who, title = info.get("sermon", ("", ""))
            set_main(s, title); set_small(s, who)
        elif f.startswith(KEYS["reading"]):
            who, ref = info.get("reading", ("", ""))
            set_main(s, ref); set_small(s, who)
            out_slides.append(s)
            main_ref = re.sub(r"\(.*?\)", "", ref).strip()
            if main_ref:
                main_ref = re.sub(r"^([가-힣]+)\s*", r"\1 ", main_ref)
                for txt in pages(verse_blocks(main_ref), 60, 70, 42):
                    out_slides.append({"n": 0, "w": s["w"], "h": s["h"], "img": "verse_bg", "texts": txt, "plain": "", "hidden": ""})
            continue
        elif f.startswith(KEYS["news"]):
            out_slides.append(s)
            for txt in pages(news_blocks(info.get("news", [])), 53, 63, 64, top=54):
                out_slides.append({"n": 0, "w": s["w"], "h": s["h"], "img": "news_bg", "texts": txt, "plain": "", "hidden": ""})
            continue
        out_slides.append(s)
    out_slides = order_sync.restructure(out_slides, items, info)   # 예배순서대로 표지·딸린 장을 다시 놓는다(없으면 템플릿 순서)
    folder = publish.SITE / "d" / sid; sd = folder / "slides"
    if sd.exists(): shutil.rmtree(sd)
    sd.mkdir(parents=True)
    for f_ in TPL.glob("*.jpg"): shutil.copy(f_, sd / f_.name)
    roles = _roles()
    for s in out_slides:
        if s["img"] == "verse_bg": s["img"] = roles["verse_bg"]
        if s["img"] == "news_bg": s["img"] = roles["news_bg"]
    for n, s in enumerate(out_slides, 1): s["n"] = n
    out_slides = slides.add_song_frames(out_slides, date, sd)
    out_slides = slides.add_extra(out_slides, date, sd)
    if y != "2000": print(order_sync.write_back(date, order_sync.sections(out_slides), row))   # PPT → 예배순서
    for s_ in out_slides: s_.pop("_sec", None)
    title = f"예배 PPT 템플릿 ({TPL.parent.name})" if y == "2000" else f"{int(m)}월 {int(d)}일 {svc} PPT"
    note = "" if info else '<span style="color:#fbbf24;font-size:12px">주보가 오면 맡은 분·설교·봉독·소식이 채워집니다</span>'
    # date= 를 꼭 넘긴다 — 빠지면 ＋ 장 넣기·교회 소식 고치기·끼운 장 불러오기가 모두 꺼진다(10/11 PPT 에서 빠졌던 것, 2026-10-07 교장님)
    (folder / "ppt.html").write_text(slides.render(out_slides, title, note, slides.song_titles(date), date=None if y == "2000" else date))
    for x in ("worship.pdf", "worship.pptx"): (folder / x).unlink(missing_ok=True)
    return folder


def _roles() -> dict:
    """틀 배경 그림 이름 — save 때 장 목록에서 빠진 봉독 본문·교회 소식 배경."""
    return json.loads((TPL / "slides.json").read_text())["bg"]


if __name__ == "__main__":
    a = [x for i, x in enumerate(sys.argv[1:], 1) if x not in ("--tpl", "--sid") and sys.argv[i - 1] not in ("--tpl", "--sid")]
    if a[0] == "save":
        save(Path(a[1]) if len(a) > 1 else HERE / "worship_ppt" / "2026-10-04.pdf")
    else:
        import publish
        sid = sys.argv[sys.argv.index("--sid") + 1] if "--sid" in sys.argv else publish.sid_for(a[1])
        print(make(a[1], sid))
