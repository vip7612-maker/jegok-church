"""새벽·수요·금요 악보집 바탕(weekday) — 예배 이름·말씀 쪽·곡 자리 (2026-10-07)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import weekday as W


class WeekdayTests(unittest.TestCase):
    def test_service_names(self):
        self.assertEqual([W.service(d) for d in ("2026-10-11", "2026-10-07", "2026-10-09", "2026-10-08", "2026-10-05")],
                         ["주일예배", "수요예배", "금요예배", "새벽예배", "새벽예배"])

    def test_data_for_dawn(self):
        W.verses_html = lambda ref: "<b class='vn'>1</b> 여호와는 나의 목자시니"
        d = W.data_for("2026-10-08", [{"t": "찬송"}, {"t": "성경봉독", "ref": "시편23편"}, {"t": "말씀", "title": "선한 목자"}])
        self.assertEqual([p["type"] for p in d["pages"]], ["cover", "sermon_text", "songs", "songs", "songs"])
        self.assertEqual(d["pages"][0]["title"], "새 벽 예 배")
        self.assertEqual((d["pages"][1]["ref"], d["pages"][1]["title"]), ("시편23편", "선한 목자"))
        self.assertEqual(d["service"], "새벽예배")
        nd = W.data_for("2026-10-08", [{"t": "찬송"}])
        self.assertNotIn("sermon_text", [p["type"] for p in nd["pages"]])   # 본문·제목이 없으면 말씀 쪽 없음


if __name__ == "__main__":
    unittest.main()
