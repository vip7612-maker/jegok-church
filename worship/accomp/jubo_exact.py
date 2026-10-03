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

import base64, html, io, sys
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
                            if (not gap_sp and g > sp["size"] * 0.3) or g > sp["size"] * 0.9 or abs(ch["bbox"][1] - top) > sp["size"] * 0.3:
                                segs.append(cur); cur = []
                        cur.append((sp, ch)); last = ch["bbox"][2]; top = ch["bbox"][1]; gap_sp = False
                if cur: segs.append(cur)
                for seg in segs:
                    while seg and not seg[-1][1]["c"].strip(): seg = seg[:-1]
                    while seg and not seg[0][1]["c"].strip(): seg = seg[1:]
                    if not seg: continue
                    runs = []
                    for sp, ch in seg:
                        if runs and runs[-1]["_sp"] is sp: runs[-1]["t"] += ch["c"]
                        else: runs.append({"_sp": sp, "t": ch["c"], "size": sp["size"], "color": _color(sp["color"]),
                                           "bold": "Bold" in sp["font"] or bool(sp["flags"] & 16), "font": sp["font"].split("+", 1)[-1]})
                    for r in runs: r.pop("_sp")
                    x0 = min(ch["bbox"][0] for _, ch in seg); x1 = max(ch["bbox"][2] for _, ch in seg)
                    y0 = min(ch["bbox"][1] for _, ch in seg); y1 = max(ch["bbox"][3] for _, ch in seg)
                    lines.append({"x": x0 * MM, "y": y0 * MM, "w": (x1 - x0) * MM, "h": (y1 - y0) * MM, "base": seg[0][1]["origin"][1] * MM,
                                  "dir": l.get("dir", (1, 0)), "runs": runs})
        # 글자 지운 배경
        p2 = fitz.open(); p2.insert_pdf(doc, from_page=pg.number, to_page=pg.number); q = p2[0]
        for b in q.get_text("dict")["blocks"]:
            if b["type"] != 0: continue
            for l in b["lines"]:
                for s in l["spans"]:
                    if s["text"].strip(): q.add_redact_annot(fitz.Rect(s["bbox"]), fill=None)
        q.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        im = Image.open(io.BytesIO(q.get_pixmap(dpi=200).tobytes("png"))).convert("RGB")
        bb = io.BytesIO(); im.save(bb, "JPEG", quality=82)
        trace = Image.open(io.BytesIO(pg.get_pixmap(dpi=100).tobytes("png"))).convert("RGB")
        tb = io.BytesIO(); trace.save(tb, "JPEG", quality=70)
        out.append({"bg": bb.getvalue(), "trace": tb.getvalue(), "w": W * MM, "h": H * MM, "lines": lines})
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


def render(date: str, pg: list[dict], fonts: dict[str, str], back: str) -> str:
    y, mo, da = date.split("-")
    title = f"{y}년 {int(mo)}월 {int(da)}일 제곡교회 주보"
    ff = "".join(f"@font-face{{font-family:'{E(n)}';src:url({u});}}" for n, u in fonts.items())
    body = ""
    for i, p in enumerate(pg, 1):
        bg = "data:image/jpeg;base64," + base64.b64encode(p["bg"]).decode()
        tr = "data:image/jpeg;base64," + base64.b64encode(p["trace"]).decode()
        body += (f'<div class="page p{i}" style="background-image:url({bg})"><img class="trace" src="{tr}" alt="">'
                 + "".join(line_html(l, fonts) for l in p["lines"]) + "</div>")
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
  document.addEventListener('input',function(e){{ var el=e.target.closest&&e.target.closest('.ln'); if(el){{ el.dataset.edited=1; el.style.letterSpacing='0'; }} }});
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
