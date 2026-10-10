// A concurrent smoke test of the real generated seats, not simulated shared users.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const directory = path.resolve(process.argv[2] || '.classroom-load');
const roster = JSON.parse(await fs.readFile(path.join(directory, 'roster.json')));
const compose = JSON.parse(await fs.readFile(path.join(directory, 'compose.json')));
const environment = compose.services['learner01-editor'].environment;
const origin = environment.EDITOR_ORIGIN, runtime = environment.RUNTIME_ORIGIN;
const original = await fs.readFile(new URL('../lessons/sqli/index.php', import.meta.url), 'utf8');
const times = [], users = [];
const checked = async (url, options = {}) => {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200, `Unexpected HTTP status for ${new URL(url).pathname}`);
  return response;
};
const started = performance.now();
try {
  await Promise.all(roster.map(async seat => {
    const response = await fetch(`${origin}/login`, { method: 'POST', redirect: 'manual', headers: { Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ code: seat.code }), signal: AbortSignal.timeout(15000) });
    assert.equal(response.status, 303, 'Learner login failed');
    const cookie = response.headers.get('set-cookie').split(';')[0];
    const user = { seat, headers: { Cookie: cookie, Origin: origin, 'Content-Type': 'application/json' } };
    users.push(user);
    const catalog = await (await checked(`${origin}/api/lessons`, { headers: user.headers })).json();
    assert.equal(catalog.length, 6);
    for (let run = 0; run < 10; run++) {
      const stamp = `${seat.name}-run${run}`;
      const code = `<?php $db = new PDO('sqlite:/tmp/load.sqlite'); $db->exec('CREATE TABLE IF NOT EXISTS stamp (value TEXT)'); $db->exec('DELETE FROM stamp'); $db->exec("INSERT INTO stamp VALUES ('${stamp}')"); echo $db->query('SELECT value FROM stamp')->fetchColumn(); ?>`;
      const start = performance.now();
      await checked(`${origin}/api/sqli/code`, { method: 'POST', headers: user.headers, body: JSON.stringify({ code }) });
      const result = await checked(`${runtime}/sqli/`, { headers: user.headers });
      assert.equal(await result.text(), stamp, 'Learner database or code mixed with another seat');
      const saved = await (await checked(`${origin}/api/sqli/code`, { headers: user.headers })).json();
      assert.equal(saved.code, code, 'Learner code was overwritten by another seat');
      times.push(performance.now() - start);
    }
  }));
  times.sort((a, b) => a - b);
  console.log(JSON.stringify({ seats: roster.length, successfulRuns: times.length, elapsedSeconds: Number(((performance.now() - started) / 1000).toFixed(2)), saveRunAndVerifyP95ms: Math.round(times[Math.floor(times.length * .95)]) }));
} finally {
  await Promise.all(users.map(user => fetch(`${origin}/api/sqli/code`, { method: 'POST', headers: user.headers, body: JSON.stringify({ code: original }), signal: AbortSignal.timeout(10000) })));
}
