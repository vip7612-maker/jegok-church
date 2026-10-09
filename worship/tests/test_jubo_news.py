"""PDF 주보로 바꿔 올려도 교회 소식은 같은 날 한글 주보(prev/ 로 밀려난 것 포함)에서 (2026-10-09 교장님 10/11 주보)."""
import os, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import ppt_tpl as P
import jubo_form


class NewsFallbackTests(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp()); (self.t / "jubo" / "prev").mkdir(parents=True)
        self.old = (P.HERE, jubo_form.kordoc, jubo_form.parse)
        P.HERE = self.t
        jubo_form.kordoc = lambda b: (b.decode(), None)
        jubo_form.parse = lambda md: {"news": ["소식:" + md] if md.startswith("HWP") else [], "order": []}

    def tearDown(self):
        P.HERE, jubo_form.kordoc, jubo_form.parse = self.old

    def test_pdf_only_reads_news_from_prev_hwp(self):
        J = self.t / "jubo"
        (J / "prev" / "2026-10-11.hwp.1").write_bytes(b"HWP old"); os.utime(J / "prev" / "2026-10-11.hwp.1", (1, 1))
        (J / "prev" / "2026-10-11.hwp.2").write_bytes(b"HWP new")
        (J / "2026-10-11.pdf").write_bytes(b"PDF")
        self.assertEqual(P.jubo_info("2026-10-11")["news"], ["소식:HWP new"])

    def test_current_hwp_wins(self):
        J = self.t / "jubo"
        (J / "2026-10-11.hwp").write_bytes(b"HWP now"); (J / "prev" / "2026-10-11.hwp.9").write_bytes(b"HWP old")
        self.assertEqual(P.jubo_info("2026-10-11")["news"], ["소식:HWP now"])

    def test_nothing(self):
        self.assertEqual(P.jubo_info("2026-10-11"), {})


if __name__ == "__main__":
    unittest.main()
