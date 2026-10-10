<?php
session_name('lab_csrf');
session_set_cookie_params(['httponly' => true, 'samesite' => 'Lax']);
session_start();
// この教材では、口座を開くと練習ユーザーとしてログインする。
$_SESSION['balance'] ??= 10000;
$_SESSION['token'] ??= bin2hex(random_bytes(32));
$message = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // TODO: セッションに保存したトークンとPOSTされたトークンを比較する。
    $amount = filter_var($_POST['amount'] ?? '', FILTER_VALIDATE_INT);
    if ($amount !== false && $amount > 0 && $amount <= $_SESSION['balance']) {
        $_SESSION['balance'] -= $amount;
        $message = '送金しました';
    } else {
        $message = '金額を確認してください';
    }
}
function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
?>
<!doctype html><html lang="ja"><meta charset="utf-8"><title>CSRF / Account</title>
<?php readfile('/opt/style.html'); ?>
<h1>練習用の口座</h1><div class="result">残高: <strong id="balance"><?= h($_SESSION['balance']) ?></strong> 円</div>
<form method="post">
<input type="hidden" name="token" value="<?= h($_SESSION['token']) ?>">
<label>送金額 <input name="amount" type="number" min="1" value="1000" required></label><button>送金する</button></form>
<p id="result"><?= h($message) ?></p></html>
