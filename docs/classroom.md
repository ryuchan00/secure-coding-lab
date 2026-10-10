# 10〜20人が同じURLで受講する

1台のLinuxサーバーでDocker Engine / Docker Compose v2を動かし、全員が同じ入口URLから受講します。受講者の端末にPHPやDockerをインストールする必要はありません。講師が1人に1つの受講コードを配ります。同じ受講コードを複数人へ配ると同じ環境を使うため、必ず各自のコードを配ってください。

## 社内LAN・VPNでの起動

サーバー側でリポジトリを取得します。Python 3も設定生成に使います。次の `192.168.1.50` は、受講者の端末から到達できるサーバーの実際のIPアドレスへ置き換えてください。

```sh
git clone https://github.com/ryuchan00/secure-coding-lab.git
cd secure-coding-lab
python3 scripts/classroom.py --seats 20 --host 192.168.1.50 --bind 0.0.0.0
docker compose -f .classroom/compose.json up --build -d --wait
```

全員が `http://192.168.1.50:8080` を開きます。講師用の `.classroom/roster.csv` には受講者と受講コードの一覧が入っています。各自の行だけを本人へ渡してください。一覧を受講者全員で共有すると、他人の環境へ入れるようになります。

受講コードは設定生成時にランダムに作ります。設定フォルダーはGitの対象から除外しています。生成済みのフォルダーへ設定を上書きしないため、再起動しても同じ受講コードを使えます。サーバーのIPが変わる場合は、設定と保存データの移行が必要です。

ブラウザは教材の表示に8081番、CSRF攻撃ページに8084番も使います。8080・8081・8084の3ポートを、受講者がいるネットワークから到達可能にしてください。教材のURLはサーバーのIPへ向き、受講者のlocalhostには向きません。

受講者用Dockerネットワークには10.240.0.0/22を小さな範囲へ分割して使います。社内LANやVPNと重なる場合は、生成時に `--subnet 10.244.0.0/22` のように重ならない範囲を指定してください。同じホストで複数の研修環境を起動するときも、別々の範囲とDocker Composeのプロジェクト名を使います。

この起動設定はHTTPです。社内LANやVPN内で使用し、一般公開する場合は先に全3オリジンのHTTPS対応と入口のアクセス制限を整えてください。ソースの公開リポジトリと、脆弱なPHPを実行する研修サーバーの一般公開は別の判断です。

## 受講者ごとの分離

- 編集したPHPと学習済みの記録は、受講者専用のDockerボリュームへ保存します。
- PHPは受講者専用のコンテナで実行します。同じSQLiteのファイル名を使っても、他人のDBと共有しません。
- Cookieを使ったPHPのセッションと送金残高は、受講者専用の実行環境で扱います。
- 各受講者のコンテナは別のinternalネットワークに属します。共通ゲートウェイが受講用Cookieを確認して、自分の環境にだけ振り分けます。
- 受講用の振り分けCookieはHttpOnlyにし、編集できるPHPへ渡しません。アプリ・PHPコンテナへDockerソケットを渡しません。

共有サーバーで任意のPHPコードを実行するため、対象は講師が受講コードを配布した研修参加者です。匿名の一般利用者向けコード実行サービスとしての隔離強度は保証していません。

## 規模と検証範囲

20人分の設定を生成できます。1人につき編集用とPHP実行用の常駐コンテナが1つずつあり、共通の入口とゲートウェイが加わります。PHPコンテナの上限は1人あたりCPU 0.5コア・メモリ256MB、編集コンテナは128MBです。上限の合計は実際の常時使用量ではありません。

自動テストでは2人の独立したブラウザを使い、同時編集、SQLite、学習済み記録、CSRF残高、未認証での拒否を検証します。20人分の環境を実際に起動し、20人の同時ログインと合計200回の保存・PHP実行・SQLite照合にも成功しました。これはHTTPによる同時実行の確認で、20台のブラウザを使った実際の研修や長時間の負荷試験ではありません。本番の研修前に実際のサーバーで予定人数が入口へ入り、教材をRunできることを確認してください。サーバーは専用のLinux VM、社内のLinux端末、AWS EC2などを使えます。

## 停止・再開・初期化

```sh
# 停止。保存コードと学習済み記録は残る
docker compose -f .classroom/compose.json down
# 再開
docker compose -f .classroom/compose.json up -d --wait
# 受講者01のDB・コメント・口座残高を戻す。保存コードは残る
docker compose -f .classroom/compose.json restart learner01-runtime
```

PHPのDBや口座残高は一時領域にあるため、実行コンテナを停止・再作成すると消えます。「初期コードに戻す」は選択した教材のPHPだけを戻します。受講を終了しても保存コードと学習済み記録は残り、同じコードで再開できます。

保存コードも全員分消す場合は `docker compose -f .classroom/compose.json down -v` を使います。これは研修の保存データを削除する操作です。

## 2人での分離テスト

個人用環境のブラウザテストと同時に検証するため、ここでは別のポートを使います。

```sh
python3 scripts/classroom.py --seats 2 --editor-port 9080 --runtime-port 9081 --attacker-port 9084 --output .classroom-test
docker compose -f .classroom-test/compose.json up --build -d --wait
CLASSROOM_CONFIG=.classroom-test npx playwright test tests/classroom.spec.js
docker compose -f .classroom-test/compose.json down -v
```

## 20人分の同時保存・実行テスト

Node.js 18以降で `node scripts/classroom-load.mjs .classroom` を実行すると、生成された全受講者が同時にログインし、1人10回ずつ保存・実行・SQLite照合を行います。全員のSQLi教材を書き換えるテストのため、専用のテスト環境で実行してください。終了時にSQLiの初期コードを戻します。

2026年10月10日にDocker Desktop / WSL環境で20人分・200回の照合に成功しました。HTTPテストの所要時間は1.13秒でした。この数値は教材の画面操作全体を含まず、提供先のサーバーの性能を保証するものではありません。
