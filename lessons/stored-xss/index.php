<?php
$db = new PDO('sqlite:/tmp/comments.sqlite');
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$db->exec('CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY, message TEXT NOT NULL)');
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $message = $_POST['message'] ?? '';
    if (is_string($message) && strlen($message) > 0 && strlen($message) <= 1000) {
        $query = $db->prepare('INSERT INTO comments (message) VALUES (?)');
        $query->execute([$message]);
    }
    header('Location: ' . parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH));
    exit;
}
$comments = $db->query('SELECT message FROM comments ORDER BY id DESC LIMIT 30')->fetchAll(PDO::FETCH_COLUMN);
function h($s) { return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
?>
<!doctype html><html lang="ja"><meta charset="utf-8"><title>コメント掲示板</title>
<?php readfile('/opt/style.html'); ?>
<h1>コメント掲示板</h1><p id="notice">コメントは文字として表示されます</p>
<form method="post"><label>コメント <input name="message" maxlength="1000" required></label><button>投稿</button></form>
<h2>保存されたコメント</h2><div id="comments">
<?php foreach ($comments as $comment): ?>
<!-- TODO: コメントをHTML本文へ出力する直前にエスケープする。 -->
<div class="result"><?= $comment ?></div>
<?php endforeach; ?></div></html>
