"""악보 그림 바깥 흰 여백을 타이트하게 잘라 낸다 (2026-10-04 교장님 원칙: 모든 악보는 그림 바깥을 딱 맞게 잘라 붙인다).

  trim_image(im) → 잘라 낸 그림(PIL)   · 투명 배경은 흰색으로 깔고 본다
  trim_bytes(b)  → 잘라 낸 그림 바이트(PNG/JPEG 그대로의 형식)
  python3 accomp/trim.py 파일…           # 그 자리에서 잘라 덮어쓴다
"""
from __future__ import annotations

import io, sys
from pathlib import Path

PAD = 0.012          # 남길 여백 — 그림 폭의 1.2% (최소 6px)


def flatten(im):
    from PIL import Image
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA"); bg = Image.new("RGB", im.size, "white"); bg.paste(im, mask=im.split()[-1]); return bg
    return im.convert("RGB")


def trim_image(im, thresh: int = 200, frac: float = 0.003):
    """글자·오선이 있는 줄·열(어두운 점이 0.3% 넘는 곳)만 남기고 바깥 흰 여백을 잘라 낸다 — 흩어진 잡티는 무시."""
    import numpy as np
    im = flatten(im)
    dark = np.asarray(im.convert("L")) < thresh
    r = np.where(dark.mean(axis=1) > frac)[0]; c = np.where(dark.mean(axis=0) > frac)[0]
    if not len(r) or not len(c): return im
    p = max(6, round(im.width * PAD))
    box = (max(0, int(c[0]) - p), max(0, int(r[0]) - p), min(im.width, int(c[-1]) + 1 + p), min(im.height, int(r[-1]) + 1 + p))
    return im.crop(box) if box != (0, 0, im.width, im.height) else im


def trim_bytes(b: bytes) -> bytes:
    from PIL import Image
    src = Image.open(io.BytesIO(b)); fmt = "PNG" if (src.format or "").upper() == "PNG" else "JPEG"
    out = io.BytesIO(); im = trim_image(src)
    im.save(out, fmt, **({"quality": 92} if fmt == "JPEG" else {})); return out.getvalue()


if __name__ == "__main__":
    for f in sys.argv[1:]:
        p = Path(f); b = p.read_bytes(); t = trim_bytes(b)
        from PIL import Image
        a, z = Image.open(io.BytesIO(b)).size, Image.open(io.BytesIO(t)).size
        if z != a: p.write_bytes(t)
        print(f"{p.name}: {a} → {z}")
