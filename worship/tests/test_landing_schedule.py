"""예배 플랫폼 첫 화면의 예배 단추 넷(새벽·수요·금요·주일) — 지금 어느 예배를 띄울지 (2026-10-07 교장님).

규칙: 예배가 끝나고 1시간이 지나면 다음 예배로 넘어간다.
  새벽 월~금 05:00~06:00(07:00에 넘어감, 토요일 새벽 없음) · 수요 19:30~20:30 · 금요 19:30~20:30(21:30에 넘어감)
  주일은 하루 종일 「오늘」, 자정에 월요일 새벽으로.
페이지의 JS(publish.SCHED_JS)를 node 로 그대로 돌려 본다.
"""
import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "accomp"))
import publish


def SJ():   # 예배 탭은 예배 구분 표에서(게시 때 넣는다) — 시험은 처음 네 가지로
    import svc
    return publish.SCHED_JS.replace("@@SVCS@@", json.dumps([{k: v[k] for k in ("id", "name", "days", "time", "place", "legacy")} for v in svc.DEFAULT], ensure_ascii=False))  # noqa: E402

# (한국 시간, 기대: 단추, 그 예배 날짜, 상태)   2026-10-05 월 · 10-07 수 · 10-09 금 · 10-10 토 · 10-11 일
CASES = [
    ("2026-10-07T06:30", "dawn", "2026-10-07", "done"),    # 수 새벽 끝난 뒤 1시간 안
    ("2026-10-07T07:00", "wed",  "2026-10-07", "ready"),   # 수 아침 7시 → 수요예배 준비 중
    ("2026-10-07T13:00", "wed",  "2026-10-07", "ready"),
    ("2026-10-07T19:45", "wed",  "2026-10-07", "live"),
    ("2026-10-07T21:00", "wed",  "2026-10-07", "done"),
    ("2026-10-07T21:30", "dawn", "2026-10-08", "ready"),   # 끝나고 1시간 뒤 → 다음 날 새벽
    ("2026-10-08T05:10", "dawn", "2026-10-08", "live"),
    ("2026-10-08T07:00", "dawn", "2026-10-09", "ready"),   # 목 낮 → 금 새벽
    ("2026-10-09T07:00", "fri",  "2026-10-09", "ready"),   # 금 아침 7시 → 금요예배 준비 중
    ("2026-10-09T20:00", "fri",  "2026-10-09", "live"),
    ("2026-10-09T21:30", "sun",  "2026-10-11", "ready"),   # 금요 끝나야 주일로(토 새벽 없음)
    ("2026-10-10T05:30", "sun",  "2026-10-11", "ready"),   # 토요일 새벽은 없다
    ("2026-10-11T00:00", "sun",  "2026-10-11", "live"),    # 주일 하루 종일
    ("2026-10-11T23:59", "sun",  "2026-10-11", "live"),
    ("2026-10-12T00:00", "dawn", "2026-10-12", "ready"),   # 월요일 0시 → 월 새벽
    ("2026-10-05T12:00", "dawn", "2026-10-06", "ready"),   # 월 낮 → 화 새벽
]


@unittest.skipUnless(shutil.which("node"), "node 없음")
class Schedule(unittest.TestCase):
    def test_cases(self):
        js = SJ() + "\nconst C=" + json.dumps(CASES) + ";\n" + r"""
const out=C.map(([t])=>{const r=svcAt(new Date(t+':00Z'));return [r.k,r.date,r.state];});
console.log(JSON.stringify(out));"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
        got = json.loads(subprocess.run(["node", f.name], capture_output=True, text=True, check=True).stdout)
        for (t, *want), g in zip(CASES, got):
            with self.subTest(t=t):
                self.assertEqual(g, want)

    def test_next_of_each(self):
        """다른 단추를 눌렀을 때: 그 예배의 다음 날짜 (수요일 13시 기준)."""
        js = SJ() + r"""
const n=new Date('2026-10-07T13:00:00Z');
console.log(JSON.stringify(['dawn','wed','fri','sun'].map(k=>{const r=nextOf(k,n);return [r.date,r.state];})));"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
        got = json.loads(subprocess.run(["node", f.name], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(got, [["2026-10-08", "ready"], ["2026-10-07", "ready"], ["2026-10-09", "ready"], ["2026-10-11", "ready"]])

    def test_leader_from_path(self):
        """지난 예배 폴더 이름(「2026 0118 주일예배 정영화/…」)에서 인도자를 읽는다. 없으면 빈 칸(지어내지 않는다)."""
        f = publish.leader_from_path
        self.assertEqual(f("2026/2026 0118 주일예배 정영화/2026 0118 주일예배 PPT.pptx"), "정영화")
        self.assertEqual(f("2025/2025 1228 주일예배 이경진/2025 1228 제곡교회예배.pptx"), "이경진")
        self.assertEqual(f("2025/20250108 수요예배.pptx"), "")
        self.assertEqual(f("2025/20250316 제곡교회예배.pptx"), "")

    def test_roles_and_filter_in_page(self):
        """수요·금요 인도·설교(services.json)가 페이지에 들어가고, 지난 예배에 인도자 거르기가 있다."""
        doc = publish.landing_html([{"date": "2026-01-18", "kind": "주일", "leader": ["정영화"], "songs": [], "src": "x"}])
        for w in ("정영선 목사", "이춘만 선교사", "김태헌 집사", 'id="flt"', "인도 정영화"[:2]):
            self.assertIn(w, doc)

    def test_song_leaders(self):
        """한 번이라도 부른 곡에 그 인도자 배지 — 콘티 기록에서 모은다. 제목은 띄어쓰기·문장부호 무시, 끝 번호(「… 1」)는 묶음."""
        items = [
            {"date": "2026-10-04", "kind": "주일", "leader": ["이경진"], "songs": ["주의 인자하심이", "괴로울 때 주님의 얼굴 보라"]},
            {"date": "2026-01-18", "kind": "주일", "leader": ["정영화"], "songs": ["주의 인자하심이 1"]},
            {"date": "2025-01-08", "kind": "수요", "leader": [], "songs": ["주의 인자하심이"]},   # 인도자 기록 없음 → 세지 않음
        ]
        got = publish.song_leaders(items)
        k = publish.song_key("주의 인자하심이 1")
        self.assertEqual(k, publish.song_key("주의인자하심이"))
        self.assertEqual(got[k], {"이경진": 1, "정영화": 1})
        self.assertEqual(got[publish.song_key("괴로울 때, 주님의 얼굴보라")], {"이경진": 1})

    def test_page_has_tabs(self):
        doc = publish.landing_html([])
        for w in ("새벽예배", "수요예배", "금요예배", "주일예배", 'id="svc"', "svcAt(", "prep.html?d='+up.date", "function svcBtns(", 'id="foot"', "admin.html\">관리자</a>", "/api/wadmin?info='+CH"):
            self.assertIn(w, doc)
        self.assertNotIn("@@", doc)


if __name__ == "__main__":
    unittest.main()


class Wadmin(unittest.TestCase):
    """맥미니 쪽 계정 DB 맞추기 문장 — 교회 정보는 처음만(DO NOTHING), 주일 인도는 섬김표를 따름, 관리자 이경진, 준비 열쇠."""
    def test_sync_statements(self):
        import wadmin
        st = wadmin.sync_statements({"2026-10-11": {"인도자": ["정상진"]}, "2026-10-18": {"인도자": []}},
                                    {"wed": {"인도": "정영선 목사", "설교": "이춘만 선교사"}}, "9999", church="zz")
        sql = [s for s, _ in st]; args = [a for _, a in st]
        self.assertTrue(any("wor_settings" in s and "DO NOTHING" in s for s in sql))
        self.assertIn(["zz", "wed", "정영선", "이춘만 선교사"], args)
        self.assertIn(["zz", "2026-10-11", "정상진"], args)
        self.assertFalse(any(a and a[1:2] == ["2026-10-18"] for a in args))     # 인도자 없는 주는 넣지 않음
        self.assertIn(["zz", "9999"], args)
        self.assertIn(["zz", "이경진", "", "admin"], args)
