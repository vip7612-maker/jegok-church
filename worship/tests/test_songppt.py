"""곡별 PPT — 예배 PPT 에서 곡을 잘라 층(악보 그림 · 자막 글 · 절 단추)으로 나눈다 (2026-10-03 교장님 승인).
실행: python3 -m unittest discover -s worship/tests -v   (jegok-church 폴더에서)
"""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import songppt as P


def sl(n, song=True, title="A", creed=False):
    return {"n": n, "song": song, "title_sig": title, "creed": creed}


class SegmentTests(unittest.TestCase):
    def test_split_by_title_and_gap(self):
        s = [sl(1, False), sl(2, title="A"), sl(3, title="A"), sl(4, False), sl(5, title="B"), sl(6, title="B")]
        self.assertEqual(P.segments(s), [(2, 3), (5, 6)])

    def test_creed_slides_are_not_songs(self):
        s = [sl(1, title="A"), sl(2, title="C", creed=True), sl(3, title="C", creed=True), sl(4, False), sl(5, title="B")]
        self.assertEqual(P.segments(s), [(1, 1), (5, 5)])

    def test_single_title_slide_merges_into_next_adjacent(self):
        # 9/27 의 65(첫 장 그림이 다름)+66~70, 105+106~123 처럼 붙어 있는 한 장짜리는 다음 곡 구간에 합친다
        s = [sl(64, False), sl(65, title="T"), sl(66, title="B"), sl(67, title="B"), sl(68, False)]
        self.assertEqual(P.segments(s), [(65, 67)])

    def test_name_by_conti_order(self):
        segs = [(39, 46), (54, 63)]
        self.assertEqual(P.name_segments(segs, ["원하고 바라고 기도합니다", "내겐 만족함이 없었네"]),
                         [("원하고 바라고 기도합니다", 39, 46), ("내겐 만족함이 없었네", 54, 63)])
        self.assertEqual(P.name_segments(segs, ["하나만"]), [("확인필요-39", 39, 46), ("확인필요-54", 54, 63)])  # 개수가 다르면 이름을 붙이지 않는다


class RenderTests(unittest.TestCase):
    def song(self):
        return {"title": "내겐 만족함이 없었네", "slides": [
            {"img": "AAA", "pic": [0, 0, 1920, 987], "sub": {"box": [0, 876, 1920, 204], "size": 72, "fill": "#000000",
                                                               "lines": [{"t": "Взирая на людей", "c": "#ffffff"}, {"t": "I believe", "c": "#ffff00"}]},
             "chips": [{"t": "1.사람을 보며", "to": 0, "on": True}, {"t": "3.저기 빛나는", "to": 1, "on": False}]},
            {"img": "BBB", "pic": [0, 0, 1920, 987], "sub": None, "chips": []}]}

    def test_layers_and_label(self):
        h = P.render(self.song())
        self.assertIn("S.title+' '+(i+1)+'/'+N", h)                                                # 왼쪽 위 「곡명 n/N」(장마다 그린다)
        self.assertIn("'L1 score'", h); self.assertIn("'L2 sub'", h)                                # 악보 층과 자막 층이 따로
        self.assertIn("Взирая на людей", h); self.assertIn("I believe", h)                            # 자막은 글자 그대로(편집 가능)
        self.assertIn('L3 chips', h); self.assertIn("1.사람을 보며", h)                              # 절 단추 줄(슬라이드 아래)
        data = json.loads(h.split('<script id="song" type="application/json">')[1].split("</script>")[0])
        self.assertEqual(data["title"], "내겐 만족함이 없었네")
        self.assertIsNone(data["slides"][1]["sub"])                                                 # 자막 없는 장도 있다

    def test_safe_filename(self):
        self.assertEqual(P.file_name("주 품에/품으소서?"), "주 품에 품으소서.html")


if __name__ == "__main__":
    unittest.main()
