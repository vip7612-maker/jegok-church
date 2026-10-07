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
        self.assertIn("▶ 예배용(두 화면)</button>", h); self.assertNotIn("▶ 발표</button>", h)   # 단추 이름(2026-10-03 교장님)                    # 지금 앞 화면 아래 썸네일 줄
        self.assertIn("function thumbs(", h)
        self.assertIn("go(", h)                               # 썸네일을 누르면 go(i) → 앞 화면 창으로 전달
        self.assertIn('id="pvcur"', h)                       # 썸네일 줄은 위(pvt), 지금 화면은 옆(pvside) — 자리 바뀜(e4b3c2e 이전 디자인 변경)

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
        # 사도신경 뒤 찬양과경배도 목차에 다시 나온다(2026-10-07 교장님: 찬양과경배 / 사도신경 / 찬양과경배 / 대표기도)
        self.assertEqual(names, ["주일예배", "찬양과경배", "♪ 도입곡A", "사도신경", "찬양과경배", "♪ 곡1", "♪ 곡2", "설교", "찬양과 결단", "♪ 적용B"])
        self.assertEqual([x[0] for x in m if x[1] == "♪ 곡1"], [4])

    def test_lyrics_deck_unchanged(self):
        # 9/27 처럼 표지 뒤에 가사 장이 이어지면 표지에는 곡 이름을 달지 않고, 가사 장이 곡 이름을 받는다
        slides = [sl(1, "찬양과경배 이 백성은 Praise & Worship"), sl(2, "가사", "1. 주 품에 2. …"), sl(3, "Sermon 설교")]
        self.assertEqual([x[1] for x in S.outline(slides, ["주 품에"])], ["찬양과경배", "♪ 주 품에", "설교"])


class OneCoverTests(unittest.TestCase):
    """찬양과경배 표지는 순서마다 1장, 곡은 그 아래 여러 개(2026-10-07 교장님)."""
    ph = staticmethod(lambda n: sl(n, "찬양과경배 이 백성은 Praise & Worship"))
    creed = "Apostles' Creed 사도신경 " + "나는 전능하신 아버지 하나님 천지의 창조주를 믿습니다 " * 8

    def deck(self):   # 템플릿처럼: 표지 1 · 사도신경 · 표지 6장 연달아 · 대표기도 · 결단
        return ([self.ph(1), sl(2, self.creed)] + [self.ph(n) for n in range(3, 9)]
                + [sl(9, "Prayer 대표기도 정상진 장로"), sl(10, "찬양과 결단 이 백성은 Praise & Worship")])

    def test_adjacent_covers_collapse(self):
        out = S.collapse_covers(self.deck())
        self.assertEqual(len(out), 5)
        self.assertEqual([x[1] for x in S.outline(out, [])], ["찬양과경배", "사도신경", "찬양과경배", "대표기도", "찬양과 결단"])
        self.assertEqual([s["n"] for s in out], [1, 2, 3, 4, 5])

    def test_frames_without_songs_still_collapse(self):
        out = S.add_song_frames(self.deck(), "1999-01-03", None)   # 곡 기록 없는 날
        self.assertEqual(len(out), 5)

    def test_song_plan_groups(self):
        g = {"intro": ["도"], "main": ["a", "b", "c"], "apply": ["적"]}
        self.assertEqual(S.song_plan(["경배", "경배", "결단"], g), [["도"], ["a", "b", "c"], ["적"]])
        self.assertEqual(S.song_plan(["경배", "결단"], g), [["도", "a", "b", "c"], ["적"]])
        self.assertEqual(S.song_plan(["경배", "경배"], g), [["도"], ["a", "b", "c", "적"]])
        self.assertEqual(S.song_plan(["결단"], g), [["도", "a", "b", "c", "적"]])
        self.assertEqual(S.song_plan([], g), [])

    def test_song_starts_mark_toc(self):
        f = lambda n, t, start="": dict(sl(n, t), **({"start": start} if start else {}))
        deck = [self.ph(1), f(2, "도입", "도입곡"), sl(3, self.creed), self.ph(4), f(5, "곡a", "곡a"), f(6, "곡a 2장"),
                f(7, "곡b", "곡b"), sl(8, "Prayer 대표기도")]
        self.assertEqual([x[1] for x in S.outline(deck, ["도입곡", "곡a", "곡b"])],
                         ["찬양과경배", "♪ 도입곡", "사도신경", "찬양과경배", "♪ 곡a", "♪ 곡b", "대표기도"])


class PlusInGridTests(unittest.TestCase):
    """교회 소식·특송·설교 ＋ 장 넣기 — 모아 보기에도, 템플릿으로 만든 주에도 (2026-10-07 교장님)."""
    def test_grid_plus_wired(self):
        h = S.render([sl(1, "교회소식"), sl(2, "소식 1"), sl(3, "특송"), sl(4, "설교")], "10월 11일 주일예배 PPT", "", [], date="2026-10-11")
        self.assertIn("const NDATE='2026-10-11'", h)          # 날짜가 빠지면 ＋·끼운 장이 모두 꺼진다
        self.assertIn("window.xpGrid=", h); self.assertIn("xpGrid(k,end)", h); self.assertIn(".gadd", h)

    def test_template_build_passes_date(self):
        src = open(os.path.join(os.path.dirname(S.__file__), "ppt_tpl.py")).read()
        self.assertRegex(src, r"slides\.render\([^\n]*date=")


if __name__ == "__main__":
    unittest.main()
