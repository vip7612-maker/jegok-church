// PPT ↔ 예배순서 이름 맞추기(2026-10-07): 예배순서 → PPT 글자(ppt_news) · PPT 에서 고침 → 예배순서. 교회 zz-test, 날짜 1999-01-03 만 쓰고 지운다.
//   node worship/tests/ppt_sync_test.mjs
import fs from 'node:fs'; import os from 'node:os'; import crypto from 'node:crypto'; import assert from 'node:assert/strict';
for (const l of fs.readFileSync(os.homedir() + '/dev/daily-briefing/.env', 'utf8').split('\n')) {
  const m = l.match(/^([A-Z_]+)=(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim().replace(/^["']|["']$/g, '');
}
const W = await import(os.homedir() + '/dev/daily-briefing/report-site/api/wadmin.js');
const P = (await import(os.homedir() + '/dev/daily-briefing/report-site/api/worship.js')).default;
const C = 'zz-test', D = '1999-01-03';
let cookie = '';
async function call(H, method, { query = {}, body = null } = {}) {
  const out = { code: 200, headers: {} };
  await H({ method, query, body, headers: { cookie, host: 'example.test', 'x-forwarded-for': '10.6.6.' + Math.floor(Math.random() * 200) } },
    { setHeader: (k, v) => { out.headers[k.toLowerCase()] = v; }, status(c) { out.code = c; return this; }, json(j) { out.body = j; return this; } });
  const sc = out.headers['set-cookie']; if (sc) cookie = sc.split(';')[0];
  return out;
}
const clean = () => W.batch([['DELETE FROM wor_order WHERE church=?', [C]], ['DELETE FROM wor_users WHERE church=?', [C]], ['DELETE FROM wor_svc WHERE church=?', [C]], ['DELETE FROM ppt_news WHERE date=?', [D]]]);
let n = 0; const ok = (c, m) => { assert.ok(c, m); n++; };
try {
  await call(W.default, 'GET', { query: { info: 'jegok' } });
  await W.batch([['CREATE TABLE IF NOT EXISTS ppt_news (date TEXT, i INTEGER, orig TEXT, texts TEXT, at TEXT, PRIMARY KEY (date, i))', []]]);
  await clean();
  await W.batch([['INSERT INTO wor_users(church,name,title,role,hash,ver,active,at) VALUES(?,?,?,?,NULL,0,1,?)', [C, '관리자', '', 'admin', 'x']]]);
  await call(W.default, 'POST', { body: { action: 'setup', church: C, name: '관리자', key: W.setupKey(C, '관리자', 0), pw: 'admin-pass-1' } });
  // PPT 를 만든 뒤처럼: 예배순서 + 짝(smap) — 4번 장 = 대표기도(가운데 글자 2번), 6번 장 = 성경봉독(본문 2번·맡은 분 3번)
  const t4 = ['Prayer', '대표기도', '정상진 장로', '함께 기도해요'], t6 = ['Scripture Reading', '성경 봉독', '시편 23편', '박서준 학생'];
  const smap = [{ i: 4, key: '대표기도', nth: 0, f: { who: 2 }, orig: t4.join('\n'), texts: t4 }, { i: 6, key: '성경봉독', nth: 0, f: { ref: 2, who: 3 }, orig: t6.join('\n'), texts: t6 }];
  const items = [{ t: '찬양' }, { t: '기도', who: '정상진 장로' }, { t: '성경봉독', who: '박서준 학생', ref: '시편 23편' }];
  await W.batch([['INSERT INTO wor_order(church,date,items,confirmed,updated,smap) VALUES(?,?,?,0,?,?)', [C, D, JSON.stringify(items), 'x', JSON.stringify(smap)]]]);
  // 1) 예배순서에서 기도 맡은 분을 고침 → PPT 4번 장 글자가 바로
  let r = await call(W.default, 'POST', { body: { action: 'order', church: C, date: D, items: [{ t: '찬양' }, { t: '기도', who: '김은정 권사' }, { t: '성경봉독', who: '박서준 학생', ref: '시편 23편' }] } });
  ok(r.code === 200 && r.body.ppt === 1 && !r.body.ref_stale, '예배순서 → PPT 한 장 바꿈');
  let [nw] = (await W.batch([['SELECT texts, orig FROM ppt_news WHERE date=? AND i=4', [D]]]))[0];
  ok(JSON.parse(nw.texts)[2] === '김은정 권사' && nw.orig === t4.join('\n'), 'PPT 4번 장 가운데 글자 = 김은정 권사');
  // 2) 본문을 바꾸면 PPT 는 그대로, 「다시 만들기」 알림
  r = await call(W.default, 'POST', { body: { action: 'order', church: C, date: D, items: [{ t: '찬양' }, { t: '기도', who: '김은정 권사' }, { t: '성경봉독', who: '박서준 학생', ref: '시편 24편' }] } });
  ok(r.body.ref_stale === true, '본문을 바꾸면 다시 만들기 알림');
  // 3) PPT 에서 봉독자 이름을 고침 → 예배순서 칸도
  const nk = crypto.createHmac('sha256', process.env.JUBO_SECRET).update('news:' + D).digest('hex').slice(0, 32);
  r = await call(P, 'POST', { body: { action: 'news', date: D, key: nk, i: 6, orig: t6.join('\n'), texts: ['Scripture Reading', '성경 봉독', '시편 24편', '이유은 학생'] } });
  ok(r.code === 200 && r.body.order === true, 'PPT → 예배순서');
  const [row] = (await W.batch([['SELECT items, by FROM wor_order WHERE church=? AND date=?', [C, D]]]))[0];
  const it = JSON.parse(row.items).find(x => x.t === '성경봉독');
  ok(it.who === '이유은 학생' && it.ref === '시편 24편' && row.by === 'PPT', '예배순서 봉독자 = 이유은 학생(고친 사람 PPT)');
  // 4) 다른 판(orig 가 다름)의 PPT 글자는 예배순서를 건드리지 않는다
  r = await call(P, 'POST', { body: { action: 'news', date: D, key: nk, i: 6, orig: 'old', texts: ['x', 'x', 'x', '엉뚱한 이름'] } });
  ok(r.body.order === false, '예전 판 PPT 글자는 무시');
  console.log(`OK ${n}개`);
} finally { await clean(); }
