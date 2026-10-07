"""곡 빠르기 표(song_tempo) — 추천 값 먼저, 손으로 고친 값은 그대로, Claude 답은 목록에 있는 곡만 (2026-10-07)."""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import song_tempo as T


class TempoTests(unittest.TestCase):
    def test_classify_keeps_only_asked_titles(self):
        fake = lambda p: json.dumps([{"t": "비를 준비하시니", "tempo": "중간곡", "deep": True},
                                     {"t": "지어낸 곡", "tempo": "빠른곡", "deep": False},
                                     {"t": "주의 보좌로 나아갑니다", "tempo": "아주빠름", "deep": False}], ensure_ascii=False)
        got = T.classify(["비를 준비하시니", "주의 보좌로 나아갑니다"], run=fake)
        self.assertEqual(list(got), [T.key("비를 준비하시니")])            # 목록 밖 곡·이상한 빠르기는 버림
        self.assertTrue(got[T.key("비를 준비하시니")]["deep"])

    def test_build_priority(self):
        k1, k2, k3 = T.key("가"), T.key("나"), T.key("다")
        table = {k3: {"t": "다", "tempo": "느린곡", "deep": True, "by": "manual"}}
        titles = {k1: "가", k2: "나", k3: "다"}
        reco = {k1: ("가", "빠른곡"), k3: ("다", "빠른곡")}
        cls = {k1: {"t": "가", "tempo": "느린곡", "deep": False}, k2: {"t": "나", "tempo": "중간곡", "deep": True}}
        out = T.build(table, titles, reco, cls)
        self.assertEqual(out[k1], {"t": "가", "tempo": "빠른곡", "deep": False, "by": "reco"})   # 추천 빠르기가 먼저
        self.assertEqual(out[k2], {"t": "나", "tempo": "중간곡", "deep": True, "by": "claude"})
        self.assertEqual(out[k3]["by"], "manual"); self.assertEqual(out[k3]["tempo"], "느린곡")   # 손으로 고친 값은 그대로


if __name__ == "__main__":
    unittest.main()
