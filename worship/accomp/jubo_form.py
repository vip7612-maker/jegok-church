#!/usr/bin/env python3
"""주보 → 양식 그대로의 HTML (hwp-to-html 스킬 「양식 있음」 방식, 2026-10-03 교장님 지시).

주보는 A4 가로 두 면, 면마다 3단(접는 주보)이다. 원본 PDF 를 그림으로 깔고(.trace)
그 위에 같은 자리·크기·색으로 HTML 을 짠다. 글은 한글 파일(kordoc)에서, kordoc 이 못 읽는
글상자(교회를 섬기는 분들·헌금 계좌)와 글자 색은 PDF 에서 가져온다.

  /usr/local/bin/python3 accomp/jubo_form.py 2026-10-04            # 드라이브에서 받아 만들고 공유
  /usr/local/bin/python3 accomp/jubo_form.py 2026-10-04 --no-share

결과: ~/Documents/주보/YYYYMMDD_제곡교회_주보.html (저장 단추 네 개 달린 편집본)
      + 공유본 report-site/d/<id>/ (HWPX·PDF 다운로드) — 악보집 [주보] 단추가 여기로 간다.
"""
from __future__ import annotations
import base64, html, io, json, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = Path.home() / "Documents" / "주보"
SAVEBAR = Path.home() / "dev/daily-briefing/docsave/savebar.js"
SITE = "https://report-site-kohl.vercel.app"
E = html.escape


# ── 원본 읽기 ────────────────────────────────────────────────────────────
def fetch(date: str) -> tuple[bytes, bytes, str]:
    """그 주 주보 PDF·HWP — 맥미니 accomp/jubo/<날짜>.* 가 있으면 그것(2026-10-03부터 드라이브 폴더 없이), 없으면 드라이브 폴더."""
    J = HERE / "jubo"
    lp, lh = J / f"{date}.pdf", next((J / f"{date}{x}" for x in (".hwp", ".hwpx") if (J / f"{date}{x}").exists()), None)
    if lp.exists() and lh:
        return lp.read_bytes(), lh.read_bytes(), f"{date.replace('-', '')} 주일 주보.pdf"
    import datetime as dt
    sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
    import prep, weekly
    g = prep.G(prep.access_token()); fo = weekly.week_folder(g, dt.date.fromisoformat(date))
    if not fo: raise SystemExit("그 주 드라이브 폴더가 없습니다")
    r = g.get(f"{prep.DRIVE}/files", q=f"'{fo['id']}' in parents and trashed=false and name contains '주보'",
              fields="files(id,name,mimeType,modifiedTime)", includeItemsFromAllDrives="true")
    fs = sorted(r.get("files", []), key=lambda f: f["modifiedTime"], reverse=True)
    pdf = next((f for f in fs if f["name"].lower().endswith(".pdf")), None)
    hwp = next((f for f in fs if f["name"].lower().endswith(".hwp") or f["name"].lower().endswith(".hwpx")), None)
    if not pdf or not hwp: raise SystemExit("주보 PDF·HWP 가 둘 다 있어야 합니다")
    return g.download(pdf["id"]), g.download(hwp["id"]), pdf["name"]


def kordoc(hwp: bytes) -> tuple[str, dict[str, bytes]]:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "jubo.hwp"; src.write_bytes(hwp); md = Path(td) / "jubo.md"
        subprocess.run(["npx", "-y", "kordoc@^4", str(src), "-o", str(md)], capture_output=True, timeout=600, cwd=td)
        if not md.exists(): raise SystemExit("kordoc 변환 실패")
        imgs = {p.name: p.read_bytes() for p in (Path(td) / "images").glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")}
        return md.read_text(), imgs


def pdf_info(pdf: bytes) -> dict:
    """PDF 에서 — 쪽 그림(배경 대조용), 표지 사진 칸(글자를 지운 그림), 글상자 글, 색 있는 줄."""
    import fitz
    from PIL import Image
    doc = fitz.open(stream=pdf, filetype="pdf")
    trace = []
    for pg in doc:
        b = io.BytesIO(); Image.open(io.BytesIO(pg.get_pixmap(dpi=100).tobytes("png"))).convert("RGB").save(b, "JPEG", quality=70)
        trace.append(b.getvalue())
    p2 = doc[1]
    lines = [(l["bbox"], "".join(s["text"] for s in l["spans"]), l["spans"]) for b in p2.get_text("dict")["blocks"] for l in b.get("lines", [])]
    # 교회를 섬기는 분들(왼쪽·오른쪽 두 줄기)과 헌금 계좌 — kordoc 이 읽지 못하는 글상자
    staff_l = [t.strip() for bb, t, _ in lines if 240 < bb[0] < 362 and 525 < bb[1] < 590 and t.strip()]
    staff_r = [t.strip() for bb, t, _ in lines if 362 <= bb[0] < 530 and 525 < bb[1] < 590 and t.strip()]
    accts = [t.strip() for bb, t, _ in lines if bb[0] < 230 and bb[1] > 550 and t.strip()]
    purple = {re.sub(r"\s+", "", s["text"]) for bb, t, sp in lines for s in sp if s["color"] == 0x9d5cbb and s["text"].strip()}
    # 표지 칸: 글자를 지우고(배경·사진만) 오른쪽 단을 잘라 낸다
    tmp = fitz.open(stream=pdf, filetype="pdf"); q = tmp[1]
    for bb, t, _ in [(l["bbox"], 0, 0) for b in q.get_text("dict")["blocks"] for l in b.get("lines", [])]:
        if bb[0] > 525: q.add_redact_annot(fitz.Rect(bb))
    q.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    pm = q.get_pixmap(dpi=150, clip=fitz.Rect(842 * 186.8 / 297, 0, 842, 595))
    b = io.BytesIO(); Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB").save(b, "JPEG", quality=78)
    MM = 297 / 842
    p1 = doc[0]
    sam_y = {}
    for blk in p1.get_text("dict")["blocks"]:
        for l in blk.get("lines", []):
            t = "".join(x["text"] for x in l["spans"]).strip()
            if l["bbox"][0] > 590 and t[:1] and "①" <= t[0] <= "⑳": sam_y.setdefault(t[0], l["bbox"][1] * MM)
    news_y = {}
    for bb, t, _ in lines:
        m = re.match(r"^\s*(\d+)\.", t)
        if bb[0] < 40 and m: news_y.setdefault(int(m.group(1)), bb[1] * MM)
    return {"sam_y": sam_y, "news_y": news_y, "trace": trace, "cover": b.getvalue(), "staff": (staff_l, staff_r), "accts": accts, "purple": purple}


# ── 마크다운 나누기 ────────────────────────────────────────────────────────
def rows(tbl: str) -> list[list[str]]:
    return [[c.strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)] for tr in re.findall(r"<tr>(.*?)</tr>", tbl, re.S)]


def parse(md: str) -> dict:
    tables = re.findall(r"<table>.*?</table>", md, re.S)
    texts = re.split(r"<table>.*?</table>", md, flags=re.S)
    d: dict = {}
    for t in tables:
        rs = rows(t); flat = " ".join(" ".join(r) for r in rs)
        if "예배인도" in flat or ("설교" in flat and "축도" in flat): d["order"] = rs
        elif "교회창립" in flat: d["mast"] = rs
        elif "읽기표" in flat: d["read"] = rs
        elif "섬김이" in flat: d["serve"] = rs
        elif "수요예배" in flat: d["wed"] = rs
    body = "\n".join(texts)
    m = re.search(r"오늘의 말씀\s*\n(.*?)\n\s*샘터모임\s*\n(.*?)(?=\n\s*$|\Z)", texts[1] if len(texts) > 1 else body, re.S)
    word, sam = (m.group(1), m.group(2)) if m else ("", "")
    wl = [x.strip() for x in word.split("\n") if x.strip()]
    d["s_title"] = wl[0] if wl else ""
    d["s_ref"] = wl[1] if len(wl) > 1 and wl[1].startswith("(") else ""
    d["s_body"] = wl[2:] if d["s_ref"] else wl[1:]
    d["sam"] = [x.strip() for x in sam.split("\n") if x.strip()]
    m = re.search(r"교회소식\s*\n(.*?)(?:!\[image\]|\Z)", body, re.S)
    d["news"] = [x.rstrip() for x in (m.group(1) if m else "").split("\n") if x.strip()]
    return d


# ── 블록 그리기 ────────────────────────────────────────────────────────────
def order_html(rs: list[list[str]]) -> str:
    top = [r[0] for r in rs if len(r) == 1 or (r and not any(r[1:]))]
    items = [r for r in rs if len(r) > 1 and any(r[1:])]
    lead = top[:4] + [""] * 4
    tail = top[4:]
    h1 = lead[2].split("<br>")
    li = ""
    for r in items:
        who = r[1].replace("다같이", "다 같 이")
        note = " ".join(x for x in r[2:] if x)
        nm = "".join(f"<i>{E(ch)}</i>" for ch in re.sub(r"\s", "", r[0]))
        li += f'<div class="or"><span class="on">{nm}</span><span class="ow">{E(who)}</span><span class="ot">{E(note)}</span></div>'
    tl = []
    for t in tail:
        ps = t.split("<br>")
        tl += [f'<p class="cf1">{E(x)}</p>' for x in ps if "애찬" not in x] + [f'<p class="cf2">{E(x)}</p>' for x in ps if "애찬" in x]
    tm = re.sub(r"(\d+)", r"<b>\1</b>", E(lead[3]))
    return (f'<p class="c1h">{E(lead[0])}</p><p class="c1v">{E(lead[1])}</p><hr class="dots">'
            f'<p class="c1s">{E(h1[0])}</p><p class="c1t">{E(h1[-1])}</p><p class="c1m">{tm}</p>'
            f'<div class="olist">{li}</div><div class="cfoot">{"".join(tl)}</div>')


def sermon_html(d: dict) -> str:
    def bold(s: str) -> str:
        s = E(s)
        return re.sub(r"((?:첫째|둘째|셋째|넷째|다섯째),[^.]*?습니다\.)", r"<b>\1</b>", s)
    return (f'<h2 class="ph">오늘의 말씀</h2><p class="st">{E(d["s_title"])}</p><p class="sr">{E(d["s_ref"])}</p>'
            f'<div class="sb fit">' + "".join(f"<p>{bold(x)}</p>" for x in d["s_body"]) + "</div>")


def sam_html(lines: list[str], ys: dict | None = None) -> str:
    groups = []
    for x in lines:
        if re.match(r"^[①-⑳]", x) or not groups: groups.append([x])
        else: groups[-1].append(x)
    if ys and all(g[0][0] in ys for g in groups):
        out = ""
        for g in groups:
            body = sam_flow(g)
            out += f'<div class="sg" style="top:{ys[g[0][0]] - 6.9 - .55:.2f}mm">{body}</div>'
        return '<h2 class="ph">샘터모임</h2>' + out
    return '<h2 class="ph">샘터모임</h2><div class="sam fit">' + sam_flow(lines) + "</div>"


def sam_flow(lines: list[str]) -> str:
    out = []; prayer = False
    for s in lines:
        e = E(s)
        if re.match(r"^[①-⑳]", s):
            prayer = "기도문으로 기도" in s
            out.append(f'<p class="si">{e}</p>')
        elif s.startswith("- "): out.append(f'<p class="sq">- {E(s[2:])}</p>')
        elif prayer: out.append(f'<p class="sp">{e}</p>')
        else: out.append(f'<p class="sh">{e}</p>')
    return "".join(out)


def news_html(lines: list[str], purple: set[str], ys: dict | None = None) -> str:
    nums = [int(re.match(r"^(\d+)\.", x).group(1)) for x in lines if re.match(r"^\d+\.\s", x)]
    anchored = bool(ys) and all(n in ys for n in nums)
    out = []
    for s in lines:
        e = E(s.strip())
        m = re.match(r"^(\d+)\.\s", s)
        if m and anchored:
            if out: out.append("</div>")
            out.append(f'<div class="ng" style="top:{ys[int(m.group(1))] - .75:.2f}mm"><p class="nh">{e}</p>')
        elif m: out.append(f'<p class="nh">{e}</p>')
        else:
            k = re.sub(r"\s+", "", s)
            cls = "nb pu" if k and any(k.startswith(p) or p.startswith(k) for p in purple if len(p) > 6) else "nb"
            e = re.sub(r"(\S+?\(\S+?\))([가-힣]{2,4})(집사|장로|권사|성도|형제|자매|선교사|사모)", r"\1\2<small>\3</small>", e)
            out.append(f'<p class="{cls}">{e}</p>')
    if anchored:
        return '<div class="pill">교 회 소 식</div>' + "".join(out) + ("</div>" if out else "")
    return '<div class="pill">교 회 소 식</div><div class="news fit">' + "".join(out) + "</div>"


def grid(rs: list[list[str]], cls: str) -> str:
    body = [r for r in rs if len(r) > 1]
    h = "".join(f"<th>{c}</th>" for c in body[0])
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in body[1:])
    return f'<table class="{cls}"><tr>{h}</tr>{trs}</table>'


def col2_html(d: dict, qr: str, staff) -> str:
    rd, sv, wd = d.get("read", []), d.get("serve", []), d.get("wed", [])
    one = lambda rs, i: rs[i][0] if len(rs) > i and len(rs[i]) == 1 else ""
    wl = (wd[0][0].split("<br>") if wd else ["| 수요예배"])
    sl, sr = staff
    lst = lambda xs: "".join(f"<p>{E(x)}</p>" for x in xs)
    return (f'<h3 class="sec" style="top:16.5mm">{E(one(rd,0).lstrip("| "))}</h3>'
            f'<p class="intro" style="top:24.5mm">{one(rd,1)}</p><p class="wk" style="top:36mm">{E(one(rd,2))}</p>'
            f'<div style="position:absolute;top:41.6mm;left:0;right:0">{grid(rd, "rt")}</div>'
            f'<h3 class="sec" style="top:75.6mm">{E(one(sv,0).lstrip("| "))}</h3><p class="wk" style="top:84.6mm">{E(one(sv,1))}</p>'
            f'<div style="position:absolute;top:90.2mm;left:0;right:0">{grid(sv, "svt")}</div>'
            f'<h3 class="sec" style="top:140.2mm">{E(wl[0].lstrip("| "))}</h3>'
            f'<p class="wed" style="top:147.6mm">{E(" ".join(wl[1:]))}</p>'
            f'<div class="qr" style="top:157.6mm"><img src="{qr}" alt="암송 큐알"><p>{(wd[-1][-1] if wd else "")}</p></div>'
            f'<h4 class="sv" style="top:179.6mm">| 교회를 섬기는 분들</h4>'
            f'<div class="staff" style="top:188mm"><div>{lst(sl)}</div><div>{lst(sr)}</div></div>')


def cover_html(rs: list[list[str]]) -> str:
    head = rs[0] if rs else ["", ""]
    m = re.match(r"(교회창립\S*)\s+(.*)", head[0]); found, date = (m.group(1), m.group(2)) if m else (head[0], "")
    vol = head[1] if len(head) > 1 else ""
    cells = [r[0] for r in rs[1:] if r and r[0]]
    motto, name = (cells[0].split("<br>") + [""])[:2] if cells else ("", "")
    desc = cells[1] if len(cells) > 1 else ""
    foot = (cells[2].split("<br>") if len(cells) > 2 else [])
    f0 = foot[0] if foot else ""; mm = re.match(r"(대한예수교장로회)\s*(.*)", f0)
    return (f'<p class="cv-top"><span>{E(found)}</span></p><p class="cd">{E(date)}</p><p class="cvol">{E(vol)}</p>'
            f'<p class="cv-mot">{E(motto)}</p><p class="cv-name">{E(name)}</p><p class="cv-desc">{desc}</p>'
            f'<div class="cv-foot"><p><small>{E(mm.group(1) if mm else "")}</small> <b>{E(mm.group(2) if mm else f0)}</b></p>'
            + "".join(f"<p>{E(x)}</p>" for x in foot[1:]) + "</div>")


def b64(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def small_qr(imgs: dict[str, bytes]) -> bytes:
    from PIL import Image
    for k, v in imgs.items():
        im = Image.open(io.BytesIO(v))
        if abs(im.width - im.height) < 5 and im.width <= 1200:
            b = io.BytesIO(); im.convert("RGB").resize((300, 300)).save(b, "PNG"); return b.getvalue()
    return b""


def render(date: str, d: dict, info: dict, imgs: dict[str, bytes], back: str) -> str:
    y, mo, da = date.split("-")
    title = f"{y}년 {int(mo)}월 {int(da)}일 제곡교회 주보"
    qr = b64(small_qr(imgs), "image/png")
    t1, t2 = (b64(x, "image/jpeg") for x in info["trace"])
    accts = "".join(f"<p>{E(x)}</p>" for x in info["accts"])
    sb = SAVEBAR.read_text() if SAVEBAR.exists() else ""
    return PAGE.format(
        title=E(title), back=back, t1=t1, t2=t2, cover=b64(info["cover"], "image/jpeg"),
        order=order_html(d.get("order", [])), sermon=sermon_html(d), sam=sam_html(d["sam"], info.get("sam_y")),
        news=news_html(d["news"], info["purple"], info.get("news_y")), accts=accts, col2=col2_html(d, qr, info["staff"]),
        cover_txt=cover_html(d.get("mast", [])), savebar=sb)


PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<meta name="description" content="제곡교회 주일 주보">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap">
<style>
@page{{size:A4 landscape;margin:0}}
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:#c9ccc8;color:#000;font-family:"Noto Sans KR",system-ui,sans-serif}}
.page{{position:relative;width:297mm;height:210mm;margin:8mm auto;background:#fff;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.2)}}
.trace{{position:absolute;inset:0;width:100%;height:100%;opacity:.45;pointer-events:none;z-index:9;display:none}}
body.showtrace .trace{{display:block}}
.layer{{position:absolute;inset:0}}
.bx{{position:absolute;overflow:hidden}}
p{{margin:0}}
/* 1면 — 예배순서 · 오늘의 말씀 · 샘터모임 */
.p1 .bg{{position:absolute;inset:0;background:linear-gradient(90deg,#edf3fa 0 108mm,#a9cce9 108mm)}}
.c1{{left:0;top:7mm;width:108mm;height:183mm;background:#fff;padding:9.6mm 9.5mm 0 11.3mm}}
.c1h{{text-align:center;font-weight:700;font-size:10pt;color:#0f518e}}
.c1v{{text-align:center;font-size:8.5pt;color:#595959;margin-top:.8mm}}
.dots{{border:0;border-top:1.6px dotted #9bbad6;margin:3.4mm 0 0}}
.c1s{{text-align:center;font-size:10pt;color:#0f518e;margin-top:5.4mm}}
.c1t{{text-align:center;font-size:16pt;color:#0f518e;line-height:1.25}}
.c1m{{text-align:right;font-size:8.2pt;color:#502962;margin-top:3.4mm}}.c1m b{{font-size:9.2pt}}
.olist{{margin-top:.9mm}}
.or{{display:flex;align-items:center;height:9.62mm;font-size:10.5pt}}
.or .on{{width:18.6mm;display:flex;justify-content:space-between;flex:none}}.or .on i{{font-style:normal}}
.or .ow{{width:28mm;margin-left:6.4mm;letter-spacing:.12em;flex:none;line-height:1.1;font-size:10pt}}
.or .ot{{font-size:9.3pt;letter-spacing:-.02em;white-space:nowrap}}
.cfoot{{margin-top:-.6mm;text-align:center}}
.cf1{{font-size:11pt;color:#3a3c84;line-height:1.2}}.cf2{{font-size:10pt;color:#3a3c84;margin-top:2.2mm;letter-spacing:.04em}}
.c2{{left:111mm;top:6.9mm;width:104mm;height:196mm;background:#fff;padding:9.6mm 9.5mm 0 10.2mm}}
.c3{{left:215mm;top:6.9mm;width:73mm;height:196mm;background:#edf3fa;padding:9.6mm 5mm 0 7.4mm}}
.ph{{margin:0;text-align:center;font-weight:400;font-size:14pt;color:#0f518e;letter-spacing:.04em}}
.st{{text-align:center;font-weight:700;font-size:10.8pt;margin-top:2.6mm}}
.sr{{text-align:center;font-weight:700;font-size:11pt;margin-top:1.6mm}}
.sb{{position:absolute;left:10.2mm;right:9.5mm;top:33.4mm;bottom:.8mm;font-size:10pt;line-height:4.07mm;text-align:justify;letter-spacing:0;word-break:keep-all}}
.sb p{{text-indent:1em;margin-bottom:4.07mm}}.sb b{{font-weight:700}}
.sam{{position:absolute;left:7.4mm;right:4.6mm;top:28mm;bottom:2mm;font-size:10.5pt;line-height:4.45mm;word-break:keep-all}}
.sg{{position:absolute;left:7.4mm;right:4.4mm;font-size:10.5pt;line-height:4.06mm;letter-spacing:.04em;word-break:keep-all}}.sg p{{margin:0 0 2.4mm}}.sg .sh{{margin:2.2mm 0 0 1.5em}}.sg .sh+.sh{{margin-top:3.6mm}}.sg .sq{{margin:2.6mm 0 0 1.1em}}.sg .sp{{margin:0 0 0 .5em}}.sg .si+.sp{{margin-top:2.6mm}}.si{{margin:0 0 3.6mm;padding-left:1.35em;text-indent:-1.35em}}.sh{{margin:0 0 2.6mm 1.6em}}
.sq{{margin:0 0 3mm 1.4em;padding-left:1em;text-indent:-1em}}.sp{{margin:0 0 .4mm .9em}}
.si+.sp{{margin-top:-1.4mm}}.sp+.si{{margin-top:3.6mm}}.sh+.si,.sq+.si{{margin-top:6mm}}
/* 2면 — 교회소식 · 읽기표·섬김이 · 표지 */
.p2 .bg{{position:absolute;inset:0;background:linear-gradient(90deg,#edf3fa 0 81.9mm,#fff 81.9mm 186.8mm,#60a9b8 186.8mm)}}
.n1{{left:0;top:0;width:81.9mm;height:210mm}}
.pill{{position:absolute;left:13mm;top:18mm;width:54.6mm;height:9.9mm;border-radius:2mm;background:#3787c4;color:#fff;font-size:14pt;text-align:center;line-height:9.9mm;letter-spacing:.12em}}
.news{{position:absolute;left:6.7mm;right:6mm;top:30.4mm;bottom:15mm;word-break:keep-all}}
.nh{{font-size:9.8pt;color:#3888c5;margin-top:2.1mm;line-height:4.6mm}}.nh:first-child{{margin-top:0}}
.ng{{position:absolute;left:6.7mm;right:5.6mm;word-break:keep-all}}.ng .nh{{margin:0 0 .3mm}}.nb{{font-size:8.7pt;line-height:4.05mm;padding-left:4.9mm;letter-spacing:-.035em}}.nb small{{font-size:6.6pt}}.pu{{color:#9d5cbb}}
.acct{{position:absolute;left:0;bottom:0;width:81.9mm;height:12mm;background:#a9cce9;padding:2.6mm 0 0 12.3mm;font-size:8pt;line-height:3.9mm;color:#262626}}
.n2{{left:81.9mm;top:0;width:104.9mm;height:210mm}}
.n2 .band{{position:absolute;left:0;right:0;top:0;height:8mm;background:#a9cce9}}
.n2 .in{{position:absolute;left:5.6mm;right:5.6mm;top:0;bottom:0}}
.sec{{position:absolute;left:0;margin:0;font-weight:400;font-size:12pt;color:#3888c5;letter-spacing:.06em}}
.sec::before{{content:"| ";font-family:serif}}
.intro{{position:absolute;left:0;right:0;font-size:10pt;line-height:4.6mm;text-align:justify;letter-spacing:.012em}}
.wk{{position:absolute;right:0;font-size:9pt}}
table{{border-collapse:collapse;width:100%;table-layout:fixed}}
th{{background:#dce9f6;color:#0f518e;font-weight:400;font-size:8.8pt;height:5.6mm;border-left:1px solid #fff}}
td{{font-size:8.6pt;line-height:3.95mm;text-align:center;border-left:1px solid #c9ccd0;border-top:1px dotted #b8bcc0;padding:0}}
tr>:first-child{{border-left:0}}.rt tr:last-child td,.svt tr:last-child td{{border-bottom:1px solid #b8bcc0}}
.rt td{{height:9.2mm;line-height:4.3mm}}.svt td{{height:8.75mm}}.svt td:nth-child(4){{letter-spacing:.3em}}.svt td:nth-child(5){{font-size:8pt;letter-spacing:-.05em}}
.rt th:first-child,.rt td:first-child{{width:9mm}}.svt th:first-child,.svt td:first-child{{width:9.2mm}}
.wed{{position:absolute;left:0;right:0;font-size:9.3pt;color:#6182d6;text-align:center;text-decoration:underline;text-underline-offset:1px;border-bottom:1px solid #6b7280;padding-bottom:.4mm}}
.qr{{position:absolute;left:0;right:0;height:21.4mm;border:1px solid #6b7280;display:flex;align-items:center;gap:3mm;padding:0 1.6mm}}
.qr img{{width:19mm;height:19mm;image-rendering:pixelated}}.qr p{{flex:1;text-align:center;font-size:10.3pt;color:#6182d6;line-height:4.6mm}}
.sv{{position:absolute;left:0;margin:0;font-weight:400;font-size:9pt;color:#0f518e}}
.staff{{position:absolute;left:0;right:0;display:flex;font-size:9pt;line-height:3.85mm;color:#262626}}
.staff>div:first-child{{width:42.6mm}}.staff p{{white-space:nowrap}}
.n3{{left:186.8mm;top:0;width:110.2mm;height:210mm;background:center/cover no-repeat}}
.cv-top{{position:absolute;left:8.2mm;right:6.4mm;top:17.6mm;display:flex;align-items:baseline;color:#fff;font-size:8pt}}
.cd{{position:absolute;right:33mm;top:17.4mm;color:#fff;font-size:9pt}}.cvol{{position:absolute;left:81.6mm;width:14.8mm;top:17.4mm;height:4.4mm;line-height:4.4mm;background:#fff;color:#0f518e;font-size:9pt;text-align:center}}
.cv-mot{{position:absolute;left:0;right:5mm;top:37.6mm;text-align:center;color:#fff;font-size:13pt;letter-spacing:.06em}}
.cv-name{{position:absolute;left:0;right:5mm;top:43.4mm;text-align:center;color:#0f518e;font-size:25pt;font-weight:700;letter-spacing:.44em;text-indent:.42em}}
.cv-desc{{position:absolute;left:0;right:5mm;top:71.4mm;text-align:center;color:#404040;font-size:9pt;line-height:4.2mm}}
.cv-foot{{position:absolute;left:0;right:5mm;top:187.6mm;text-align:center;font-size:8pt;color:#262626;line-height:3.9mm}}
.cv-foot p:first-child{{margin-bottom:1.4mm}}.cv-foot small{{font-size:8pt;color:#0f518e}}.cv-foot b{{font-weight:400;color:#fff;font-size:13pt;letter-spacing:.3em}}
/* 저장 단추 · 돌아가기 */
.savebar{{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:6px;align-items:center;justify-content:center;padding:8px;background:#2b2f33}}
.savebar button,.jnav a{{font:700 13px "Noto Sans KR",sans-serif;border:0;border-radius:8px;padding:7px 13px;cursor:pointer;background:#e8a33c;color:#1a1c1e;text-decoration:none}}
.savebar .msg{{color:#e7eaec;font-size:12.5px}}
.jnav{{display:flex;justify-content:center;gap:8px;padding:8px 0 0}}.jnav a{{background:#fff;border:1px solid #cbd5e1}}
#linkbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:30;align-items:center;justify-content:center}}
#linkbox.on{{display:flex}}#linkbox .in{{background:#fff;padding:16px;border-radius:10px}}#linkin{{width:300px}}
@media print{{body{{background:#fff}}.page{{margin:0;box-shadow:none;break-after:page}}.savebar,.jnav,#linkbox,.trace{{display:none!important}}
*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head>
<body>
<div class="savebar" role="toolbar" aria-label="저장">
  <button class="main" id="b-hwpx" type="button">HWPX로 저장</button>
  <button class="main" id="b-pdf" type="button">PDF로 저장</button>
  <button class="main" id="b-gdoc" type="button">구글문서로 저장</button>
  <button type="button" onclick="document.body.classList.toggle('showtrace')">원본 겹쳐 보기</button>
  <span class="msg" id="msg" aria-live="polite"></span>
</div>
<div id="linkbox" role="dialog" aria-modal="true"><div class="in"><b>링크</b>
  <input id="linkin" readonly><button type="button" id="b-copy">링크 복사</button> <button type="button" id="b-close">닫기</button></div></div>
<nav class="jnav"><a href="{back}">◀ 악보집으로</a></nav>
<div class="page p1"><img class="trace" src="{t1}" alt=""><div class="layer"><div class="bg"></div>
  <div class="bx c1">{order}</div>
  <div class="bx c2">{sermon}</div>
  <div class="bx c3">{sam}</div>
</div></div>
<div class="page p2"><img class="trace" src="{t2}" alt=""><div class="layer"><div class="bg"></div>
  <div class="bx n1">{news}<div class="acct">{accts}</div></div>
  <div class="bx n2"><div class="band"></div><div class="in">{col2}</div></div>
  <div class="bx n3" style="background-image:url({cover})">{cover_txt}</div>
</div></div>
<script data-share>
/* 넘치는 칸은 글자를 조금씩 줄여 한 칸에 담는다(원본처럼 한 면에) */
(function(){{function fit(){{document.querySelectorAll('.fit').forEach(function(el){{var s=parseFloat(getComputedStyle(el).fontSize),n=0;
el.style.fontSize='';s=parseFloat(getComputedStyle(el).fontSize);
while(el.scrollHeight>el.clientHeight+1&&n<30){{s*=0.97;el.style.fontSize=s+'px';el.style.lineHeight='1.42';n++}}}})}}
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);addEventListener('load',fit);fit()}})();
</script>
<script>{savebar}</script>
</body></html>"""


def share(date: str, html_text: str, title: str) -> str:
    body = json.dumps({"key": f"/jubo/{date}", "title": title, "html": html_text}).encode()
    req = urllib.request.Request("http://127.0.0.1:8765/share", data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))["url"]


def make(date: str, do_share: bool = True) -> tuple[Path, str]:
    """주보 HTML — 원본 PDF 그대로 자리 맞춘 편집본(jubo_exact, 2026-10-03 교장님: 원본과 어긋남 없이·칸마다 고칠 수 있게).
    한글 글을 다시 흘려 짜던 옛 방식은 make_reflow (줄바꿈·자리가 원본과 어긋남)."""
    import jubo_exact
    return jubo_exact.make(date, do_share)


def make_reflow(date: str, do_share: bool = True) -> tuple[Path, str]:
    pdf, hwp, _ = fetch(date)
    md, imgs = kordoc(hwp)
    d, info = parse(md), pdf_info(pdf)
    back = f"{SITE}/jegok_worship_{date.replace('-', '')}"
    out = render(date, d, info, imgs, back)
    DOCS.mkdir(parents=True, exist_ok=True)
    f = DOCS / f"{date.replace('-', '')}_제곡교회_주보.html"; f.write_text(out)
    url = share(date, out, f"{date.replace('-', '')} 제곡교회 주보") if do_share else ""
    return f, url


if __name__ == "__main__":
    f, url = make(sys.argv[1], "--no-share" not in sys.argv)
    print(f); print(url)
