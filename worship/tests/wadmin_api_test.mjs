// api/wadmin.js 를 실제 예배 DB 에 대고 돌려 본다 — 교회 이름 'zz-test' 만 쓰고 끝나면 지운다.
//   node worship/tests/wadmin_api_test.mjs
import fs from 'node:fs'; import os from 'node:os'; import assert from 'node:assert/strict';
for (const l of fs.readFileSync(os.homedir() + '/dev/daily-briefing/.env', 'utf8').split('\n')) {
  const m = l.match(/^([A-Z_]+)=(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim().replace(/^["']|["']$/g, '');
}
const api = await import(os.homedir() + '/dev/daily-briefing/report-site/api/wadmin.js');
const H = api.default, C = 'zz-test';
let cookie = '';
async function call(method, { query = {}, body = null, ip = '10.9.9.' + Math.floor(Math.random() * 200) } = {}) {
  const out = { code: 200, headers: {}, body: null };
  const res = { setHeader: (k, v) => { out.headers[k.toLowerCase()] = v; }, status(c) { out.code = c; return this; }, json(j) { out.body = j; return this; } };
  await H({ method, query, body, headers: { cookie, host: 'example.test', 'x-forwarded-for': ip } }, res);
  const sc = out.headers['set-cookie']; if (sc) cookie = sc.split(';')[0].endsWith('=') ? '' : sc.split(';')[0];
  return out;
}
const clean = () => api.batch([['DELETE FROM wor_users WHERE church=?', [C]], ['DELETE FROM wor_settings WHERE church=?', [C]], ['DELETE FROM wor_assign WHERE church=?', [C]]]);
let n = 0; let r0; const ok = (c, m) => { assert.ok(c, m); n++; };
try {
  await call('GET', { query: { info: 'jegok' } });      // 표 만들기
  await clean();
  await api.batch([['INSERT INTO wor_users(church,name,title,role,hash,ver,active,at) VALUES(?,?,?,?,NULL,0,1,?)', [C, '관리자', '', 'admin', 'x']],
                   ['INSERT INTO wor_settings(church,k,v) VALUES(?,?,?)', [C, '_prep_key', '4321']],
                   ['INSERT INTO wor_settings(church,k,v) VALUES(?,?,?)', [C, 'name', '시험교회']]]);
  // 비밀번호를 아직 안 정한 계정으로 로그인하면 안내만 하고 틀린 횟수로 세지 않는다
  for (let i = 0; i < 6; i++) r0 = await call('POST', { ip: '10.7.7.7', body: { action: 'login', church: C, name: '관리자', pw: 'whatever' } });
  ok(r0.code === 409 && r0.body.error.includes('비밀번호 정하기'), '비밀번호 정하기 전 로그인은 안내(409), 6번 해도 안 막힘');
  // 처음 정하기
  let r = await call('POST', { body: { action: 'setup', church: C, name: '관리자', key: 'nope', pw: 'abcdef1' } });
  ok(r.code === 403, '틀린 링크 열쇠는 막힘');
  r = await call('POST', { body: { action: 'setup', church: C, name: '관리자', key: api.setupKey(C, '관리자', 0), pw: '123' } });
  ok(r.code === 400, '짧은 비밀번호 거절');
  r = await call('POST', { body: { action: 'setup', church: C, name: '관리자', key: api.setupKey(C, '관리자', 0), pw: 'admin-pass-1' } });
  ok(r.code === 200 && cookie.startsWith('wsess='), '정하면 로그인 쿠키');
  r = await call('GET', { query: { me: 1 } });
  ok(r.body.auth && r.body.role === 'admin', '쿠키로 관리자 확인');
  // 공개 정보에 열쇠가 나가지 않는다
  r = await call('GET', { query: { info: C } });
  ok(r.body.settings.name === '시험교회' && !JSON.stringify(r.body).includes('4321'), '공개 info 에 준비 열쇠 없음');
  // 관리자: 인도자 추가 → 링크
  r = await call('POST', { body: { action: 'adduser', name: '김인도', title: '집사', role: 'leader' } });
  ok(r.code === 200 && r.body.link.includes('setup=zz-test.'), '인도자 추가하면 처음 정하기 링크');
  r = await call('POST', { body: { action: 'adduser', name: '김인도' } });
  ok(r.code === 409, '같은 이름은 거절');
  // 관리자는 아무 날짜나 준비 열쇠
  r = await call('POST', { body: { action: 'prep', church: C, date: '2026-10-07' } });
  ok(r.code === 200 && r.body.key === '4321', '관리자는 수요일 준비도 열림');
  // 인도자: 비밀번호 정하고, 맡지 않은 날은 막힘 → 맡기면 열림
  const adminCookie = cookie; cookie = '';
  r = await call('POST', { body: { action: 'setup', church: C, name: '김인도', key: api.setupKey(C, '김인도', 0), pw: 'leader-pass-1' } });
  ok(r.code === 200 && r.body.role === 'leader', '인도자 비밀번호 정함');
  r = await call('POST', { body: { action: 'prep', church: C, date: '2026-10-09' } });
  ok(r.code === 403, '맡지 않은 금요일은 막힘');
  r = await call('POST', { body: { action: 'adduser', name: '또' } });
  ok(r.code === 403, '인도자는 관리자 일 못 함');
  cookie = adminCookie;
  r = await call('POST', { body: { action: 'assign', svc: 'fri', date: '', leader: '김인도', preacher: '정설교' } });
  ok(r.code === 200, '평소 금요 인도 지정');
  cookie = '';
  r = await call('POST', { body: { action: 'prep', church: C, date: '2026-10-09', name: '김인도', pw: 'leader-pass-1' } });
  ok(r.code === 200 && r.body.key === '4321', '이름+비밀번호로 맡은 금요일 준비 열림');
  r = await call('POST', { body: { action: 'prep', church: C, date: '2026-10-11' } });
  ok(r.code === 403, '맡지 않은 주일은 여전히 막힘');
  // 틀린 비밀번호 여러 번 → 막힘
  const ip = '10.8.8.8';
  for (let i = 0; i < 5; i++) await call('POST', { ip, body: { action: 'login', church: C, name: '김인도', pw: 'wrong-' + i } });
  r = await call('POST', { ip, body: { action: 'login', church: C, name: '김인도', pw: 'leader-pass-1' } });
  ok(r.code === 429, '5번 틀리면 15분 막힘');
  // 잠그면 쿠키도 무효
  cookie = adminCookie;
  r = await call('POST', { body: { action: 'active', name: '김인도', on: false } });
  ok(r.code === 200, '인도자 잠금');
  r = await call('POST', { body: { action: 'login', church: C, name: '김인도', pw: 'leader-pass-1' } });
  ok(r.code === 403, '잠긴 계정은 로그인 안 됨');
  console.log(`OK ${n}개`);
} finally {
  await clean(); await api.batch([['DELETE FROM wor_fail WHERE ip LIKE ?', ['10.%']]]);
}
