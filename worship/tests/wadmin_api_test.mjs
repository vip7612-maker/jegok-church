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
const clean = () => api.batch([['DELETE FROM wor_order WHERE church=?', [C]], ['DELETE FROM wor_tpl WHERE church=?', [C]], ['DELETE FROM wor_reco WHERE church=?', [C]], ['DELETE FROM wor_users WHERE church=?', [C]], ['DELETE FROM wor_settings WHERE church=?', [C]], ['DELETE FROM wor_assign WHERE church=?', [C]]]);
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
  // 예배순서: 맡은 날은 기본 순서가 오고, 저장·확정이 된다 · 맡지 않은 날은 막힘
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  ok(r.code === 200 && !r.body.saved && r.body.items.some(x => x.t === '설교'), '금요일 기본 순서(저장 전)');
  r = await call('POST', { body: { action: 'order', church: C, date: '2026-10-09', items: [{ t: '찬양' }, { t: '기도' }, { t: '' }], confirm: true } });
  ok(r.code === 200 && r.body.items.length === 2 && r.body.confirmed, '순서 저장·확정(빈 칸은 버림)');
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  ok(r.body.saved && r.body.items[1].t === '기도' && r.body.by === '김인도', '저장한 순서를 다시 읽음');
  r = await call('GET', { query: { order: C, date: '2026-10-11' } });
  ok(r.code === 403, '맡지 않은 주일 순서는 못 봄');
  r = await call('POST', { body: { action: 'prep', church: C, date: '2026-10-09' } });
  ok(r.body.conti_key && r.body.conti_key.length === 32, '준비 열쇠와 함께 콘티 열쇠');
  const saveCookie = cookie; cookie = '';
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  ok(r.code === 401, '로그인 없으면 순서 못 봄');
  // 주보 올리기(2026-10-07): 브라우저가 Blob 에 바로 올릴 열쇠 — 로그인·맡은 날·자리·확장자 확인 / 서버엔 주소만
  const tok = (date, pathname) => call('POST', { body: { type: 'blob.generate-client-token', payload: { pathname, multipart: false, clientPayload: JSON.stringify({ church: C, date }) } } });
  r = await tok('2026-10-09', `jubo/${C}/2026-10-09/1.hwp`);
  ok(r.code === 403 && r.body.error.includes('비밀번호'), '로그인 없으면 올릴 열쇠 없음');
  cookie = saveCookie;
  r = await tok('2026-10-09', `jubo/${C}/2026-10-09/1.hwp`);
  ok(r.code === 200 && typeof r.body.clientToken === 'string' && r.body.clientToken.length > 20, '맡은 날은 올릴 열쇠');
  r = await tok('2026-10-11', `jubo/${C}/2026-10-11/1.hwp`);
  ok(r.code === 403, '맡지 않은 날은 열쇠 없음');
  r = await tok('2026-10-09', `jubo/other/2026-10-09/1.hwp`);
  ok(r.code === 403, '다른 자리에는 열쇠 없음');
  r = await tok('2026-10-09', `jubo/${C}/2026-10-09/1.exe`);
  ok(r.code === 403, '주보가 아닌 파일은 열쇠 없음');
  r = await call('POST', { body: { action: 'jubo', church: C, date: '2026-10-09', name: '주보.hwp', url: 'https://evil.example.com/jubo/zz-test/2026-10-09/1.hwp' } });
  ok(r.code === 400, '다른 곳 주소는 거절');
  const good = `https://abc.public.blob.vercel-storage.com/jubo/${C}/2026-10-09/1-x.hwp`;
  r = await call('POST', { body: { action: 'jubo', church: C, date: '2026-10-09', name: '10월9일 주보.hwp', url: good } });
  ok(r.code === 200 && r.body.jubo.url === good && r.body.jubo.name === '10월9일 주보.hwp', '올린 주보 주소 기록');
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  ok(r.body.jubo && r.body.jubo.url === good, '다시 열어도 주보 첨부가 보임');
  // 순서에 맡은 분·설교 제목·성경 본문 (2026-10-07)
  r = await call('POST', { body: { action: 'order', church: C, date: '2026-10-09', items: [
    { t: '대표기도', who: ' 정상진 장로 ' }, { t: '성경봉독', who: '김인도 집사', ref: '마가복음 3:31-35' }, { t: '설교', who: '정영선 목사', title: '하나님의 가족', x: 'drop' }] } });
  ok(r.code === 200 && r.body.items[0].who === '정상진 장로' && r.body.items[1].ref === '마가복음 3:31-35' && r.body.items[2].title === '하나님의 가족' && !('x' in r.body.items[2]), '맡은 분·본문·제목 저장(모르는 칸은 버림)');
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  ok(r.body.items[2].who === '정영선 목사', '다시 읽어도 맡은 분');
  // 예배순서 ↔ PPT 동기화(2026-10-07): 임시 저장은 rev 그대로, 확정하면 rev 하나 올림 · 주보를 다시 올리면 읽을 차례로
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  const rev0 = r.body.rev;
  ok(typeof rev0 === 'number' && 'built_rev' in r.body && r.body.src === 'user', '순서에 rev·built_rev·src');
  r = await call('POST', { body: { action: 'order', church: C, date: '2026-10-09', items: [{ t: '찬양' }] } });
  ok(r.body.rev === rev0, '임시 저장은 rev 그대로');
  r = await call('POST', { body: { action: 'order', church: C, date: '2026-10-09', items: [{ t: '찬양' }], confirm: true } });
  ok(r.body.rev === rev0 + 1 && r.body.built_rev < r.body.rev, '확정하면 rev 하나 올림 → 맥미니가 PPT 를 다시 만들 차례');
  await api.batch([['UPDATE wor_order SET jubo_done=? WHERE church=? AND date=?', ['2026-10-07T00:00:00Z', C, '2026-10-09']]]);
  // 첨부가 있으면 새로 올리지 못한다 — 지운 뒤에만(2026-10-07 교장님)
  r = await call('POST', { body: { action: 'jubo', church: C, date: '2026-10-09', name: '새 주보.pdf', url: `https://abc.public.blob.vercel-storage.com/jubo/${C}/2026-10-09/2.pdf` } });
  ok(r.code === 409 && r.body.error.includes('삭제하고 다시 첨부'), '첨부가 있으면 다시 올리기 막힘');
  r = await tok('2026-10-09', `jubo/${C}/2026-10-09/3.pdf`);
  ok(r.code === 403 && r.body.error.includes('삭제하고 다시 첨부'), '첨부가 있으면 올릴 열쇠도 없음');
  r = await call('POST', { body: { action: 'jubo', church: C, date: '2026-10-09', del: true } });
  ok(r.code === 200 && r.body.jubo === null, '첨부 지우기');
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  ok(r.body.jubo === null && r.body.items.length > 0, '지워도 순서는 그대로');
  r = await call('POST', { body: { action: 'jubo', church: C, date: '2026-10-09', name: '새 주보.pdf', url: `https://abc.public.blob.vercel-storage.com/jubo/${C}/2026-10-09/2.pdf` } });
  ok(r.code === 200, '지운 뒤에는 새로 올림');
  r = await call('GET', { query: { order: C, date: '2026-10-09' } });
  ok(r.body.jubo_done === '', '새로 올리면 맥미니가 읽을 차례');
  ok(JSON.stringify(api.defaultOrder('2026-10-11').map(x => x.t)) === JSON.stringify(['성경암송', '찬양과 경배', '사도신경', '찬양과 경배', '대표기도', '교회소식', '봉헌', '성경봉독', '특송', '설교', '찬양과 결단', '축도']), '주일 기본 순서 = 템플릿 PPT 순서');
  // 교회 템플릿: 저장·목록·불러오기·지우기 — 날짜마다 바뀌는 제목·본문은 저장하지 않는다
  r = await call('POST', { body: { action: 'tpl_save', church: C, name: '금요예배', items: [{ t: '찬양' }, { t: '설교', who: '정영선 목사', title: '이번 주 제목', ref: '요 3:16' }] } });
  ok(r.code === 200, '템플릿 저장');
  r = await call('GET', { query: { tpl: C } });
  ok(r.code === 200 && r.body.list.length === 1 && r.body.list[0].name === '금요예배' && r.body.list[0].items[1].who === '정영선 목사' && !r.body.list[0].items[1].title && !r.body.list[0].items[1].ref, '템플릿 목록(제목·본문은 빼고)');
  // 칸 기록(최근 순서)·말씀에 맞는 곡
  await call('POST', { body: { action: 'order', church: C, date: '2026-10-09', items: [{ t: '설교', who: '정영선 목사', title: '제목' }] } });
  r = await call('GET', { query: { recent: C } });
  ok(r.code === 200 && r.body.rows.some(x => x.items.some(i => i.who === '정영선 목사')), '최근 순서에서 맡은 분 기록');
  r = await call('GET', { query: { reco: C, date: '2026-10-09' } });
  ok(r.code === 200 && r.body.reco === null, '추천 없으면 null');
  await api.batch([['INSERT INTO wor_reco(church,date,src,data,updated) VALUES(?,?,?,?,?)', [C, '2026-10-09', '요3:16|', JSON.stringify({ guide: '한 줄', ccm: [{ title: '곡', tempo: '느린곡' }] }), 'now']]]);
  r = await call('GET', { query: { reco: C, date: '2026-10-09' } });
  ok(r.body.reco.guide === '한 줄' && r.body.reco.ccm[0].tempo === '느린곡', '추천·예배 방향 읽기');
  const sc2 = cookie; cookie = '';
  r = await call('GET', { query: { reco: C, date: '2026-10-09' } }); ok(r.code === 401, '로그인 없으면 추천 못 봄'); cookie = sc2;
  r = await call('POST', { body: { action: 'tpl_save', church: 'jegok', name: '남의교회', items: [{ t: '찬양' }] } });
  ok(r.code === 400, '다른 교회 템플릿은 저장 못 함');
  r = await call('POST', { body: { action: 'tpl_save', church: C, name: '', items: [{ t: '찬양' }] } });
  ok(r.code === 400, '이름 없는 템플릿 거절');
  r = await call('POST', { body: { action: 'tpl_del', church: C, name: '금요예배' } });
  ok(r.code === 200 && (await call('GET', { query: { tpl: C } })).body.list.length === 0, '템플릿 지우기');
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
