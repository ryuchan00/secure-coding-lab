<?php
session_name('lab_access');
session_start();
// 練習用: aliceとしてログイン済みの状態を作る。
$_SESSION['user_id'] = 'alice';
$documents = [
    '1' => ['owner' => 'alice', 'text' => 'aliceの明細: 書籍 2000円'],
    '2' => ['owner' => 'bob', 'text' => 'bobの明細: 医療費 8000円'],
];
$id = $_GET['id'] ?? '1';
$document = is_string($id) ? ($documents[$id] ?? null) : null;
if ($document === null) {
    http_response_code(404);
    exit('明細が見つかりません');
}
// TODO: 明細の所有者とログイン中の利用者を比較する。
if ($document['owner'] !== $_SESSION['user_id']) {
    http_response_code(403);
    exit('この明細を閲覧する権限がありません');
}
function h($s) { return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
?>
<!doctype html><html lang="ja"><meta charset="utf-8"><title>明細の閲覧</title>
<?php readfile('/opt/style.html'); ?>
<h1>明細の閲覧</h1><p>ログイン中: alice / 自分の明細番号: 1</p>
<form method="get"><label>明細番号 <input name="id" value="<?= h($id) ?>" required></label><button>表示</button></form>
<div id="document" class="result"><?= h($document['text']) ?></div></html>
