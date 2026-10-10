<?php
$db = new PDO('sqlite:/tmp/accounts.sqlite');
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$db->exec('CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, password TEXT)');
$seed = $db->prepare('INSERT OR IGNORE INTO users VALUES (?, ?)');
$seed->execute(['alice', 'training-only']);
$message = 'ログインしてください';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name = $_POST['name'] ?? '';
    $password = $_POST['password'] ?? '';
    // TODO: 入力値がSQLの構文として解釈されないように修正する。
    $query = $db->prepare('SELECT name FROM users WHERE name = ? AND password = ?');
    $query->execute([$name, $password]);
    $user = $query->fetchColumn();
    $message = $user ? 'ログイン成功: ' . $user : 'ログイン失敗';
}
function h($s) { return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
?>
<!doctype html><html lang="ja"><meta charset="utf-8"><title>SQLi / Login</title>
<?php readfile('/opt/style.html'); ?>
<h1>会員ログイン</h1><small>練習用アカウント: alice / training-only</small>
<form method="post"><label>ユーザー名 <input name="name" required></label>
<label>パスワード <input name="password" type="password" required></label><button>ログイン</button></form>
<div class="result" id="result"><?= h($message) ?></div>
<p><small>教材を短くするためパスワードを平文保存しています。本番ではpassword_hash / password_verifyを使います。</small></p></html>
