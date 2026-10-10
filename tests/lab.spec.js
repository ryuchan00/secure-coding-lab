const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const origin = 'http://localhost:8080';
async function save(request, lab, file = 'index.php') {
  const code = fs.readFileSync(path.join(__dirname, '..', 'lessons', lab, file), 'utf8');
  const res = await request.post(`/api/${lab}/code`, { headers: { Origin: origin }, data: { code } });
  expect(res.status()).toBe(200);
}
test.afterEach(async ({ request }) => {
  for (const id of ['sqli', 'xss', 'csrf', 'access', 'stored-xss', 'traversal']) await save(request, id);
  await request.post('/api/progress', { headers: { Origin: origin }, data: { completed: [] } });
});
test('SQLi uses a real database; parameter binding preserves login and rejects injection', async ({ page, request }) => {
  await save(request, 'sqli');
  await page.goto('http://localhost:8081');
  const login = async (name, password) => {
    await page.locator('[name=name]').fill(name);
    await page.locator('[name=password]').fill(password);
    await page.getByRole('button', { name: 'ログイン', exact: true }).click();
  };
  await login('alice', 'training-only'); await expect(page.locator('#result')).toContainText('ログイン成功');
  await login('alice', 'incorrect'); await expect(page.locator('#result')).toContainText('ログイン失敗');
  await login("alice' -- ", 'incorrect'); await expect(page.locator('#result')).toContainText('ログイン成功');
  await save(request, 'sqli', 'solution.php');
  await login("alice' -- ", 'incorrect'); await expect(page.locator('#result')).toContainText('ログイン失敗');
  await login('alice', 'training-only'); await expect(page.locator('#result')).toContainText('ログイン成功');
});
test('XSS actually executes JavaScript before the fix and renders as text afterward', async ({ page, request }) => {
  const payload = '<img src=x onerror="document.body.textContent=\'XSSが実行されました\'">';
  await save(request, 'xss');
  await page.goto('http://localhost:8082/?name=' + encodeURIComponent(payload));
  await expect(page.locator('body')).toHaveText('XSSが実行されました');
  await save(request, 'xss', 'solution.php');
  await page.reload();
  await expect(page.locator('#greeting')).toContainText(payload);
  await expect(page.locator('img')).toHaveCount(0);
  await page.goto('http://localhost:8082/?name=' + encodeURIComponent('山田 & 鈴木'));
  await expect(page.locator('#greeting')).toHaveText('こんにちは、山田 & 鈴木さん');
});
test('CSRF cross-origin form carries session cookie; token validation blocks it', async ({ page, request }) => {
  await save(request, 'csrf');
  await page.goto('/');
  await page.locator('nav button[data-id=csrf]').click();
  const preview = page.frameLocator('#preview');
  await expect(preview.locator('#balance')).toHaveText('10000');
  await page.getByRole('button', { name: '攻撃ページ', exact: true }).click();
  await preview.getByRole('button').click();
  const result = preview.frameLocator('iframe');
  await expect(result.locator('#balance')).toHaveText('9000');
  await save(request, 'csrf', 'solution.php');
  await preview.getByRole('button').click();
  await expect(result.locator('body')).toContainText('CSRFトークンが一致しません');
  await page.getByRole('button', { name: 'アプリ', exact: true }).click();
  await expect(preview.locator('#balance')).toHaveText('9000');
  await preview.getByRole('button', { name: '送金する' }).click();
  await expect(preview.locator('#balance')).toHaveText('8000');
  const invalid = await page.request.post('http://localhost:8083', { form: { amount: '1000', 'token[]': 'bad' } });
  expect(invalid.status()).toBe(403);
});
test('editor saves and executes PHP; reset and solution work; preview cannot access editor', async ({ page, request }) => {
  await save(request, 'sqli');
  await request.post('/api/progress', { headers: { Origin: origin }, data: { completed: [] } });
  await page.goto('/');
  await expect(page.locator('#title')).toHaveText('SQLインジェクション');
  await expect(page.locator('.CodeMirror')).toBeVisible();
  expect(await page.locator('.CodeMirror .cm-keyword').count()).toBeGreaterThan(0);
  await page.evaluate(() => window.labEditor.setValue('<?php\n$x = 1;\n?>'));
  await page.evaluate(() => { window.labEditor.setCursor({ line: 1, ch: 0 }); window.labEditor.focus(); });
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => window.labEditor.getLine(1))).toBe('    $x = 1;');
  await page.keyboard.press('Shift+Tab');
  expect(await page.evaluate(() => window.labEditor.getLine(1))).toBe('$x = 1;');
  await page.evaluate(() => window.labEditor.setValue('<?php echo "edited PHP runs"; ?>'));
  await page.getByRole('button', { name: /保存して Run/ }).click();
  await expect(page.frameLocator('#preview').locator('body')).toHaveText('edited PHP runs');
  await page.getByRole('button', { name: '修正例を読む' }).click();
  await page.getByRole('button', { name: 'エディタに反映' }).click();
  expect(await page.evaluate(() => window.labEditor.getValue())).toContain('$db->prepare');
  await page.getByRole('button', { name: /保存して Run/ }).click();
  page.once('dialog', d => d.accept());
  await page.getByRole('button', { name: '初期コードに戻す' }).click();
  await expect.poll(() => page.evaluate(() => window.labEditor.getValue())).toBe(fs.readFileSync(path.join(__dirname, '..', 'lessons/sqli/index.php'), 'utf8'));
  await expect(page.locator('#dirty')).toHaveText('保存済み');
  const frame = page.frames().find(f => f.url().startsWith('http://localhost:8081'));
  expect(await frame.evaluate(() => { try { return parent.document.title; } catch { return 'blocked'; } })).toBe('blocked');
  await page.getByRole('button', { name: '学習済みにする' }).click();
  await page.reload();
  await expect(page.locator('#progress')).toHaveText('1 / 6');
  await page.screenshot({ path: 'test-results/workspace.png', fullPage: true });
});
test('editor rejects cross-origin mutation, path traversal and oversized requests', async ({ request }) => {
  const wrongOrigin = await request.post('/api/sqli/code', { headers: { Origin: 'http://localhost:8082' }, data: { code: '<?php echo 1;' } });
  expect(wrongOrigin.status()).toBe(403);
  const wrongHost = await request.get('/api/lessons', { headers: { Host: 'attacker.example:8080' } });
  expect(wrongHost.status()).toBe(403);
  const traversal = await request.post('/api/other/code', { headers: { Origin: origin }, data: { code: 'bad' } });
  expect(traversal.status()).toBe(404);
  const large = await request.post('/api/sqli/code', { headers: { Origin: origin }, data: { code: 'x'.repeat(70000) } });
  expect(large.status()).toBe(413);
  const invalid = await request.post('/api/sqli/code', { headers: { Origin: origin }, data: { code: null } });
  expect(invalid.status()).toBe(400);
});
test('mobile layout remains usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('#title')).toHaveText('SQLインジェクション');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('access control preserves own document and refuses another owner', async ({ page, request }) => {
  await save(request, 'access');
  await page.goto('http://localhost:8085/?id=1');
  await expect(page.locator('#document')).toContainText('aliceの明細');
  await page.goto('http://localhost:8085/?id=2');
  await expect(page.locator('#document')).toContainText('bobの明細');
  await save(request, 'access', 'solution.php');
  expect((await page.goto('http://localhost:8085/?id=2')).status()).toBe(403);
  await expect(page.locator('body')).toContainText('閲覧する権限がありません');
  await page.goto('http://localhost:8085/?id=1');
  await expect(page.locator('#document')).toContainText('aliceの明細');
  expect((await page.goto('http://localhost:8085/?id=999')).status()).toBe(404);
});
test('stored XSS executes again on reload; escaping covers saved and new comments', async ({ page, request }) => {
  const payload = '<img src=x onerror="document.getElementById(\'notice\').textContent=\'保存されたXSSが実行されました\'">';
  await save(request, 'stored-xss');
  await page.goto('http://localhost:8086/');
  await page.locator('[name=message]').fill(payload);
  await page.getByRole('button', { name: '投稿' }).click();
  await expect(page.locator('#notice')).toHaveText('保存されたXSSが実行されました');
  await page.reload();
  await expect(page.locator('#notice')).toHaveText('保存されたXSSが実行されました');
  await save(request, 'stored-xss', 'solution.php');
  await page.reload();
  await expect(page.locator('#notice')).toHaveText('コメントは文字として表示されます');
  await expect(page.locator('#comments .result').first()).toHaveText(payload);
  await expect(page.locator('#comments img')).toHaveCount(0);
  await page.locator('[name=message]').fill('こんにちは & ありがとう');
  await page.getByRole('button', { name: '投稿' }).click();
  await expect(page.locator('#comments .result').first()).toHaveText('こんにちは & ありがとう');
});
test('traversal reads fixture outside public directory; allowlist blocks it', async ({ page, request }) => {
  await save(request, 'traversal');
  await page.goto('http://localhost:8087/?file=guide.txt');
  await expect(page.locator('#content')).toContainText('公開ガイド');
  await page.goto('http://localhost:8087/?file=../private.txt');
  await expect(page.locator('#content')).toContainText('TEST-CUSTOMER-001');
  await save(request, 'traversal', 'solution.php');
  expect((await page.goto('http://localhost:8087/?file=../private.txt')).status()).toBe(403);
  await expect(page.locator('body')).toContainText('公開していません');
  await page.goto('http://localhost:8087/?file=guide.txt');
  await expect(page.locator('#content')).toContainText('公開ガイド');
});
test('beginners see explanations before exercises for all six lessons', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('nav button')).toHaveCount(6);
  const concepts = { sqli: 'SQLとデータベース', xss: 'XSSとは', csrf: 'Cookieとログイン状態', access: '認証と認可', 'stored-xss': '保存型XSSとは', traversal: 'ディレクトリとファイルの場所' };
  for (const [id, heading] of Object.entries(concepts)) {
    await page.locator(`nav button[data-id="${id}"]`).click();
    await expect(page.locator('#explanation')).toBeVisible();
    await expect(page.locator('#explanation')).toContainText(heading);
    await expect(page.locator('#practice')).toBeHidden();
    await page.getByRole('button', { name: '体験と修正の手順' }).click();
    await expect(page.locator('#practice')).toBeVisible();
    await expect(page.locator('#steps h3')).toHaveCount(3);
  }
});
