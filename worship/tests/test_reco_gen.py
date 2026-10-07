"""말씀에 맞는 곡 + 예배 방향 글(reco_gen) — 본문·제목 찾기, 교회 곡 목록 밖 곡은 버림, 방향 글 5줄 이내 (2026-10-07)."""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import reco_gen as R, publish


class RecoTests(unittest.TestCase):
    def test_source_dawn_and_sunday(self):
        dawn = [{"t": "찬송"}, {"t": "성경봉독", "ref": "시편23편"}, {"t": "말씀", "title": "선한 목자"}]
        self.assertEqual(R.source(dawn), ("시편23편", "선한 목자"))          # 새벽예배 「말씀」 = 설교
        self.assertEqual(R.source([{"t": "설교", "title": "제목만"}]), ("", "제목만"))
        self.assertEqual(R.source([{"t": "찬송"}]), ("", ""))

    def test_make_filters_and_limits(self):
        tb = {publish.song_key(t): {"t": t, "tempo": tp, "deep": d} for t, tp, d in
              [("주는 나의 목자", "느린곡", True), ("내가 매일 기쁘게", "빠른곡", False)]}
        R.table = lambda: tb; R.bible = lambda ref: "1 여호와는 나의 목자시니"
        fake = lambda p: json.dumps({"theme": "목자 되신 주", "guide": "1\n2\n3\n4\n5\n6\n7",
                                     "songs": [{"title": "주는 나의 목자", "why": "목자 고백"}, {"title": "지어낸 곡", "why": "x"},
                                               {"title": "내가 매일 기쁘게", "why": "기쁨"}, {"title": "주는 나의 목자", "why": "중복"}]}, ensure_ascii=False)
        d = R.make("2026-10-08", [{"t": "성경봉독", "ref": "시편23편"}], run=fake)
        self.assertEqual([x["title"] for x in d["ccm"]], ["주는 나의 목자", "내가 매일 기쁘게"])   # 목록 밖·중복은 버림
        self.assertEqual(d["ccm"][0], {"title": "주는 나의 목자", "tempo": "느린곡", "deep": True, "why": "목자 고백"})
        self.assertEqual(len(d["guide"].splitlines()), 5)                                       # 5줄까지만
        self.assertIsNone(R.make("2026-10-08", [{"t": "찬송"}], run=fake))                       # 본문·제목 없으면 안 만듦

    def test_summary_only(self):   # 본문·제목이 없어도 주보 설교 요약만으로 — 요약이 프롬프트에 들어간다
        import publish
        tb = {publish.song_key("주는 나의 목자"): {"t": "주는 나의 목자", "tempo": "느린곡", "deep": True}}
        R.table = lambda: tb; R.bible = lambda ref: ""
        seen = {}
        def fake(p):
            seen["p"] = p
            return json.dumps({"theme": "t", "guide": "g", "songs": [{"title": "주는 나의 목자", "why": "w"}]}, ensure_ascii=False)
        d = R.make("2026-10-08", [{"t": "찬송"}], run=fake, summary="다윗은 솔로몬에게 하나님을 알라고 당부합니다")
        self.assertIn("다윗은 솔로몬에게", seen["p"]); self.assertTrue(d["summary"]); self.assertEqual(len(d["ccm"]), 1)


if __name__ == "__main__":
    unittest.main()
