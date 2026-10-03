"""주일예배 PPT HTML — 발표자 보기 썸네일(2026-10-03 교장님: 아래에 지금 노래의 모든 장, 누르면 앞 화면으로).
실행: python3 -m unittest discover -s worship/tests -v   (jegok-church 폴더에서)
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import slides as S


def sl(n, plain, hidden=""):
    return {"n": n, "w": 1440, "h": 810, "img": f"{n:03d}.jpg", "texts": [{"t": plain}], "plain": plain, "hidden": hidden or plain}


class PresenterThumbTests(unittest.TestCase):
    def page(self):
        slides = [sl(1, "주일예배"), sl(2, "찬양과 경배"), sl(3, "가사 1", "1. 주 품에"), sl(4, "가사 2"), sl(5, "설교")]
        return S.render(slides, "10월 4일 주일예배 PPT", "", ["주 품에"])

    def test_thumb_strip_in_presenter_view(self):
        h = self.page()
        self.assertIn('id="pvthumbs"', h)
        self.assertIn("▶ 예배용</button>", h); self.assertNotIn("▶ 발표</button>", h)   # 단추 이름(2026-10-03 교장님)                    # 지금 앞 화면 아래 썸네일 줄
        self.assertIn("function thumbs(", h)
        self.assertIn("go(", h)                               # 썸네일을 누르면 go(i) → 앞 화면 창으로 전달
        self.assertLess(h.index('id="pvcur"'), h.index('id="pvthumbs"'))

    def test_song_range_from_toc(self):
        h = self.page()
        self.assertIn("function songRange(", h)               # 목차 표시(노래·순서) 사이 = 한 노래의 장들


class FrameOutlineTests(unittest.TestCase):
    """가사가 아직 없는 틀(곡마다 「찬양과경배」 표지 장만) — 자리마다 곡 이름을 단다(2026-10-03)."""
    def test_placeholders_get_song_names(self):
        ph = lambda n: sl(n, "찬양과경배 이 백성은 내가 나를 위하여 지었나니 Praise & Worship")
        creed = "Apostles' Creed 사도신경 " + "나는 전능하신 아버지 하나님 천지의 창조주를 믿습니다 " * 8   # 실제처럼 글이 긴 사도신경 장
        slides = [sl(1, "주일예배"), ph(2), sl(3, creed), ph(4), ph(5), sl(6, "Sermon 설교"),
                  sl(7, "찬양과 결단 이 백성은 Praise & Worship")]
        m = S.outline(slides, ["도입곡A", "곡1", "곡2", "적용B"])
        names = [x[1] for x in m]
        self.assertEqual(names, ["주일예배", "찬양과경배", "♪ 도입곡A", "사도신경", "♪ 곡1", "♪ 곡2", "설교", "찬양과 결단", "♪ 적용B"])
        self.assertEqual([x[0] for x in m if x[1] == "♪ 곡1"], [4])

    def test_lyrics_deck_unchanged(self):
        # 9/27 처럼 표지 뒤에 가사 장이 이어지면 표지에는 곡 이름을 달지 않고, 가사 장이 곡 이름을 받는다
        slides = [sl(1, "찬양과경배 이 백성은 Praise & Worship"), sl(2, "가사", "1. 주 품에 2. …"), sl(3, "Sermon 설교")]
        self.assertEqual([x[1] for x in S.outline(slides, ["주 품에"])], ["찬양과경배", "♪ 주 품에", "설교"])


if __name__ == "__main__":
    unittest.main()
