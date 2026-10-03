// 그림 창고(Vercel Blob)에 한꺼번에 올리기 — 입력: 한 줄에 {"path":"assets/ab/<지문>.jpg","file":"/로컬/경로","type":"image/jpeg"}
// 출력: 한 줄에 {"path":…,"url":…} 또는 {"path":…,"error":…}. 토큰은 환경변수 BLOB_READ_WRITE_TOKEN.
import { put } from "@vercel/blob";
import { readFileSync } from "node:fs";
import readline from "node:readline";

const rl = readline.createInterface({ input: process.stdin });
const jobs = [];
for await (const line of rl) if (line.trim()) jobs.push(JSON.parse(line));
const N = 8; let i = 0;
async function worker() {
  while (i < jobs.length) {
    const j = jobs[i++];
    try {
      const r = await put(j.path, readFileSync(j.file), { access: "public", addRandomSuffix: false, allowOverwrite: true,
        contentType: j.type, cacheControlMaxAge: 31536000 });
      console.log(JSON.stringify({ path: j.path, url: r.url }));
    } catch (e) { console.log(JSON.stringify({ path: j.path, error: String(e.message || e) })); }
  }
}
await Promise.all(Array.from({ length: N }, worker));
