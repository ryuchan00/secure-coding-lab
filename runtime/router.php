<?php
// Classroom gateway selects the learner. This router only selects a lesson.
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$lessons = ['sqli', 'xss', 'csrf', 'access', 'stored-xss', 'traversal'];
$parts = explode('/', trim($path, '/'));
if (count($parts) !== 1 || !in_array($parts[0], $lessons, true)) {
    http_response_code(404);
    echo '教材が見つかりません';
    return true;
}
$directory = '/work/' . $parts[0];
chdir($directory);
require $directory . '/index.php';
return true;
