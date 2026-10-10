'use strict';
// All PHP and lesson text is assigned with textContent/value, never innerHTML.
const $ = id => document.getElementById(id);
let lessons = [], current, saved = '', solution = '', busy = false;
let completed;
try { completed = new Set(JSON.parse(localStorage.getItem('scl-completed') || '[]')); } catch { completed = new Set(); }
const cm = CodeMirror.fromTextArea($('editor'), {
  mode: 'application/x-httpd-php', theme: 'dracula', lineNumbers: true,
  styleActiveLine: true, matchBrackets: true, indentUnit: 4, tabSize: 4,
  indentWithTabs: false, autofocus: false,
  extraKeys: {
    Tab: 'indentMore', 'Shift-Tab': 'indentLess',
    'Ctrl-Enter': () => action(run), 'Cmd-Enter': () => action(run),
  },
});
cm.getInputField().setAttribute('aria-label', 'PHPコードエディタ');
window.labEditor = cm;
const dirty = () => cm.getValue() !== saved;
function status(text, error = false) { $('status').textContent = text; $('status').classList.toggle('error', error); }
async function api(path, data) {
  const response = await fetch('/api/' + path, data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '処理に失敗しました');
  return result;
}
function lines() {
  $('dirty').textContent = dirty() ? '未保存' : '保存済み';
}
function progress() {
  $('progress').textContent = `${lessons.filter(l => completed.has(l.id)).length} / ${lessons.length}`;
  $('complete').textContent = completed.has(current?.id) ? '✓ 学習済み（クリックで戻す）' : '学習済みにする';
}
function preview(attack = false) {
  const url = `http://localhost:${attack ? 8084 : current.port}/`;
  $('preview').src = `${url}?_run=${Date.now()}`;
  $('external').href = url;
  $('app-tab').classList.toggle('selected', !attack);
  $('attack-tab').classList.toggle('selected', attack);
  $('preview-note').textContent = attack ? '別オリジンからのフォーム送信' : 'PHPの実行結果';
}
async function select(lesson) {
  if (dirty() && !confirm('未保存の変更を破棄して教材を切り替えますか？')) return;
  const result = await api(lesson.id + '/code');
  current = lesson; saved = result.code; cm.setValue(saved); cm.clearHistory(); lines();
  document.querySelectorAll('nav button').forEach(b => { const active = b.dataset.id === lesson.id; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); });
  $('title').textContent = lesson.title; $('subtitle').textContent = lesson.subtitle; $('duration').textContent = lesson.duration;
  $('lesson-number').textContent = `LESSON ${String(lessons.indexOf(lesson) + 1).padStart(2, '0')}`;
  $('steps').replaceChildren();
  lesson.steps.forEach((step, i) => { const h = document.createElement('h3'), n = document.createElement('span'), p = document.createElement('p'); n.className = 'step-number'; n.textContent = String(i + 1).padStart(2, '0'); h.append(n, step.title); p.textContent = step.body; $('steps').append(h, p); });
  $('payload-box').hidden = !lesson.payload; $('payload').textContent = lesson.payload || '';
  $('attack-tab').hidden = lesson.id !== 'csrf';
  preview(); progress(); status('コードを編集し、保存してRunで動作を確かめてください。');
}
async function action(fn) {
  if (busy) return;
  busy = true;
  const buttons = [...document.querySelectorAll('button')];
  buttons.forEach(b => b.disabled = true);
  try { await fn(); } catch (e) { status(e.message, true); }
  finally { busy = false; buttons.forEach(b => b.disabled = false); }
}
async function run() {
  if (!current) return;
  const code = cm.getValue();
  await api(current.id + '/code', { code }); saved = code; lines(); preview();
  status('保存しました。右の画面で通常操作と攻撃入力を試してください。');
}
$('run').onclick = () => action(run);
cm.on('change', lines);
$('reset').onclick = () => action(async () => {
  if (!confirm('この教材のコードを初期状態に戻しますか？')) return;
  const result = await api(current.id + '/reset', {});
  saved = result.code; cm.setValue(saved); cm.clearHistory(); lines(); preview(); status('初期コードに戻しました。CSRFの残高とセッションは維持されます。');
});
$('solution').onclick = () => action(async () => { solution = (await api(current.id + '/solution')).code; $('solution-code').textContent = solution; $('solution-dialog').showModal(); });
$('close-dialog').onclick = () => $('solution-dialog').close();
$('apply-solution').onclick = () => { cm.setValue(solution); lines(); $('solution-dialog').close(); status('修正例を反映しました。保存してRunで実行してください。'); };
$('copy').onclick = async () => { try { await navigator.clipboard.writeText(current.payload); status('攻撃入力をコピーしました。右のフォームに貼り付けてください。'); } catch { status('コピーできませんでした。攻撃入力を選択してコピーしてください。', true); } };
$('app-tab').onclick = () => preview(); $('attack-tab').onclick = () => preview(true);
$('reload').onclick = () => preview($('attack-tab').classList.contains('selected'));
$('complete').onclick = () => { if (completed.has(current.id)) completed.delete(current.id); else completed.add(current.id); try { localStorage.setItem('scl-completed', JSON.stringify([...completed])); } catch {} progress(); };
window.addEventListener('beforeunload', e => { if (dirty()) { e.preventDefault(); e.returnValue = ''; } });
action(async () => {
  lessons = await api('lessons');
  lessons.forEach((l, i) => { const b = document.createElement('button'), n = document.createElement('span'), t = document.createElement('strong'); n.textContent = String(i + 1).padStart(2, '0'); t.textContent = l.title; b.dataset.id = l.id; b.append(n, t); b.onclick = () => action(() => select(l)); $('lessons').append(b); });
  await select(lessons[0]);
});
