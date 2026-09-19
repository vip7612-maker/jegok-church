#!/usr/bin/env python3
"""콘티 추천 파이프라인 테스트 — kordoc·Claude·yt-dlp·드라이브는 가짜. 실행: python3 -m unittest discover -s worship/tests -v"""
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conti  # noqa: E402

FIX = Path(__file__).with_name("fixture_jubo.md").read_text(encoding="utf-8")


class DateTests(unittest.TestCase):
    def test_from_filename(self):
        self.assertEqual(conti.date_from_filename("20260920 주일 주보.hwp"), date(2026, 9, 20))
        self.assertEqual(conti.date_from_filename("주보_2026-09-27.hwp"), date(2026, 9, 27))
        self.assertIsNone(conti.date_from_filename("주보.hwp"))
        self.assertIsNone(conti.date_from_filename("20261399.hwp"))


class SermonParseTests(unittest.TestCase):
    def test_real_bulletin(self):
        s = conti.parse_sermon(FIX)
        self.assertEqual(s["title"], "귀향(歸鄕) 공동체")
        self.assertEqual(s["scripture"], "역대상 9:1-44")
        self.assertIn("바벨론 포로생활", s["summary"])
        self.assertEqual(len(s["points"]), 3)
        self.assertTrue(s["points"][0].startswith("첫째"))
        self.assertNotIn("샘터모임", s["summary"])          # 다음 절은 포함하지 않는다
        self.assertNotIn("귀향(歸鄕) 공동체\n", s["summary"][:20])

    def test_missing_section(self):
        s = conti.parse_sermon("<p>아무 내용</p>")
        self.assertEqual((s["title"], s["scripture"], s["summary"]), ("", "", ""))


class RepertoireTests(unittest.TestCase):
    TXT = "26 0906\n2026년 9월 6일 주일예배콘티\n도입\n* 긴 어둠 속에 영광의 빛 잃고 (하나님의 등불) A\n메인\n* 주 은혜임을 G→A\n* 모든 것 들으시는 주 E (하나님 선하시다)\n* 주 은혜임을 G\n적용\n* 베드로의 고백 G\n"

    def test_parse(self):
        rep = conti.parse_repertoire(self.TXT)
        self.assertEqual(rep["주 은혜임을"]["count"], 2)
        self.assertEqual(rep["주 은혜임을"]["keys"], {"G→A": 1, "G": 1})
        self.assertEqual(rep["긴 어둠 속에 영광의 빛 잃고"]["alt"], ["하나님의 등불"])
        self.assertEqual(rep["모든 것 들으시는 주"]["alt"], ["하나님 선하시다"])
        self.assertEqual(list(rep)[0], "주 은혜임을")           # 빈도순
        self.assertEqual(conti.main_key(rep["주 은혜임을"]), "G→A")


class NormalizeTests(unittest.TestCase):
    def test_counts_and_tempo_aliases(self):
        ccm = [{"title": f"곡{i}", "key": "G", "tempo": t} for i, t in enumerate(["빠름"] * 7 + ["medium"] * 8 + ["느린곡"] * 6 + ["이상"])]
        hymns = [{"no": 1, "title": f"찬{i}", "key": "G", "tempo": t} for i, t in enumerate(["빠른곡"] * 3 + ["중간곡"] * 4 + ["느린곡"] * 2)]
        r = conti.normalize({"theme": "x", "ccm": ccm, "hymns": hymns})
        self.assertEqual(r["counts"]["ccm"], {"빠른곡": 6, "중간곡": 8, "느린곡": 6})   # 7개 → 6개로 잘림, 이상 태그 제외
        self.assertEqual(len(r["ccm"]), 20)
        self.assertEqual(len(r["hymns"]), 9)                                        # 찬송가 후보는 전부 보관
        kept, short = conti.trim(r["hymns"], conti.DIST_HYMN)
        self.assertEqual((len(kept), short), (9, {"느린곡": 1}))

    def test_verify_hymns_by_youtube_title(self):
        hymns = [{"no": 430, "title": "주와 같이 길 가는 것", "tempo": "중간곡", "key": "E"},
                 {"no": 999, "title": "없는 찬송", "tempo": "빠른곡", "key": "G"},
                 {"no": 191, "title": "내가 매일 기쁘게", "tempo": "빠른곡", "key": "G"}]
        def fake(q, n=3, timeout=40):
            if "430" in q: return [{"title": "[새찬송가] 430장 주와 같이 길 가는 것", "url": "u430", "duration": 200}]
            if "191" in q: return [{"title": "[새찬송가]192장 내가 매일 기쁘게", "url": "bad", "duration": 200},
                                  {"title": "191 내가 매일 기쁘게", "url": "u191", "duration": 200}]
            return [{"title": "전혀 다른 영상", "url": "x", "duration": 100}]
        with mock.patch.object(conti, "yt_search", fake):
            out = conti.verify_hymns(hymns, workers=1)
        self.assertEqual([(h["no"], h["url"]) for h in out], [(430, "u430"), (191, "u191")])   # 999 탈락, 192장 영상은 191 로 안 침

    def test_prompt_template_formats(self):
        txt = conti.PROMPT.format(title="t", scripture="s", summary="x", repertoire="r")
        self.assertIn('"ccm":[', txt)
        self.assertIn("첫 글자가 {)", txt)

    def test_extract_json_fenced(self):
        self.assertEqual(conti._extract_json('```json\n{"theme":"t","ccm":[],"hymns":[]}\n```')["theme"], "t")


class YoutubeTests(unittest.TestCase):
    def test_pick_prefers_full_length(self):
        rows = [{"title": "쇼츠", "url": "u1", "duration": 40}, {"title": "라이브", "url": "u2", "duration": 300}]
        self.assertEqual(conti.pick_video(rows), "u2")
        self.assertEqual(conti.pick_video([{"title": "x", "url": "u1", "duration": 40}]), "u1")
        self.assertEqual(conti.pick_video([]), "")

    def test_search_parses_yt_dlp_output(self):
        out = "제목A\thttps://youtu.be/a\t250\n제목B\thttps://youtu.be/b\tNA\n"
        with mock.patch.object(conti.subprocess, "run", return_value=mock.Mock(stdout=out)):
            rows = conti.yt_search("q")
        self.assertEqual(rows[0]["duration"], 250.0)
        self.assertEqual(rows[1]["duration"], 0)

    def test_attach_links_uses_search_field(self):
        rec = {"ccm": [{"title": "a", "search": "a 찬양팀", "tempo": "빠른곡", "key": "G"}], "hymns": [{"no": 305, "title": "b", "tempo": "느린곡", "key": "G"}]}
        seen = []
        def fake(q, n=3, timeout=40):
            seen.append(q); return [{"title": q, "url": f"https://y/{len(seen)}", "duration": 200}]
        rec["hymns"].append({"no": 1, "title": "이미 링크", "tempo": "빠른곡", "key": "G", "url": "https://have"})
        with mock.patch.object(conti, "yt_search", fake):
            conti.attach_links(rec, workers=1)
        self.assertEqual(seen, ["a 찬양팀", "새찬송가 305장 b"])            # url 있는 항목은 다시 검색하지 않음
        self.assertTrue(rec["hymns"][0]["url"].startswith("https://y/"))


class FormatTests(unittest.TestCase):
    def test_format_matches_spec(self):
        rec = {"theme": "돌아옴", "short": {},
               "ccm": [{"title": "아름다운 마음들이 모여서", "key": "C", "tempo": "빠른곡", "url": "http://a"},
                       {"title": "주 은혜임을", "key": "G", "tempo": "중간곡", "url": ""},
                       {"title": "시선", "key": "E", "tempo": "느린곡", "url": "http://c"}],
               "hymns": [{"no": 305, "title": "나 같은 죄인 살리신", "key": "G", "tempo": "느린곡", "url": "http://h"}]}
        t = conti.format_text(date(2026, 9, 20), {"title": "귀향 공동체", "scripture": "역대상 9:1-44"}, rec)
        self.assertIn("🎵 9/20(일) 주일예배 콘티 추천", t)
        self.assertIn("<빠른곡>\n1. 아름다운 마음들이 모여서 C코드 http://a", t)
        self.assertIn("<중간곡>\n1. 주 은혜임을 G코드 (링크 못 찾음)", t)
        self.assertIn("[찬송가 1곡]", t)
        self.assertIn("1. 305장 나 같은 죄인 살리신 G코드 http://h", t)
        self.assertNotIn("정원 미달", t)

    def test_chunks(self):
        text = "\n".join(f"{i}. 곡" for i in range(3000))
        chunks = conti.telegram_chunks(text, 3900)
        self.assertTrue(all(len(c) <= 3900 for c in chunks))
        self.assertEqual("\n".join(chunks), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
