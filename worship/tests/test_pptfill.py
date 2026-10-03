"""주일예배 PPT 채우기 — 암송 줄 나누기·사도신경 글 다듬기·글 넘침 계산 (네트워크 없이).
실행: python3 -m unittest discover -s worship/tests -v   (jegok-church 폴더에서)
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import pptfill as F


class PptFillTests(unittest.TestCase):
    def test_recite_lines_break_at_endings(self):
        v = "너희가 나를 택한 것이 아니요 내가 너희를 택하여 세웠나니 이는 너희로 가서 열매를 맺게 하고 또 너희 열매가 항상 있게 하여 내 이름으로 아버지께 무엇을 구하든지 다 받게 하려 함이라"
        self.assertEqual(F.lines_of(v), ["너희가 나를 택한 것이 아니요 ", "내가 너희를 택하여 세웠나니 ", "이는 너희로 가서 열매를 맺게 하고 ",
                                         "또 너희 열매가 항상 있게 하여 ", "내 이름으로 아버지께 무엇을 구하든지 ", "다 받게 하려 함이라"])
        self.assertTrue(all(len(l.strip()) <= 23 for l in F.lines_of("이제부터는 너희를 종이라 하지 아니하리니 종은 주인이 하는 것을 알지 못함이라 너희를 친구라 하였노니 내가 내 아버지께 들은 것을 다 너희에게 알게 하였음이라")))

    def test_creed_text_cleanup(self):
        self.assertEqual(F._clean("본디오빌라도에게 고난을 받아"), "본디오 빌라도에게 고난을 받아")
        self.assertEqual(F._clean("страдал при Понтии Пилате,был распят"), "страдал при Понтии Пилате, был распят")
        self.assertEqual(F._clean("оттуда придёт судитьживых и мертвых ."), "оттуда придёт судить живых и мертвых.")
        self.assertEqual([F.script(x) for x in ("나는", "Верую", "I believe")], ["ko", "ru", "en"])

    def test_line_count_estimate(self):
        # 60pt 한 줄(안쪽 폭 1327pt)에 「제곡교회를 찾아 주신 여러분들을 진심으로 환영합니다.」는 두 줄(실제 구글 렌더링과 같음)
        self.assertEqual(F._lines_needed("제곡교회를 찾아 주신 여러분들을 진심으로 환영합니다.", 60, 1327), 2)
        self.assertEqual(F._lines_needed("2. 모임", 60, 1327), 1)
        # 성경암송 표지 부제(칸 안쪽 폭 883pt): 46pt 면 두 줄로 넘어가고 44pt 면 한 줄(교장님: 한 줄에 들어가야)
        t = "네 마음을 다하고 뜻을 다하고 힘을 다하여"
        self.assertEqual(F._lines_needed(t, 46.24, 883), 2); self.assertEqual(F._lines_needed(t, 44, 883), 1)


if __name__ == "__main__":
    unittest.main()
