#!/usr/bin/env python3
"""예배 준비 사전 세팅 테스트 — 구글 API 는 가짜. 실행: python3 -m unittest discover -s worship/tests -v (jegok-church 루트)"""
import io
import os
import sys
import unittest
import zipfile
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import prep  # noqa: E402


class DateNameTests(unittest.TestCase):
    def test_next_sunday(self):
        self.assertEqual(prep.next_sunday(date(2026, 9, 19)), date(2026, 9, 20))   # 토 → 내일
        self.assertEqual(prep.next_sunday(date(2026, 9, 18)), date(2026, 9, 20))   # 금 → 모레
        self.assertEqual(prep.next_sunday(date(2026, 9, 20)), date(2026, 9, 20))   # 일 → 오늘
        self.assertEqual(prep.next_sunday(date(2026, 9, 21)), date(2026, 9, 27))   # 월 → 다음 일요일

    def test_folder_name_matches_existing_pattern(self):
        self.assertEqual(prep.folder_name(date(2026, 9, 20)), "2026 0920 주일예배 이경진")
        self.assertEqual(prep.folder_name(date(2026, 1, 18), "정영화"), "2026 0118 주일예배 정영화")
        self.assertEqual(prep.folder_name(date(2026, 4, 5), suffix="부활주일"), "2026 0405 주일예배 이경진 부활주일")

    def test_file_names(self):
        d = date(2026, 9, 20)
        self.assertEqual(prep.file_name("2026 0000 반주자 및 싱어용 악보", d), "2026 0920 반주자 및 싱어용 악보")
        self.assertEqual(prep.file_name("2026 0000 주일예배 PPT", d), "2026 0920 주일예배 PPT")
        self.assertEqual(prep.file_name("2026 0000 주일예배 PPT", date(2027, 1, 3)), "2027 0103 주일예배 PPT")

    def test_slides_replacement(self):
        r = prep.slides_replacements(date(2026, 9, 20))[0]["replaceAllText"]
        self.assertEqual((r["containsText"]["text"], r["replaceText"]), ("2026.00.00", "2026.09.20"))


def make_pptx(slide1_xml: str, other_xml: str = "<p:sld><p:cSld><p:spTree></p:spTree></p:cSld></p:sld>") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("[Content_Types].xml"), "<Types/>")
        z.writestr("ppt/slides/slide1.xml", slide1_xml)
        z.writestr("ppt/slides/slide2.xml", other_xml)
        z.writestr("ppt/media/image1.png", b"\x89PNG\x00binary")
    return buf.getvalue()


COVER = ('<p:sld><p:txBody><a:p><a:r><a:t>2026년  </a:t></a:r><a:r><a:t>00</a:t></a:r><a:r><a:t>월 </a:t></a:r>'
         '<a:r><a:t>00</a:t></a:r><a:r><a:t>일  /  제곡교회</a:t></a:r></a:p>'
         '<a:p><a:r><a:t>00</a:t></a:r></a:p></p:txBody></p:sld>')   # 두 번째 문단의 00 은 날짜가 아님 → 건드리지 않아야 함


class PptxTests(unittest.TestCase):
    def test_cover_date_runs_replaced_only_in_date_paragraph(self):
        out, n = prep.patch_pptx_date(make_pptx(COVER), date(2026, 9, 20))
        self.assertEqual(n, 2)
        z = zipfile.ZipFile(io.BytesIO(out))
        s1 = z.read("ppt/slides/slide1.xml").decode()
        self.assertIn("<a:t>2026년  </a:t></a:r><a:r><a:t>09</a:t></a:r><a:r><a:t>월 </a:t></a:r><a:r><a:t>20</a:t></a:r><a:r><a:t>일  /  제곡교회</a:t>", s1)
        self.assertIn("<a:p><a:r><a:t>00</a:t></a:r></a:p>", s1)          # 날짜 아닌 00 은 그대로
        self.assertEqual(z.read("ppt/media/image1.png"), b"\x89PNG\x00binary")   # 다른 항목은 바이트 그대로
        self.assertEqual(z.read("ppt/slides/slide2.xml").decode(), "<p:sld><p:cSld><p:spTree></p:spTree></p:cSld></p:sld>")
        self.assertEqual(sorted(z.namelist()), sorted(zipfile.ZipFile(io.BytesIO(make_pptx(COVER))).namelist()))

    def test_year_change(self):
        out, n = prep.patch_pptx_date(make_pptx(COVER), date(2027, 1, 3))
        s1 = zipfile.ZipFile(io.BytesIO(out)).read("ppt/slides/slide1.xml").decode()
        self.assertIn("<a:t>2027년  </a:t>", s1)
        self.assertIn("<a:t>01</a:t>", s1)
        self.assertIn("<a:t>03</a:t>", s1)

    def test_no_date_paragraph_changes_nothing(self):
        src = make_pptx("<p:sld><a:p><a:r><a:t>00</a:t></a:r></a:p></p:sld>")
        out, n = prep.patch_pptx_date(src, date(2026, 9, 20))
        self.assertEqual(n, 0)
        self.assertEqual(zipfile.ZipFile(io.BytesIO(out)).read("ppt/slides/slide1.xml"), zipfile.ZipFile(io.BytesIO(src)).read("ppt/slides/slide1.xml"))


class FakeG:
    """구글 API 가짜 — 폴더/파일 존재 여부를 조절해 멱등성을 검사한다."""
    def __init__(self, existing_folder=None, existing_files=()):
        self.existing_folder = existing_folder; self.existing_files = set(existing_files); self.calls = []
    def find_child(self, parent, name, mime=None):
        if mime == prep.FOLDER_MIME:
            return {"id": "F1", "webViewLink": "https://drive/F1"} if self.existing_folder == name else None
        return {"id": "X", "webViewLink": "https://drive/X"} if name in self.existing_files else None
    def create_folder(self, parent, name): self.calls.append(("folder", name)); return {"id": "F1", "webViewLink": "https://drive/F1"}
    def copy(self, fid, parent, name): self.calls.append(("copy", name)); return {"id": "S1", "webViewLink": "https://slides/S1"}
    def slides_batch(self, pid, reqs): self.calls.append(("slides", pid)); return {"replies": [{"replaceAllText": {"occurrencesChanged": 1}}]}
    def download(self, fid): self.calls.append(("download", fid)); return make_pptx(COVER)
    def upload_pptx(self, parent, name, data): self.calls.append(("upload", name, len(data))); return {"id": "P1", "webViewLink": "https://drive/P1"}


class PrepareFlowTests(unittest.TestCase):
    def test_fresh_run_creates_everything(self):
        g = FakeG()
        with mock.patch.object(prep, "log"):
            res = prep.prepare(date(2026, 9, 20), "이경진", "", g=g)
        kinds = [c[0] for c in g.calls]
        self.assertEqual(kinds, ["folder", "copy", "slides", "download", "upload"])
        self.assertEqual(g.calls[1][1], "2026 0920 반주자 및 싱어용 악보")
        self.assertEqual(g.calls[4][1], "2026 0920 주일예배 PPT")
        self.assertEqual([r["status"] for r in res["results"]], ["copied", "copied"])
        self.assertEqual(res["results"][1]["date_edits"], 2)
        self.assertIn("2026 0920 주일예배 이경진", prep.summary(res))

    def test_idempotent_when_exists(self):
        g = FakeG(existing_folder="2026 0920 주일예배 이경진", existing_files={"2026 0920 반주자 및 싱어용 악보", "2026 0920 주일예배 PPT"})
        with mock.patch.object(prep, "log"):
            res = prep.prepare(date(2026, 9, 20), "이경진", "", g=g)
        self.assertEqual(g.calls, [])                                   # 아무것도 새로 만들지 않음
        self.assertEqual([r["status"] for r in res["results"]], ["exists", "exists"])

    def test_dry_run_touches_nothing(self):
        res = prep.prepare(date(2026, 9, 20), "이경진", "", dry_run=True, g=FakeG())
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["files"], ["2026 0920 반주자 및 싱어용 악보", "2026 0920 주일예배 PPT"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
