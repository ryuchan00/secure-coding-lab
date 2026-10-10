<?php
$name = $_GET['name'] ?? 'ゲスト';
?>
<!doctype html><html lang="ja"><meta charset="utf-8"><title>XSS / Greeting</title>
<?php readfile('/opt/style.html'); ?>
<h1>あいさつメーカー</h1>
<form method="get"><label>名前 <input name="name" placeholder="名前を入力"></label><button>表示する</button></form>
<!-- TODO: 入力をHTMLとして解釈させず、文字列として表示する。 -->
<div class="result" id="greeting">こんにちは、<?= $name ?>さん</div>
</html>
