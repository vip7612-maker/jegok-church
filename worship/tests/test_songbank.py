"""곡별 PPT 모으기 — 머리글 읽기·곡명 맞추기·콘티 기록 읽기 규칙 (네트워크 없이).
실행: python3 -m unittest discover -s worship/tests -v   (jegok-church 폴더에서)
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import songbank as B


class NameTests(unittest.TestCase):
    def test_header_icon_and_hymn_number(self):
        self.assertIn("내가 늘 의지하는 예수", B.header_variants("3 86장 내가 늘 의지하는 예수 - 통86")[0])
        self.assertEqual(B.header_variants("3 86장 내가 늘 의지하는 예수 - 통86")[1], 86)
        self.assertIn("말씀 앞에서", B.header_variants("고 말씀 앞에서")[0])          # 앞 아이콘이 글자로 읽힌 것
        self.assertIn("주 예수 나의 산 소망", B.header_variants("주 예수 나의 산 소망")[0])   # 진짜 첫 글자는 남긴다

    def test_clean_conti_title(self):
        self.assertEqual(B.clean_title("무명이어도 G (충만)"), ("무명이어도", ["충만"]))
        self.assertEqual(B.clean_title("주 은혜임을 G→A")[0], "주 은혜임을")
        self.assertEqual(B.clean_title("주와 같이 길 가는 것 E (찬송가430장)"), ("주와 같이 길 가는 것", []))

    def test_similarity(self):
        self.assertGreater(B.sim("우리는 기대하고", "우리는 기대하고 기도하며 기다리네"), 0.9)    # 악보집의 짧은 이름
        self.assertGreater(B.sim("주와 같이 킬 가는 것", "주와 같이 길 가는 것"), 0.86)            # 인식 오타
        self.assertLess(B.sim("주를 찬양", "주 이름 찬양"), 0.86)                                  # 다른 곡은 붙이지 않는다

    def test_conti_weeks(self):
        t = "26 0823\n2026년 8월 23일 주일예배콘티\n도입\n* 무명이어도 G (충만)\n메인\n* 풀은 마르고 꽃은 시드나 G\n25 1123\n* 주님 말씀하시면 D\n"
        self.assertEqual(B.conti_weeks(t), {"2026-08-23": ["무명이어도 G (충만)", "풀은 마르고 꽃은 시드나 G"], "2025-11-23": ["주님 말씀하시면 D"]})

    def test_dictionary_prefers_conti_name(self):
        D = B.Dictionary(); D.add("무명이어도", ["충만"], prio=1); D.add("주님 다시 오실 때까지", prio=3)
        self.assertEqual(D.match("충만")[0], "무명이어도")

    def test_source_dates(self):
        self.assertEqual(B.date_of("2025 1123 제곡교회예배.pptx", ""), "2025-11-23")
        self.assertEqual(B.date_of("24,08,25 주일예배.pdf", ""), "2024-08-25")
        self.assertEqual(B.date_of("2024_0728_제곡교회예배", ""), "2024-07-28")
        self.assertFalse(B.is_service_ppt("486장 이 세상에 근심된 일이 많고.pptx"))
        self.assertFalse(B.is_service_ppt("2024_0728_ 제곡교회예배_반주자,싱어"))
        self.assertTrue(B.is_service_ppt("2026 0823 주일예배 PPT"))


if __name__ == "__main__":
    unittest.main()
