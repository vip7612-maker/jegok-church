#!/usr/bin/env python3
"""주보 → 원본과 꼭 맞는 편집 가능한 HTML (hwp-to-html 스킬 「양식 있음」, 2026-10-03 교장님: 원본을 깔고 비교해 어긋남이 없게, 입력 칸마다 고칠 수 있게).

jubo_form.py 는 한글 파일 글을 다시 흘려 짜서 줄바꿈·자리가 원본과 어긋났다(196줄 중 120줄이 1.5mm 넘게).
여기서는 원본 PDF 를 그대로 쓴다.
  · 배경 = PDF 쪽에서 글자만 지운 그림(선·상자·띠·큐알·사진은 원본 그대로)
  · 글자 = PDF 의 줄마다 같은 자리(mm)·크기·색·굵기로, 줄 안에 글꼴·색이 바뀌는 조각까지 살려서 — 줄마다 고칠 수 있게(contenteditable)
  · 글꼴 = PDF 에 들어 있는 글꼴(함초롬돋움·굴림 …)을 그대로, 없는 글자는 Noto Sans KR
  · 줄 폭 = 원본 줄 폭에 맞게 글자 간격을 조금씩 맞춘다(고치면 그 줄은 자연 간격으로)
jubo_form.py 의 주보 가져오기(fetch)·저장 단추(docsave savebar)·공유(share)·저장 위치를 그대로 쓴다.

  /usr/local/bin/python3 accomp/jubo_exact.py 2026-10-04            # 만들고 공유
  /usr/local/bin/python3 accomp/jubo_exact.py 2026-10-04 --no-share
"""
from __future__ import annotations

import base64, html, io, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import jubo_form as JF  # noqa: E402

MM = 25.4 / 72          # pt → mm
E = html.escape


def _color(c: int) -> str:
    return f"#{c:06x}"


def pages(pdf: bytes) -> tuple[list[dict], dict[str, str]]:
    """PDF → 쪽마다 {bg: jpeg, w, h, lines:[{x,y,w,h,runs:[{t,size,color,bold,font}]}]}, 글꼴 {이름: data URL}."""
    import fitz
    from PIL import Image
    doc = fitz.open(stream=pdf, filetype="pdf")
    fonts: dict[str, str] = {}
    for pg in doc:
        for xref, ext, _t, base, _n, _enc in [f[:6] for f in pg.get_fonts()]:
            name = base.split("+", 1)[-1]
            if name in fonts or ext not in ("ttf", "otf", "cff"): continue
            try:
                _nm, fext, _ty, buf = doc.extract_font(xref)
                if buf: fonts[name] = f"data:font/{'otf' if fext in ('otf', 'cff') else 'ttf'};base64," + base64.b64encode(buf).decode()
            except Exception:
                pass
    out = []
    for pg in doc:
        W, H = pg.rect.width, pg.rect.height
        lines = []
        rects = [(it[1].x0 * MM, it[1].y0 * MM, it[1].x1 * MM, it[1].y1 * MM) for d in pg.get_drawings()
                 if d.get("fill") is not None for it in d["items"] if it[0] == "re"]
        grids = table_grids(rects)
        def walls(y_mm):                                  # 그 높이에서 표 칸 세로 경계들(mm)
            return [x for g in grids if g["y0"] - 0.5 <= y_mm <= g["y1"] + 0.5 for x in g["xs"]]
        # 원본의 굵은 글은 글자를 한 번 더 테두리로 덧그린 것(가짜 굵게) — 그 글자 자리를 모아 굵게로 본다
        stroked = {(round(c[2][0], 1), round(c[2][1], 1)) for t in pg.get_texttrace() if t["type"] == 1 for c in t["chars"]}
        for b in pg.get_text("rawdict")["blocks"]:
            if b["type"] != 0: continue
            for l in b["lines"]:
                # 글자 단위로 보고, 앞 글자와 멀리 떨어진 곳(표의 칸 사이 등)에서 따로 칸을 나눈다
                # 칸 나누기: ① 빈칸 글자 없이 벌어진 곳(표의 이웃 칸) ② 빈칸이 있어도 아주 멀리 벌어진 곳 ③ 높이가 바뀐 곳(세로로 쌓은 글자)
                segs, cur, last, top, gap_sp = [], [], None, None, False
                for sp in l["spans"]:
                    for ch in sp["chars"]:
                        if not ch["c"].strip():
                            gap_sp = True; cur.append((sp, ch)); continue
                        if last is not None and cur:
                            g = ch["bbox"][0] - last
                            cx = (ch["bbox"][0] + ch["bbox"][2]) / 2 * MM; lx = last * MM
                            wall = any(lx - 0.3 < w < cx for w in walls(ch["bbox"][1] * MM))
                            if (not gap_sp and g > sp["size"] * 0.3) or g > sp["size"] * 0.9 or abs(ch["bbox"][1] - top) > sp["size"] * 0.3 or wall:
                                segs.append(cur); cur = []
                        cur.append((sp, ch)); last = ch["bbox"][2]; top = ch["bbox"][1]; gap_sp = False
                if cur: segs.append(cur)
                for seg in segs:
                    trail = bool(seg) and not seg[-1][1]["c"].strip()
                    lead = bool(seg) and not seg[0][1]["c"].strip()
                    while seg and not seg[-1][1]["c"].strip(): seg = seg[:-1]
                    while seg and not seg[0][1]["c"].strip(): seg = seg[1:]
                    if not seg: continue
                    runs = []
                    for sp, ch in seg:
                        bold = "Bold" in sp["font"] or bool(sp["flags"] & 16) or (round(ch["origin"][0], 1), round(ch["origin"][1], 1)) in stroked
                        if runs and runs[-1]["_sp"] is sp and runs[-1]["bold"] == bold: runs[-1]["t"] += ch["c"]
                        else: runs.append({"_sp": sp, "t": ch["c"], "size": sp["size"], "color": _color(sp["color"]),
                                           "bold": bold, "font": sp["font"].split("+", 1)[-1]})
                    for r in runs: r.pop("_sp")
                    x0 = min(ch["bbox"][0] for _, ch in seg); x1 = max(ch["bbox"][2] for _, ch in seg)
                    y0 = min(ch["bbox"][1] for _, ch in seg); y1 = max(ch["bbox"][3] for _, ch in seg)
                    lines.append({"x": x0 * MM, "y": y0 * MM, "w": (x1 - x0) * MM, "h": (y1 - y0) * MM, "base": seg[0][1]["origin"][1] * MM,
                                  "dir": l.get("dir", (1, 0)), "runs": runs, "lead": lead, "trail": trail,
                                  "size": max(r["size"] for r in runs)})
        lines, cells = make_cells(lines, grids)
        lines, blocks = make_blocks(lines)
        # 글자 지운 배경
        p2 = fitz.open(); p2.insert_pdf(doc, from_page=pg.number, to_page=pg.number); q = p2[0]
        for b in q.get_text("dict")["blocks"]:
            if b["type"] != 0: continue
            for l in b["lines"]:
                for s in l["spans"]:
                    if s["text"].strip(): q.add_redact_annot(fitz.Rect(s["bbox"]), fill=None)
        q.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        im = Image.open(io.BytesIO(q.get_pixmap(dpi=200).tobytes("png"))).convert("RGB")
        # 원본에서 가로세로 비율이 틀어진 채 그려진 그림(정사각형 큐알을 납작하게 등) — 배경에서 지우고 제 비율로 다시 얹는다
        fixes = []
        from PIL import ImageDraw
        for info in pg.get_image_info(xrefs=True):
            x0, y0, x1, y1 = info["bbox"]
            if x1 <= 0 or y1 <= 0 or not info.get("xref") or info["height"] == 0: continue
            bw, bh = x1 - x0, y1 - y0
            if bw < 20 or bh < 20 or bw > W * 0.5: continue
            want = info["width"] / info["height"]
            if abs((bw / bh) / want - 1) < 0.08: continue
            k = im.width / W
            ImageDraw.Draw(im).rectangle([x0 * k, y0 * k, x1 * k, y1 * k], fill="white")
            sw = min(bw, bh * want); sh = sw / want
            data = doc.extract_image(info["xref"])
            fixes.append({"x": (x0 + (bw - sw) / 2) * MM, "y": (y0 + (bh - sh) / 2) * MM, "w": sw * MM, "h": sh * MM,
                          "src": f"data:image/{data['ext']};base64," + base64.b64encode(data["image"]).decode()})
        bb = io.BytesIO(); im.save(bb, "JPEG", quality=82)
        trace = Image.open(io.BytesIO(pg.get_pixmap(dpi=100).tobytes("png"))).convert("RGB")
        tb = io.BytesIO(); trace.save(tb, "JPEG", quality=70)
        out.append({"bg": bb.getvalue(), "trace": tb.getvalue(), "w": W * MM, "h": H * MM, "lines": lines, "blocks": blocks, "cells": cells, "fixes": fixes})
    return out, fonts


def line_html(l: dict, fonts: dict) -> str:
    runs = "".join(
        f'<span style="font-family:\'{E(r["font"])}\',\'Noto Sans KR\',sans-serif;font-size:{r["size"]:.2f}pt;color:{r["color"]}'
        f'{";font-weight:700" if r["bold"] else ""}">{E(r["t"])}</span>' for r in l["runs"])
    vertical = l["dir"][0] == 0
    size = max(r["size"] for r in l["runs"]) * 0.3528        # pt → mm
    style = (f"left:{l['x']:.2f}mm;top:{l['base'] - size * 0.88:.2f}mm;width:{l['w']:.2f}mm;line-height:{size:.2f}mm"
             + (";writing-mode:vertical-rl" if vertical else ""))
    return (f'<div class="ln" contenteditable="true" spellcheck="false" data-w="{l["w"]:.2f}" data-x="{l["x"]:.2f}" '
            f'data-y="{l["y"]:.2f}" data-h="{l["h"]:.2f}" style="{style}">{runs}</div>')


BULLET = re.compile(r"^\s*(?:[-–•◇·※]|[①-⑳]|\d+\.\s)")
HEAD = re.compile(r"^\s*(?:[①-⑳]|\d+\.\s?\S)")          # 「1. 환영합니다」「① 찬양을…」 같은 제목 줄 — 묶지 않고 따로(교장님: 제목 따로 내용 따로)


def table_grids(rects: list[tuple]) -> list[dict]:
    """원본의 색 칸 → 표 격자. 머리 줄(가로로 붙은 색 칸 3개 넘게)이 열을, 바로 아래로 붙은 첫 열 색 칸들이 행을 정한다."""
    heads, rows_by = [], {}
    for r in rects:
        if r[2] - r[0] > 2 and r[3] - r[1] > 2: rows_by.setdefault((round(r[1], 0), round(r[3], 0)), []).append(r)
    for rs in rows_by.values():
        rs = sorted(rs); run = [rs[0]]
        for r in rs[1:]:
            if abs(r[0] - run[-1][2]) < 0.5: run.append(r)
            else:
                if len(run) >= 3: heads.append(run)
                run = [r]
        if len(run) >= 3: heads.append(run)
    grids = []
    for hdr in heads:
        c0 = hdr[0]
        side = sorted(r for r in rects if abs(r[0] - c0[0]) < 0.5 and abs(r[2] - c0[2]) < 0.5 and r[1] >= c0[3] - 0.5)
        rows = [(c0[1], c0[3])]                           # (위, 아래)
        for r in side:                                    # 앞 행 바로 아래에 붙은 첫 열 칸만 이어서(다른 표로 넘어가지 않게)
            top, prev_bottom = r[1], rows[-1][1]
            if top - prev_bottom > 0.5: break
            if abs(top - prev_bottom) <= 0.5: rows.append((r[1], r[3]))
        cols = [(r[0], r[2]) for r in hdr]
        grids.append({"rows": rows, "cols": cols, "xs": [c[0] for c in cols[1:]], "y0": rows[0][0], "y1": rows[-1][1]})
    return grids


def make_cells(lines: list[dict], grids: list[dict]) -> tuple[list[dict], list[dict]]:
    """표는 칸마다 한 입력 칸으로(2026-10-03 교장님: 표 제목 따로, 표는 칸마다). 칸 안에 든 글 조각은 모두 그 칸 하나로."""
    cells = [{"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "items": []}
             for g in grids for (y0, y1) in g["rows"] for (x0, x1) in g["cols"]]
    rest = []
    for l in lines:
        cx, cy = l["x"] + l["w"] / 2, l["y"] + l["h"] / 2
        c = next((c for c in cells if c["x"] - 0.3 <= cx <= c["x"] + c["w"] + 0.3 and c["y"] - 0.3 <= cy <= c["y"] + c["h"] + 0.3), None)
        if c is not None and l["dir"][0] != 0: c["items"].append(l)
        else: rest.append(l)
    out = []
    for c in cells:
        if not c["items"]: continue
        rows, cur = [], []
        for it in sorted(c["items"], key=lambda t: (round(t["y"], 0), t["x"])):
            if cur and abs(it["y"] - cur[0]["y"]) > 0.8: rows.append(cur); cur = []
            cur.append(it)
        if cur: rows.append(cur)
        rr = []
        for row in rows:
            row.sort(key=lambda t: t["x"]); x0 = row[0]["x"]; x1 = max(t["x"] + t["w"] for t in row)
            spread = len(row) > 1 and (x1 - x0) > c["w"] * 0.55              # 「마 리 아」처럼 칸 너비에 고르게 퍼진 글
            runs = []
            for k, t in enumerate(row):
                if k: runs.append(dict(t["runs"][0], t=" "))
                runs += t["runs"]
            rr.append({"runs": runs, "spread": spread, "l": x0 - c["x"], "r": c["x"] + c["w"] - x1, "y": row[0]["y"], "h": row[0]["h"],
                       "size": max(t["size"] for t in row)})
        pitch = (rr[-1]["y"] - rr[0]["y"]) / (len(rr) - 1) if len(rr) > 1 else rr[0]["size"] * 0.3528 * 1.2
        c.update({"rows": rr, "pitch": pitch})
        out.append(c)
    return rest, out


def cell_html(c: dict) -> str:
    def runs(rs):
        return "".join(f'<span style="font-family:\'{E(r["font"])}\',\'Noto Sans KR\',sans-serif;font-size:{r["size"]:.2f}pt;color:{r["color"]}'
                       f'{";font-weight:700" if r["bold"] else ""}">{E(r["t"])}</span>' for r in rs)
    rows = "".join(
        f'<div class="cr" style="line-height:{c["pitch"]:.2f}mm;'
        + (f'text-align:justify;text-align-last:justify;padding:0 {max(0, r["r"]):.2f}mm 0 {max(0, r["l"]):.2f}mm' if r["spread"] else "text-align:center")
        + f'">{runs(r["runs"])}</div>' for r in c["rows"])
    return (f'<div class="cell" contenteditable="true" spellcheck="false" style="left:{c["x"]:.2f}mm;top:{c["y"]:.2f}mm;'
            f'width:{c["w"]:.2f}mm;height:{c["h"]:.2f}mm">{rows}</div>')


def make_blocks(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    """여러 줄로 이어지는 글(오늘의 말씀·샘터 질문·공동기도문·소식 문단 …)은 한 글상자로 — 한 곳에서 쓰고 고치면 줄이
    저절로 다시 바뀐다(2026-10-03 교장님). 본문 줄 간격(글자 크기의 1.45배 이하)으로 3줄 넘게 붙어 있으면 한 묶음,
    한 줄쯤 빈 곳은 문단 나눔. 줄 머리에 「-」「①」 같은 표시가 있으면 새 문단(둘째 줄부터 들여 쓰기 그대로)."""
    used, blocks = set(), []
    i = 0
    while i < len(lines):
        l = lines[i]
        txt = lambda g: "".join(r["t"] for r in g["runs"])
        mm = l["size"] * 0.3528
        if l["dir"][0] == 0 or HEAD.match(txt(l)) or l["w"] < mm * 2: i += 1; continue
        grp = [i]; pitch = None
        j = i + 1
        while j < len(lines):
            n, prev = lines[j], lines[grp[-1]]
            if abs(n["size"] - l["size"]) > 0.2 or n["dir"][0] == 0 or HEAD.match(txt(n)) or n["w"] < mm * 2: break
            gx = min(lines[k]["x"] for k in grp)
            if abs(n["x"] - gx) > mm * 3: break                     # 들여쓴 첫 줄·내어 쓴 줄 모두 허용
            gap = n["y"] - prev["y"]
            if pitch is None:
                if not (mm * 1.0 <= gap <= mm * 1.45): break        # 본문 줄 간격으로 붙어 있어야 한 묶음
                pitch = gap
            elif not (pitch * 0.85 <= gap <= pitch * 1.15 or pitch * 1.7 <= gap <= pitch * 2.6): break
            grp.append(j); j += 1
        G = [lines[k] for k in grp]
        bx = min(g["x"] for g in G); maxw = max(g["x"] + g["w"] for g in G) - bx
        wrap2 = len(G) == 2 and G[0]["w"] >= maxw * 0.85 and G[1]["w"] < G[0]["w"] * 0.92   # 두 줄이면 첫 줄이 꽉 차서 넘어간 글일 때만
        if (len(G) >= 3 or wrap2) and maxw >= 25:                        # 좁은 표 칸(읽기표 등)은 줄 그대로
            text = lambda g: "".join(r["t"] for r in g["runs"])
            paras, cur = [], None
            for k, g in enumerate(G):
                prev = G[k - 1] if k else None
                blank = prev is not None and g["y"] - prev["y"] > pitch * 1.5
                hang = cur is not None and g["x"] > bx + cur["fx"] + mm * 0.5      # 앞 줄보다 들여 쓴 줄 = 내어 쓰기의 이어지는 줄
                newp = (prev is None or blank or BULLET.match(text(g))
                        or (not hang and prev["x"] + prev["w"] < bx + maxw * 0.8))
                if cur and not newp and "cx" not in cur: cur["cx"] = g["x"] - bx   # 둘째 줄이 시작하는 자리 = 내어 쓰기 기준
                if newp:
                    cur = {"fx": g["x"] - bx, "gap": (g["y"] - prev["y"] - pitch) if blank else 0, "runs": []}
                    paras.append(cur)
                elif prev["trail"] or g["lead"]:
                    cur["runs"].append(dict(g["runs"][0], t=" "))
                for r in g["runs"]:
                    last = cur["runs"][-1] if cur["runs"] else None
                    if last and last["bold"] == r["bold"] and last["font"] == r["font"] and last["color"] == r["color"]:
                        cur["runs"][-1] = dict(last, t=last["t"] + r["t"])
                    else:
                        cur["runs"].append(dict(r))
            for pa in paras:                                   # 첫 줄 자리(fx)와 둘째 줄 자리(cx) → 왼쪽 여백·첫 줄 들여쓰기
                cx = pa.get("cx", 0.0) if pa.get("cx", 0.0) > 0.2 else 0.0
                pa["pad"] = cx; pa["indent"] = pa["fx"] - cx
            mids = [g["x"] + g["w"] / 2 for g in G]
            centered = max(mids) - min(mids) < 1.2 and max(g["w"] for g in G) - min(g["w"] for g in G) > 3
            if centered:                                       # 줄마다 가운데 맞춘 글(큐알 옆 안내 등) — 줄 하나가 한 문단
                paras = [{"fx": 0, "pad": 0, "indent": 0, "gap": 0, "runs": [dict(r) for r in g["runs"]]} for g in G]
            full = [g for g in G if g["w"] > maxw * 0.95]              # 꽉 찬 줄 — 글자 간격 맞추는 기준
            ref = max(full or G, key=lambda g: g["w"])
            blocks.append({"x": bx, "y": G[0]["y"], "h": G[0]["h"], "w": maxw, "pitch": pitch, "size": l["size"],
                           "font": l["runs"][0]["font"], "color": l["runs"][0]["color"], "paras": paras,
                           "ref": text(ref), "refw": ref["w"], "center": centered})
            used.update(grp); i = j
        else:
            i += 1
    return [l for k, l in enumerate(lines) if k not in used], blocks


def block_html(b: dict) -> str:
    def runs(rs):
        return "".join(f'<span style="font-family:\'{E(r["font"])}\',\'Noto Sans KR\',sans-serif;color:{r["color"]}'
                       f'{";font-weight:700" if r["bold"] else ""}">{E(r["t"])}</span>' for r in rs)
    paras = "".join(f'<div class="pa" style="padding-left:{p["pad"]:.2f}mm;text-indent:{p["indent"]:.2f}mm;margin-top:{max(0, p["gap"]):.2f}mm">{runs(p["runs"])}</div>'
                    for p in b["paras"])
    return (f'<div class="blk" contenteditable="true" spellcheck="false" data-x="{b["x"]:.2f}" data-y="{b["y"]:.2f}" data-h="{b["h"]:.2f}" '
            f'data-refw="{b["refw"]:.2f}" data-ref="{E(b["ref"])}" style="left:{b["x"]:.2f}mm;top:{b["y"]:.2f}mm;width:{b["w"] + 0.3:.2f}mm;'
            f'{"text-align:center;" if b.get("center") else ""}'
            f'font-size:{b["size"]:.2f}pt;line-height:{b["pitch"]:.2f}mm;font-family:\'{E(b["font"])}\',\'Noto Sans KR\',sans-serif;color:{b["color"]}">'
            f'{paras}</div>')


def render(date: str, pg: list[dict], fonts: dict[str, str], back: str) -> str:
    y, mo, da = date.split("-")
    title = f"{y}년 {int(mo)}월 {int(da)}일 제곡교회 주보"
    ff = "".join(f"@font-face{{font-family:'{E(n)}';src:url({u});}}" for n, u in fonts.items())
    body = ""
    for i, p in enumerate(pg, 1):
        bg = "data:image/jpeg;base64," + base64.b64encode(p["bg"]).decode()
        tr = "data:image/jpeg;base64," + base64.b64encode(p["trace"]).decode()
        body += (f'<div class="page p{i}" style="background-image:url({bg})"><img class="trace" src="{tr}" alt="">'
                 + "".join(f'<img class="fix" src="{f["src"]}" alt="" style="left:{f["x"]:.2f}mm;top:{f["y"]:.2f}mm;width:{f["w"]:.2f}mm;height:{f["h"]:.2f}mm">'
                           for f in p.get("fixes", []))
                 + "".join(line_html(l, fonts) for l in p["lines"]) + "".join(block_html(b) for b in p.get("blocks", [])) + "".join(cell_html(c) for c in p.get("cells", [])) + "</div>")
    sb = JF.SAVEBAR.read_text() if JF.SAVEBAR.exists() else ""
    return PAGE.format(title=E(title), ff=ff, body=body, back=back, savebar=sb)


PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<meta name="description" content="제곡교회 주일 주보">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap">
<style>
{ff}
@page{{size:A4 landscape;margin:0}}
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:#c9ccc8;color:#000;font-family:"Noto Sans KR",system-ui,sans-serif}}
.page{{position:relative;width:297mm;height:210mm;margin:8mm auto;background:#fff center/100% 100% no-repeat;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.2)}}
.trace{{position:absolute;inset:0;width:100%;height:100%;opacity:.5;pointer-events:none;z-index:9;display:none}}
body.showtrace .trace{{display:block}}
.ln{{position:absolute;white-space:pre;outline:none;z-index:2}}
.fix{{position:absolute;z-index:1}}
.blk{{position:absolute;outline:none;z-index:2;text-align:justify;word-break:break-all;line-break:anywhere;white-space:pre-wrap}}
.blk .pa{{min-height:1em}}
.cell{{position:absolute;display:flex;flex-direction:column;justify-content:center;outline:none;z-index:2;white-space:nowrap}}
.cell:hover{{background:rgba(232,163,60,.12)}}.cell:focus{{background:rgba(232,163,60,.2);box-shadow:inset 0 0 0 1px #e8a33c}}
.blk:hover{{background:rgba(232,163,60,.08)}}.blk:focus{{background:rgba(232,163,60,.14);box-shadow:0 0 0 1px #e8a33c}}
.ln:hover{{background:rgba(232,163,60,.12)}}.ln:focus{{background:rgba(232,163,60,.22);box-shadow:0 0 0 1px #e8a33c}}
.savebar{{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:6px;align-items:center;justify-content:center;padding:8px;background:#2b2f33}}
.savebar button,.jnav a{{font:700 13px "Noto Sans KR",sans-serif;border:0;border-radius:8px;padding:7px 13px;cursor:pointer;background:#e8a33c;color:#1a1c1e;text-decoration:none}}
.savebar .msg{{color:#e7eaec;font-size:12.5px}}
.jnav{{display:flex;justify-content:center;gap:8px;padding:8px 0 0}}.jnav a{{background:#fff;border:1px solid #cbd5e1}}
.tip{{text-align:center;font-size:12.5px;color:#334155;margin:6px 0 0}}
.savebar~.jnav .editlink{{display:none}}   /* 편집본에서는 「고치기」 링크를 숨기고, 공유본(저장 단추가 빠짐)에서만 보인다 */
#linkbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:30;align-items:center;justify-content:center}}
#linkbox.on{{display:flex}}#linkbox .in{{background:#fff;padding:16px;border-radius:10px}}#linkin{{width:300px}}
@media print{{body{{background:#fff}}.page{{margin:0;box-shadow:none;break-after:page}}.savebar,.jnav,.tip,#linkbox,.trace{{display:none!important}}
.ln:hover,.ln:focus{{background:none;box-shadow:none}}*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
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
<nav class="jnav"><a href="{back}">◀ 악보집으로</a><a class="editlink" href="edit.html">✏️ 고치기</a></nav>
<p class="tip">글자를 누르면 바로 고칠 수 있습니다 · 다 고친 뒤 「링크 복사」를 누르면 이 주보 링크에 반영됩니다(맥미니·테일스케일 연결 기기) · 「원본 겹쳐 보기」로 원본과 비교</p>
{body}
<script data-share>
/* 줄 폭을 원본 줄 폭에 맞춘다 — 글자 간격을 조금씩. 고친 줄은 자연 간격으로 둔다 */
(function(){{
  var PX=96/25.4;
  function fit(){{document.querySelectorAll('.ln').forEach(function(el){{ if(el.dataset.edited) return;
    var pg=el.parentNode.getBoundingClientRect(), k=pg.width/(297*PX)||1;              // 화면 배율(휴대폰 축소 등)
    el.style.letterSpacing='0'; var r=document.createRange(); r.selectNodeContents(el); var b=r.getBoundingClientRect();
    var want=parseFloat(el.dataset.w)*PX, have=b.width/k, n=(el.textContent||'').length;
    if(n>1&&have>0){{ var d=(want-have)/n; if(Math.abs(d)<14) el.style.letterSpacing=d.toFixed(2)+'px'; }}   // 글자 간격은 글자마다 뒤에 붙으므로 n 으로 나눈다
    b=r.getBoundingClientRect();                                                       // 세로: 글자 상자 가운데를 원본 가운데에
    var cy=((b.top+b.bottom)/2-pg.top)/k, wy=(parseFloat(el.dataset.y)+parseFloat(el.dataset.h)/2)*PX;
    el.style.top=(parseFloat(el.style.top)*PX+(wy-cy))/PX+'mm'; }}); }}
  function fitBlocks(){{document.querySelectorAll('.blk').forEach(function(el){{ if(el.dataset.fitted) return;
    var pg=el.parentNode.getBoundingClientRect(), k=pg.width/(297*PX)||1;
    var probe=document.createElement('span'); probe.style.cssText='position:absolute;visibility:hidden;white-space:pre;letter-spacing:0';
    probe.textContent=el.dataset.ref; el.appendChild(probe); var nat=probe.getBoundingClientRect().width/k; el.removeChild(probe);
    var n=el.dataset.ref.length; if(n>1&&nat>0){{ var d=(parseFloat(el.dataset.refw)*PX-nat)/n; if(Math.abs(d)<6) el.style.letterSpacing=d.toFixed(3)+'px'; }}
    var tw=document.createTreeWalker(el,NodeFilter.SHOW_TEXT), t=tw.nextNode();                    // 첫 글자 가운데를 원본 첫 줄 가운데에
    while(t&&!t.nodeValue.trim()) t=tw.nextNode();
    if(t){{ var r=document.createRange(), i=t.nodeValue.search(/\S/); r.setStart(t,i); r.setEnd(t,i+1); var b=r.getBoundingClientRect();
      var cy=((b.top+b.bottom)/2-pg.top)/k, wy=(parseFloat(el.dataset.y)+parseFloat(el.dataset.h)/2)*PX;
      el.style.top=(parseFloat(el.style.top)*PX+(wy-cy))/PX+'mm'; }}
    el.dataset.fitted=1; }}); }}
  document.addEventListener('input',function(e){{ var el=e.target.closest&&e.target.closest('.ln'); if(el){{ el.dataset.edited=1; el.style.letterSpacing='0'; }} }});
  if(document.fonts&&document.fonts.ready) document.fonts.ready.then(fitBlocks); addEventListener('load',fitBlocks);
  if(document.fonts&&document.fonts.ready) document.fonts.ready.then(fit); addEventListener('load',fit); fit();
}})();
</script>
<script>{savebar}</script>
</body></html>"""


def make(date: str, do_share: bool = True) -> tuple[Path, str]:
    pdf, _hwp, _ = JF.fetch(date)
    pg, fonts = pages(pdf)
    back = f"{JF.SITE}/jegok_worship_{date.replace('-', '')}"
    out = render(date, pg, fonts, back)
    JF.DOCS.mkdir(parents=True, exist_ok=True)
    f = JF.DOCS / f"{date.replace('-', '')}_제곡교회_주보.html"; f.write_text(out)
    url = JF.share(date, out, f"{date.replace('-', '')} 제곡교회 주보") if do_share else ""
    if url:                                           # 공유본 옆에 편집본(edit.html) — 「✏️ 고치기」로 열고, 고친 뒤 「링크 복사」로 공유본에 반영
        import re as _re, subprocess
        sid = _re.search(r"/d/([^/]+)/", url).group(1)
        site = Path.home() / "dev/daily-briefing/report-site"
        (site / "d" / sid / "edit.html").write_text(out.replace('<title>', '<meta name="robots" content="noindex"><title>✏️ ', 1))
        subprocess.run([str(Path.home() / ".local/node/bin/vercel"), "deploy", "--prod", "--yes"], cwd=site, capture_output=True, timeout=600)
    return f, url


if __name__ == "__main__":
    f, url = make(sys.argv[1], "--no-share" not in sys.argv)
    print(f); print(url)
