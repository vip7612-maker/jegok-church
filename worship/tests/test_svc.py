"""예배 구분(svc) — 때(날짜·날짜-예배열쇠), 처음 네 가지는 날짜만, 같은 날 여러 예배 (2026-10-07 교장님)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import svc as V

SV = [dict(x) for x in V.DEFAULT] + [
    {"id": "sun2", "name": "주일예배2부", "days": "0", "time": "13:00", "place": "본당", "tpl": "", "ord": 5, "legacy": 0},
    {"id": "youth", "name": "청년예배", "days": "06", "time": "15:00", "place": "청년부실", "tpl": "", "ord": 6, "legacy": 0}]


class SvcTests(unittest.TestCase):
    def test_split_and_urls(self):
        self.assertEqual(V.split("2026-10-11"), ("2026-10-11", None))
        self.assertEqual(V.split("2026-10-11-youth"), ("2026-10-11", "youth"))
        self.assertEqual(V.d8("2026-10-11-youth"), "20261011-youth"); self.assertEqual(V.d8("2026-10-08"), "20261008")
        self.assertEqual(V.from_d8("20261011-youth"), "2026-10-11-youth"); self.assertEqual(V.from_d8("20261008"), "2026-10-08")
        with self.assertRaises(ValueError): V.split("2026-10-11-../x")

    def test_service_of(self):
        self.assertEqual(V.service_of("2026-10-11", SV)["id"], "sun")          # 날짜만 = 그 요일 처음 예배(처음 네 가지 먼저)
        self.assertEqual(V.service_of("2026-10-08", SV)["id"], "dawn")
        self.assertEqual(V.service_of("2026-10-11-sun2", SV)["name"], "주일예배2부")
        self.assertEqual(V.name("2026-10-10-youth", SV), "청년예배")

    def test_occ_of_and_day_list(self):
        self.assertEqual(V.occ_of("2026-10-11", "sun", SV), "2026-10-11")    # 처음 네 가지는 날짜만(지금 자료·주소 그대로)
        self.assertEqual(V.occ_of("2026-10-11", "sun2", SV), "2026-10-11-sun2")
        self.assertEqual(V.occs_on("2026-10-11", SV), ["2026-10-11", "2026-10-11-sun2", "2026-10-11-youth"])
        self.assertEqual(V.occs_on("2026-10-08", SV), ["2026-10-08"])
        self.assertEqual(V.wday("2026-10-11"), 0); self.assertEqual(V.wday("2026-10-10"), 6)

    def test_pipeline_keys(self):   # 같은 날 다른 예배(날짜-열쇠)도 주소·악보집 바탕이 따로
        import publish, weekday
        V._cache["jegok"] = SV
        try:
            self.assertEqual(publish.slug("2026-10-11-youth"), "jegok_worship_20261011-youth")
            self.assertTrue(publish.url("2026-10-11-youth").endswith("/jegok/20261011-youth"))
            self.assertTrue(publish.url("2026-10-11").endswith("/jegok/20261011"))
            self.assertFalse(weekday.sunday_book("2026-10-11-sun2")); self.assertTrue(weekday.sunday_book("2026-10-11"))
            weekday.verses_html = lambda ref: ""
            d = weekday.data_for("2026-10-10-youth", [{"t": "찬양"}])
            self.assertEqual(d["pages"][0]["title"], "청 년 예 배"); self.assertEqual(d["pages"][0]["date"], "2026.10.10")
        finally:
            V._cache.pop("jegok", None)


if __name__ == "__main__":
    unittest.main()
