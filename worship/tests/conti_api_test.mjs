// api/conti.js 임시저장(draft) — rev 를 올리지 않아 맥미니가 다시 만들지 않는다 (2026-10-07)
//   node worship/tests/conti_api_test.mjs   (날짜 1999-01-03 만 쓰고 지운다. 생성 시험 줄은 built_rev 를 크게 잡아 맥미니가 집어 가지 않게)
import fs from 'node:fs'; import os from 'node:os'; import crypto from 'node:crypto'; import assert from 'node:assert/strict';
for (const l of fs.readFileSync(os.homedir() + '/dev/daily-briefing/.env', 'utf8').split('\n')) {
  const m = l.match(/^([A-Z_]+)=(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim().replace(/^["']|["']$/g, '');
}
const H = (await import(os.homedir() + '/dev/daily-briefing/report-site/api/conti.js')).default;
const W = await import(os.homedir() + '/dev/daily-briefing/report-site/api/wadmin.js');
const key = crypto.createHmac('sha256', process.env.JUBO_SECRET).update('conti').digest('hex').slice(0, 32), D = '1999-01-03';
async function post(body) { const out = { code: 200 }; await H({ method: 'POST', query: {}, body, headers: {} },
  { setHeader() {}, status(c) { out.code = c; return this; }, json(j) { out.body = j; return this; } }); return out; }
const row = async () => (await W.batch([['SELECT rev,built_rev,main FROM conti WHERE date=?', [D]]]))[0][0];
let n = 0; const ok = (c, m) => { assert.ok(c, m); n++; };
try {
  await W.batch([['DELETE FROM conti WHERE date=?', [D]]]);
  let r = await post({ date: D, key, intro: [], main: [{ title: '시험곡' }], apply: [], pool: [], draft: true });
  ok(r.code === 200 && r.body.draft, '임시저장 됨');
  let x = await row(); ok(Number(x.rev) === 0 && Number(x.built_rev) === 0 && x.main.includes('시험곡'), '처음 임시저장: rev 0 — 만들 일 없음');
  await post({ date: D, key, intro: [], main: [{ title: '시험곡2' }], apply: [], pool: [], draft: true });
  x = await row(); ok(Number(x.rev) === 0 && x.main.includes('시험곡2'), '다시 임시저장해도 rev 그대로, 곡은 바뀜');
  await W.batch([['UPDATE conti SET built_rev=100 WHERE date=?', [D]]]);
  r = await post({ date: D, key, intro: [], main: [{ title: '시험곡3' }], apply: [], pool: [] });
  ok(r.code === 200 && !r.body.draft && r.body.rev === 1, '생성: rev 하나 올림');
  console.log(`OK ${n}개`);
} finally { await W.batch([['DELETE FROM conti WHERE date=?', [D]]]); }
