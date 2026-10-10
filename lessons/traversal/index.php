<?php
// 演習用の架空データを用意する。
@mkdir('/tmp/files/public', 0700, true);
file_put_contents('/tmp/files/public/guide.txt', '公開ガイド: このファイルは誰でも閲覧できます。');
file_put_contents('/tmp/files/private.txt', '非公開の架空データ: 顧客情報 TEST-CUSTOMER-001');
$file = $_GET['file'] ?? 'guide.txt';
if (!is_string($file)) {
    http_response_code(400);
    exit('ファイル名を指定してください');
}
// TODO: 公開してよいファイルだけを許可する。

$content = @file_get_contents('/tmp/files/public/' . $file);
if ($content === false) {
    http_response_code(404);
    exit('ファイルが見つかりません');
}
function h($s) { return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
?>
<!doctype html><html lang="ja"><meta charset="utf-8"><title>公開ファイル</title>
<?php readfile('/opt/style.html'); ?>
<h1>公開ファイル</h1><form method="get"><label>ファイル名 <input name="file" value="<?= h($file) ?>" required></label><button>表示</button></form>
<pre id="content" class="result"><?= h($content) ?></pre></html>
