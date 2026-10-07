"""주보 PDF 예배순서 읽기 규칙(jubo_rules) — 꼴이 다른 주보 세 가지 + 제곡교회 (2026-10-07 교장님).
fixtures/jubo_fmt_*.md = 시험용으로 지어 만든 주보 PDF 를 kordoc 으로 바꾼 글(교회·사람 이름은 지어낸 것).
"""
import os, sys, unittest
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(H), "accomp"))
import jubo_rules as R

fx = lambda n: open(os.path.join(H, "fixtures", f"jubo_fmt_{n}.md")).read()
NO = lambda md: None   # Claude 를 부르지 않는다


class Pieces(unittest.TestCase):
    def test_names(self):
        for a, b in [("헌금", "봉헌"), ("신앙고백", "사도신경"), ("말 씀", "설교"), ("광 고", "교회소식"), ("축복선언", "축도"), ("공중기도", "대표기도"),
                     ("말씀봉독", "성경봉독"), ("①기도", "대표기도"), ("설교(말씀)", "설교")]:
            self.assertEqual(R.name_of(a), b, a)
        self.assertIsNone(R.name_of("예배인도")); self.assertIsNone(R.name_of("헌금위원")); self.assertFalse(R.name_of("주차안내"))

    def test_who(self):
        for a, b in [("정영선 목 사", "정영선 목사"), ("올 랴 선교사", "올랴 선교사"), ("김용준안수집사부부", "김용준 안수집사 부부"),
                     ("담임목사 홍길동", "담임목사 홍길동"), ("담임목사", "담임목사"), ("다 같 이", "다같이"), ("청년부 중창단", "청년부 중창단")]:
            self.assertEqual(R.fix_who(a), b, a)

    def test_ref_hymn_quote(self):
        g = R.read_row(["「빛의 자녀처럼」 (엡 5:8-14)", "담임목사 한성민"])
        self.assertEqual(g, {"ref": "엡 5:8-14", "title": "빛의 자녀처럼", "who": "담임목사 한성민"})
        self.assertEqual(R.read_row(["새찬송가 8장", "다같이"]), {"hymn": "새찬송가 8장", "who": "다같이"})
        self.assertEqual(R.read_row(["시편 23편"])["ref"], "시편 23편")

    def test_verify_drops_invented(self):
        md = "<table><tr><td>설교</td><td>정영선 목사</td></tr></table>"
        self.assertEqual(R.verify([{"t": "설교", "who": "정영선 목사", "title": "지어낸 제목"}], md), [{"t": "설교", "who": "정영선 목사"}])


class Formats(unittest.TestCase):
    def test_a_table_two_services(self):   # 표, 1부·2부 칸, 아래 오후 예배 — 1부만, 오후 예배는 끊는다
        items, how = R.read(fx("a"), ask=NO)
        self.assertEqual(how["by"], "rules")
        self.assertEqual([x["t"] for x in items], ["예배의 부름", "찬양과 경배", "사도신경", "대표기도", "성경봉독", "특송", "설교", "봉헌", "교회소식", "축도"])
        d = {x["t"]: x for x in items}
        self.assertEqual(d["대표기도"]["who"], "김철수 장로")                 # 1부 칸
        self.assertEqual(d["성경봉독"]["ref"], "요한복음 3:16-21")
        self.assertEqual(d["설교"], {"t": "설교", "who": "박영호 목사", "title": "하나님의 사랑"})
        self.assertEqual(d["사도신경"]["who"], "다같이")                       # 내용 칸 「사도신경」은 맡은 분이 아님
        self.assertEqual(d["특송"]["who"], "호산나 찬양대")                     # 봉독~설교 사이 찬양대 = 특송

    def test_b_dotted_lines(self):         # 점선으로 이은 글줄, 글자 사이 빈칸
        items, how = R.read(fx("b"), ask=NO)
        d = {x["t"]: x for x in items}
        self.assertEqual(d["대표기도"]["who"], "정미경 집사")
        self.assertEqual(d["성경봉독"]["ref"], "에베소서 5:8-14")
        self.assertEqual(d["설교"], {"t": "설교", "who": "담임목사 한성민", "title": "빛의 자녀처럼"})
        self.assertEqual(d["특송"]["who"], "청년부 중창단")
        self.assertEqual(d["축도"]["who"], "담임목사")

    def test_c_fragmented_uses_claude_then_verifies(self):   # 칸이 쪼개진 PDF — Claude 값을 먼저, 원문에 없으면 버림
        self.assertTrue(R.fragmented(R.find_block(R.rows_of(fx("c")))))
        fake = lambda md: R.from_llm([{"name": "경배와 찬양", "who": "찬양팀"}, {"name": "공중기도", "who": "오세훈 집사"},
                                      {"name": "말씀봉독", "who": "최은지 자매", "ref": "마가복음 10:46-52"},
                                      {"name": "말씀선포", "who": "윤재석 목사", "title": "보지 못하던 자가 보다"},
                                      {"name": "헌신찬양", "who": "다함께"}, {"name": "축복선언", "who": "윤재석 목사", "title": "지어낸 말"}])
        items, how = R.read(fx("c"), ask=fake)
        self.assertEqual(how["by"], "claude+rules")
        d = {x["t"]: x for x in items}
        self.assertEqual(d["대표기도"]["who"], "오세훈 집사")
        self.assertEqual(d["설교"], {"t": "설교", "who": "윤재석 목사", "title": "보지 못하던 자가 보다"})
        self.assertEqual(d["성경봉독"]["ref"], "마가복음 10:46-52")
        self.assertNotIn("title", d["축도"])

    def test_c_without_claude_still_returns_order(self):
        items, how = R.read(fx("c"), ask=lambda md: (_ for _ in ()).throw(RuntimeError("꺼짐")))
        self.assertIn("claude_error", how)
        self.assertGreaterEqual(len(items), 5)


if __name__ == "__main__":
    unittest.main()
