"""예배순서(예배준비 화면) ↔ 주보 ↔ 주일예배 PPT 상호 동기화 (2026-10-07 교장님).
실행: python3 -m unittest discover -s worship/tests -p test_order_sync.py   (jegok-church 폴더에서)
"""
import copy, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accomp"))
import order_sync as O


def cover(label, title, main="", n=0):
    t = [{"x": 100, "y": 168, "w": 300, "h": 30, "s": 22.0, "c": "#efe6dd", "b": False, "t": label, "a": "c"},
         {"x": 100, "y": 205, "w": 600, "h": 160, "s": 150.0, "c": "#6b5444", "b": True, "t": title, "a": "c"}]
    if main: t.append({"x": 100, "y": 430, "w": 600, "h": 60, "s": 50.0, "c": "#6b5444", "b": True, "t": main, "a": "c"})
    return {"n": n, "w": 1440, "h": 810, "img": "c.jpg", "texts": t, "plain": " ".join(x["t"] for x in t), "hidden": ""}


def page(plain):
    return {"n": 0, "w": 1440, "h": 810, "img": "p.jpg", "texts": [{"x": 0, "y": 0, "w": 10, "h": 10, "s": 30, "c": "#fff", "t": plain}], "plain": plain, "hidden": ""}


def deck():
    head = {"n": 0, "w": 1440, "h": 810, "img": "k_cover.jpg", "plain": "JEGOK CHURCH 주일예배",
            "texts": [{"x": 0, "y": 148, "w": 10, "h": 10, "s": 22, "c": "#fff", "t": "JEGOK CHURCH"}, {"x": 0, "y": 185, "w": 10, "h": 10, "s": 190, "c": "#fff", "t": "주일예배"}], "hidden": ""}
    end = {"n": 0, "w": 1440, "h": 810, "img": "k_end.jpg", "plain": "예배를 마칩니다 제곡교회",
           "texts": [{"x": 0, "y": 250, "w": 10, "h": 10, "s": 112, "c": "#fff", "t": "예배를 마칩니다"}], "hidden": ""}
    s = [head, cover("Opening", "성경암송", "네 마음을 다하고"), page("이사야 43:1"), page("이사야 43:2"),
         cover("Praise & Worship", "찬양과경배", "이 백성은"), cover("Apostles’ Creed", "사도신경"), page("나는 전능하신"), page("그는 성령으로"),
         cover("Praise & Worship", "찬양과경배", "이 백성은"), cover("Praise & Worship", "찬양과경배", "이 백성은"),
         cover("Prayer", "대표기도", "정상진 장로"), cover("Announcements", "교회 소식"), page("소식 1"),
         cover("Offering", "봉헌", "마리아 어린이"), cover("Scripture Reading", "성경 봉독", "역대상25:1-5"), page("1 다윗이"),
         cover("Special Praise", "특 송", "김용준 안수집사 부부"), cover("Sermon", "설교", "이름없는 사람들"),
         cover("Praise & Worship", "찬양과 결단", "이 백성은"), cover("Benediction", "축도"), end]
    for n, x in enumerate(s, 1): x["n"] = n
    return s


def titles(slides):
    return [O.cover_title(s) or ("·" if s["img"] != "k_end.jpg" else "끝") for s in slides]


JUBO_1011 = [["주님의 기쁨인 아름다운 공동체의 주일예배"], ["오전 10시 30분부터 성경암송이 시작됩니다."],
             ["성경암송", "김은정 권사", "", ""], ["예배인도", "이경진 장로", "", ""], ["경배와 찬양", "다같이", "", ""],
             ["기도", "올랴 선교사", "", ""], ["광고", "정영선 목사", "", ""], ["봉헌", "김하윤 어린이", "", ""],
             ["봉헌기도", "정영선 목사", "", ""], ["성경봉독", "박서준 학생", "", "역대상28:1-10"], ["찬 양", "샤샤&amp;릴리야<br>가정", "", ""],
             ["설교", "정영선 목사", "", "내 아들 솔로몬아"], ["찬양", "다같이", "", "나는 주를 섬기는 것에<br>후회가 없습니다."],
             ["축도", "정영선 목사", "", ""], ["예배를 능가하는 삶도 없고<br>삶을 능가하는 예배도 없습니다."]]


class CanonTests(unittest.TestCase):
    def test_aliases(self):
        for a, b in [("경배와 찬양", "찬양과경배"), ("찬양과 경배", "찬양과경배"), ("광고", "교회소식"), ("교회 소식", "교회소식"),
                     ("기도", "대표기도"), ("특 송", "특송"), ("특별찬양", "특송"), ("성경 봉독", "성경봉독"), ("간증", "간증")]:
            self.assertEqual(O.canon(a), b, a)


class JuboTests(unittest.TestCase):
    def test_jubo_rows_to_items(self):
        j = O.jubo_items(JUBO_1011)
        self.assertEqual([x["t"] for x in j], ["성경암송", "찬양과 경배", "대표기도", "교회소식", "봉헌", "성경봉독", "특송", "설교", "찬양과 결단", "축도"])
        d = {x["t"]: x for x in j}
        self.assertEqual(d["대표기도"]["who"], "올랴 선교사")
        self.assertEqual(d["성경봉독"], {"t": "성경봉독", "who": "박서준 학생", "ref": "역대상28:1-10"})
        self.assertEqual(d["특송"]["who"], "샤샤&릴리야 가정")                     # 「찬 양」이 설교 앞이면 특송, <br>·&amp; 정리
        self.assertEqual(d["설교"], {"t": "설교", "who": "정영선 목사", "title": "내 아들 솔로몬아"})
        self.assertNotIn("ref", d["찬양과 결단"])                                  # 설교 뒤 찬양의 넷째 칸은 곡 이름 — 본문 아님

    def test_pdf_spacing(self):
        j = O.jubo_items([["기도", "올 랴 선교사", "", ""]], pdf=True)
        self.assertEqual(j[0]["who"], "올랴 선교사")

    def test_merge_fills_and_keeps(self):
        items = [dict(x) for x in O.DEFAULT_SUN]
        items[4]["who"] = "손으로 적은 분"                                           # 대표기도 — 이미 적은 값은 그대로
        j = O.jubo_items(JUBO_1011) + [{"t": "간증", "who": "홍길동"}]
        j.insert(5, j.pop())                                                          # 간증을 봉헌 다음에
        m = O.merge_jubo(items, j)
        names = [x["t"] for x in m]
        self.assertEqual(names[:5], ["성경암송", "찬양과 경배", "사도신경", "찬양과 경배", "대표기도"])   # 주보에 없는 사도신경·둘째 경배는 남는다
        self.assertEqual(m[4]["who"], "손으로 적은 분")
        self.assertEqual(names[names.index("봉헌") + 1], "간증")                       # 주보에만 있는 순서는 앞 순서 뒤에 끼운다
        self.assertEqual(next(x for x in m if x["t"] == "설교")["title"], "내 아들 솔로몬아")
        self.assertEqual(len(m), len(O.DEFAULT_SUN) + 1)                             # 지우지 않는다


class RestructureTests(unittest.TestCase):
    def test_from_template_when_no_order(self):
        out = O.restructure(deck(), None, {})
        self.assertEqual([x["t"] for x in O.sections(out)],
                         ["성경암송", "찬양과 경배", "사도신경", "찬양과 경배", "대표기도", "교회소식", "봉헌", "성경봉독", "특송", "설교", "찬양과 결단", "축도"])
        self.assertEqual(titles(out)[0], "주일예배"); self.assertEqual(titles(out)[-1], "끝")

    def test_order_drives_slides(self):
        items = [dict(x) for x in O.DEFAULT_SUN]
        items = [x for x in items if x["t"] != "축도"]                               # 지우면 장이 빠지고
        k = [x["t"] for x in items].index("특송"); sp = items.pop(k)
        items.insert([x["t"] for x in items].index("봉헌"), sp)                      # 옮기면 따라 옮겨지고
        items.insert([x["t"] for x in items].index("설교") + 1, {"t": "간증", "who": "홍길동 집사"})   # 없는 순서는 새 표지
        out = O.restructure(deck(), items, {})
        t = titles(out)
        self.assertNotIn("축도", t)
        self.assertLess(t.index("특 송"), t.index("봉헌"))
        g = out[t.index("간증")]
        self.assertEqual(O.cover_title(g), "간증"); self.assertIn("홍길동 집사", g["plain"])
        self.assertEqual(t[t.index("교회 소식") + 1], "·")                             # 딸린 장(소식)은 표지를 따라간다
        self.assertEqual(t[t.index("사도신경") + 1:t.index("사도신경") + 3], ["·", "·"])
        self.assertEqual([x["t"] for x in O.sections(out)], [x["t"] for x in items])  # 다시 읽으면 같은 순서(PPT → 예배순서)
        self.assertEqual([s["n"] for s in out], list(range(1, len(out) + 1)))

    def test_third_praise_clones_cover(self):
        items = [dict(x) for x in O.DEFAULT_SUN] + [{"t": "찬양과 경배"}]
        out = O.restructure(deck(), items, {})
        self.assertEqual(sum(1 for s in out if O.canon(O.cover_title(s) or "") == "찬양과경배"), 3)

    def test_section_fields_from_info(self):
        info = {"prayer": "올랴 선교사", "sermon": ("정영선 목사", "내 아들 솔로몬아"), "reading": ("박서준 학생", "역대상28:1-10"), "special": "샤샤 가정", "offering": "김하윤 어린이"}
        sec = {x["t"]: x for x in O.sections(O.restructure(deck(), None, info))}
        self.assertEqual(sec["대표기도"]["who"], "올랴 선교사")
        self.assertEqual(sec["설교"], {"t": "설교", "who": "정영선 목사", "title": "내 아들 솔로몬아"})
        self.assertEqual(sec["성경봉독"]["ref"], "역대상28:1-10")

    def test_order_info(self):
        items = [{"t": "대표기도", "who": "가"}, {"t": "성경봉독", "who": "나", "ref": "요 3:16"}, {"t": "설교", "title": "제목"}, {"t": "특송", "who": "다"}, {"t": "봉헌", "who": "라"}]
        info = O.order_info(items, {"sermon": ("정영선 목사", "주보 제목")})
        self.assertEqual(info["prayer"], "가"); self.assertEqual(info["reading"], ("나", "요 3:16"))
        self.assertEqual(info["sermon"], ("정영선 목사", "제목"))                       # 빈 칸은 주보 값을 둔다
        self.assertEqual(info["special"], "다"); self.assertEqual(info["offering"], "라")


class ExtraTests(unittest.TestCase):
    def test_extra_not_duplicated_when_order_has_it(self):
        import slides as S
        items = [dict(x) for x in O.DEFAULT_SUN]
        items.insert([x["t"] for x in items].index("특송") + 1, {"t": "선교 보고", "who": "디마 선교사"})
        out = O.restructure(deck(), items, {})
        ex = [{"after": "SpecialPraise", "base": "ScriptureReading", "label": "Mission Report", "title": "선교 보고", "name": "디마 선교사"}]
        out = S.insert_extra(out, ex, None)
        self.assertEqual(sum(1 for s in out if O.cover_title(s) == "선교 보고"), 1)

    def test_extra_added_and_written_back(self):
        import slides as S
        out = O.restructure(deck(), None, {})
        ex = [{"after": "SpecialPraise", "base": "ScriptureReading", "label": "Mission Report", "title": "선교 보고", "name": "디마 선교사"}]
        out = S.insert_extra(out, ex, None)
        names = [x["t"] for x in O.sections(out)]
        self.assertEqual(names[names.index("특송") + 1], "선교 보고")
        self.assertEqual(O.sections(out)[names.index("선교 보고")].get("who"), "디마 선교사")


class SameDefaultTests(unittest.TestCase):
    def test_python_and_api_default_sunday_match(self):
        import re
        js = open(os.path.expanduser("~/dev/daily-briefing/report-site/api/wadmin.js")).read()
        arr = re.search(r"const sun = \[(.*?)\];", js).group(1)
        self.assertEqual(re.findall(r"'([^']+)'", arr), [x["t"] for x in O.DEFAULT_SUN])

    def test_prep_role_fields_match(self):   # 예배준비 화면 ROLE 과 같은 순서에 맡은 분 칸
        h = open(os.path.expanduser("~/dev/daily-briefing/report-site/jegok_worship/prep.html")).read()
        for c in O.FIELDS: self.assertIn(c, h)


if __name__ == "__main__":
    unittest.main()
