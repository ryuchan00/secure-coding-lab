const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const config = process.env.CLASSROOM_CONFIG;
test.skip(!config, 'Classroom tests require the generated two-seat configuration');

test('two concurrent learners have isolated code, SQLite, progress and sessions', async ({ browser }) => {
  const directory = path.resolve(config);
  const roster = JSON.parse(fs.readFileSync(path.join(directory, 'roster.json')));
  const compose = JSON.parse(fs.readFileSync(path.join(directory, 'compose.json')));
  const env = compose.services['learner01-editor'].environment;
  const origin = env.EDITOR_ORIGIN, runtime = env.RUNTIME_ORIGIN;
  const contexts = await Promise.all([browser.newContext(), browser.newContext()]);
  const pages = await Promise.all(contexts.map(c => c.newPage()));
  const save = (i, lesson, code) => contexts[i].request.post(`${origin}/api/${lesson}/code`, { headers: { Origin: origin }, data: { code } });
  try {
    await Promise.all(pages.map(async (p, i) => {
      await p.goto(origin);
      await p.locator('[name=code]').fill(roster[i].code);
      await p.getByRole('button', { name: '研修を始める' }).click();
      await expect(p.locator('#workspace-name')).toHaveText(`受講者 0${i + 1}`);
    }));
    // All six lessons use the shared preview origin and retain their own form paths.
    const titles = { sqli: '会員ログイン', xss: 'あいさつメーカー', csrf: '練習用の口座', access: '明細の閲覧', 'stored-xss': 'コメント掲示板', traversal: '公開ファイル' };
    for (const [lesson, title] of Object.entries(titles)) {
      await pages[0].locator(`nav button[data-id="${lesson}"]`).click();
      await expect(pages[0].frameLocator('#preview').locator('h1')).toHaveText(title);
    }
    await pages[0].locator('nav button[data-id=sqli]').click();
    // Each runtime writes the same DB path, but the databases belong to different containers.
    const code = i => `<?php $db = new PDO('sqlite:/tmp/isolation.sqlite'); $db->exec('DROP TABLE IF EXISTS example'); $db->exec('CREATE TABLE example (value TEXT)'); $db->exec("INSERT INTO example VALUES ('learner${i}')"); echo $db->query('SELECT value FROM example')->fetchColumn(); ?>`;
    await Promise.all([save(0, 'sqli', code(1)), save(1, 'sqli', code(2))]);
    await Promise.all(pages.map(async (p, i) => {
      await p.getByRole('button', { name: '再読込' }).click();
      await expect(p.frameLocator('#preview').locator('body')).toHaveText(`learner${i + 1}`);
      const response = await contexts[i].request.get(`${origin}/api/sqli/code`);
      expect((await response.json()).code).toBe(code(i + 1));
    }));
    await save(0, 'sqli', "<?php $db = new PDO('sqlite:/tmp/isolation.sqlite'); echo $db->query('SELECT value FROM example')->fetchColumn(); ?>");
    const aDb = await contexts[0].request.get(`${runtime}/sqli/`);
    expect(await aDb.text()).toBe('learner1');
    await contexts[0].request.post(`${origin}/api/progress`, { headers: { Origin: origin }, data: { completed: ['sqli'] } });
    const bProgress = await contexts[1].request.get(`${origin}/api/progress`);
    expect((await bProgress.json()).completed).toEqual([]);
    await Promise.all(contexts.map(c => c.request.get(`${runtime}/csrf/`)));
    await contexts[0].request.post(`${runtime}/csrf/`, { form: { amount: '1000' } });
    const aBalance = await contexts[0].request.get(`${runtime}/csrf/`);
    const bBalance = await contexts[1].request.get(`${runtime}/csrf/`);
    expect(await aBalance.text()).toContain('id="balance">9000');
    expect(await bBalance.text()).toContain('id="balance">10000');
    await save(0, 'csrf', fs.readFileSync(path.join(__dirname, '../lessons/csrf/solution.php'), 'utf8'));
    expect((await contexts[0].request.post(`${runtime}/csrf/`, { form: { amount: '1000' } })).status()).toBe(403);
    expect((await contexts[1].request.post(`${runtime}/csrf/`, { form: { amount: '1000' } })).status()).toBe(200);
    await pages[0].locator('nav button[data-id=csrf]').click();
    await pages[0].getByRole('button', { name: '攻撃ページ', exact: true }).click();
    await pages[0].frameLocator('#preview').getByRole('button').click();
    await expect(pages[0].frameLocator('#preview').frameLocator('iframe').locator('body')).toContainText('CSRFトークンが一致しません');
    await pages[1].locator('nav button[data-id=csrf]').click();
    await pages[1].getByRole('button', { name: '攻撃ページ', exact: true }).click();
    await pages[1].frameLocator('#preview').getByRole('button').click();
    await expect(pages[1].frameLocator('#preview').frameLocator('iframe').locator('#balance')).toHaveText('8000');
    await save(0, 'sqli', "<?php echo isset($_COOKIE['lab_workspace']) ? 'leaked' : 'hidden'; echo gethostbyname('learner02-runtime') === 'learner02-runtime' ? ' isolated' : ' peer visible'; ?>");
    expect(await (await contexts[0].request.get(`${runtime}/sqli/`)).text()).toBe('hidden isolated');
    const outsider = await browser.newContext();
    try {
      expect((await outsider.request.get(`${origin}/api/sqli/code`)).status()).toBe(401);
      expect((await outsider.request.get(`${runtime}/sqli/`)).status()).toBe(401);
      expect((await outsider.request.get(`${runtime}/sqli/`, { headers: { Cookie: 'lab_workspace=forged' } })).status()).toBe(401);
      expect((await contexts[0].request.post(`${origin}/api/sqli/code`, { headers: { Origin: runtime }, data: { code: '<?php echo 1;' } })).status()).toBe(403);
    } finally { await outsider.close(); }
    await contexts[0].request.post(`${origin}/logout`, { headers: { Origin: origin } });
    expect((await contexts[0].request.get(`${origin}/api/sqli/code`)).status()).toBe(401);
    expect((await contexts[1].request.get(`${origin}/api/sqli/code`)).status()).toBe(200);
  } finally {
    // Restore test seats through each learner's authenticated editor.
    for (let i = 0; i < 2; i++) {
      // Re-login through POST even if an earlier assertion or logout changed navigation.
      await contexts[i].request.post(`${origin}/login`, { headers: { Origin: origin }, form: { code: roster[i].code } });
      for (const lesson of ['sqli', 'xss', 'csrf', 'access', 'stored-xss', 'traversal']) {
        await save(i, lesson, fs.readFileSync(path.join(__dirname, '..', 'lessons', lesson, 'index.php'), 'utf8'));
      }
      await contexts[i].request.post(`${origin}/api/progress`, { headers: { Origin: origin }, data: { completed: [] } });
    }
    await Promise.all(contexts.map(c => c.close()));
  }
});
