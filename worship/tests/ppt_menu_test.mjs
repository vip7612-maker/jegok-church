// PPT 목차 ＋ 메뉴 추가(2026-10-08): 메뉴(type menu) 저장 · 그 안의 장(sect m:<id>) · 메뉴를 빼면 안의 장도. 날짜 1999-01-10 만 쓰고 지운다.
//   node worship/tests/ppt_menu_test.mjs
import fs from 'node:fs'; import os from 'node:os'; import crypto from 'node:crypto'; import assert from 'node:assert/strict';
for (const l of fs.readFileSync(os.homedir() + '/dev/daily-briefing/.env', 'utf8').split('\n')) {
  const m = l.match(/^([A-Z_]+)=(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim().replace(/^["']|["']$/g, '');
}
const P = (await import(os.homedir() + '/dev/daily-briefing/report-site/api/worship.js')).default;
const D = '1999-01-10', key = crypto.createHmac('sha256', process.env.JUBO_SECRET).update('news:' + D).digest('hex').slice(0, 32);
async function call(method, { query = {}, body = null } = {}) {
  const out = { code: 200, headers: {} };
  await P({ method, query, body, headers: {} }, { setHeader: (k, v) => { out.headers[k] = v; }, status(c) { out.code = c; return this; }, json(j) { out.body = j; return this; } });
  return out;
}
const list = async () => (await call('GET', { query: { pages: D } })).body;
let n = 0; const ok = (c, m) => { assert.ok(c, m); n++; };
for (const p of await list()) await call('POST', { body: { action: 'pagedel', date: D, key, id: p.id } });
let r = await call('POST', { body: { action: 'page', date: D, key: 'wrong', type: 'menu', data: { title: '간증' } } });
ok(r.code === 403, '열쇠 없으면 막힘');
r = await call('POST', { body: { action: 'page', date: D, key, type: 'menu', data: { title: '' } } });
ok(r.code === 400, '빈 제목은 막힘');
r = await call('POST', { body: { action: 'page', date: D, key, type: 'menu', sect: 'news', data: { title: '간증', after: '설교', x: 1 } } });
ok(r.code === 200, '메뉴 넣기');
let L = await list(); const m = L.find(p => p.type === 'menu');
ok(m && m.sect === 'menu' && m.data.title === '간증' && m.data.after === '설교' && !('x' in m.data), '메뉴는 sect menu, 제목·자리만 저장');
r = await call('POST', { body: { action: 'page', date: D, key, sect: 'm:' + m.id, type: 'text', data: { title: '간증 1', body: '내용' } } });
ok(r.code === 200, '메뉴 안에 장 넣기');
L = await list(); ok(L.some(p => p.sect === 'm:' + m.id && p.type === 'text'), '메뉴 안의 장 = sect m:<id>');
r = await call('POST', { body: { action: 'page', date: D, key, id: m.id, type: 'menu', data: { title: '간증과 나눔', after: '' } } });
L = await list(); ok(L.find(p => p.id === m.id).data.title === '간증과 나눔', '메뉴 이름 고치기');
r = await call('POST', { body: { action: 'page', date: D, key, sect: 'news', type: 'text', data: { title: '소식' } } });
await call('POST', { body: { action: 'pagedel', date: D, key, id: m.id } });
L = await list(); ok(!L.some(p => p.id === m.id || p.sect === 'm:' + m.id) && L.some(p => p.sect === 'news'), '메뉴를 빼면 안의 장도 빠지고 다른 장은 그대로');
for (const p of L) await call('POST', { body: { action: 'pagedel', date: D, key, id: p.id } });
ok((await list()).length === 0, '시험 자료 지움');
console.log('OK ' + n + '개');
