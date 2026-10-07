"""예배준비 [초기화] — 악보집·PPT 를 사이트에서 내리되 지우지 않고 옮겨 둔다 (2026-10-07 교장님)."""
import json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import publish as P


class UnpublishTests(unittest.TestCase):
    def test_unpublish_moves_and_unroutes(self):
        t = Path(tempfile.mkdtemp()); site, here = t / "site", t / "acc"
        for d in (site / "d" / "SID1", here / "data", here / "out", here / "jubo"): d.mkdir(parents=True)
        (site / "d" / "SID1" / "index.html").write_text("x"); (here / "data" / "2026-10-08.json").write_text("{}")
        (here / "out" / "2026-10-08.html").write_text("x"); (here / "jubo" / "2026-10-08.pdf").write_text("x"); (here / "data" / "2026-10-11.json").write_text("{}")
        (site / "vercel.json").write_text(json.dumps({"rewrites": [{"source": "/jegok_worship_20261008/", "destination": "/d/SID1/"},
                                                                     {"source": "/jegok_worship_20261008/:path*", "destination": "/d/SID1/:path*"},
                                                                     {"source": "/jegok_worship_20261011/", "destination": "/d/SID2/"}],
                                                        "redirects": [{"source": "/jegok_worship_20261008", "destination": "/jegok_worship_20261008/"}]}))
        shares = t / "shares.json"; shares.write_text(json.dumps({"/accomp/2026-10-08": "SID1"}))
        pubf = here / "published.json"; pubf.write_text(json.dumps(["2026-10-08", "2026-10-11"]))
        old = (P.SITE, P.HERE, P.SHARES, P.PUBLISHED)
        try:
            P.SITE, P.HERE, P.SHARES, P.PUBLISHED = site, here, shares, pubf
            keep = t / "keep"
            done = P.unpublish("2026-10-08", keep)
        finally:
            P.SITE, P.HERE, P.SHARES, P.PUBLISHED = old
        self.assertEqual(json.loads(pubf.read_text()), ["2026-10-11"])
        v = json.loads((site / "vercel.json").read_text())
        self.assertEqual([r["source"] for r in v["rewrites"]], ["/jegok_worship_20261011/"]); self.assertEqual(v["redirects"], [])
        self.assertFalse((site / "d" / "SID1").exists()); self.assertTrue((keep / "site-SID1" / "index.html").exists())   # 지우지 않고 옮김
        for f in ("2026-10-08.json", "2026-10-08.html", "2026-10-08.pdf"): self.assertTrue((keep / f).exists(), f)
        self.assertTrue((here / "data" / "2026-10-11.json").exists())                                                      # 다른 날은 그대로
        self.assertIn("첫 화면 목록에서 뺌", done)


if __name__ == "__main__":
    unittest.main()
