# 制度信用ダッシュボード V14.49 クラウド試作版

## これは何？
GitHub Pages の無料公開ページに、V14.48 の画面を表示する**閲覧専用の試作版**です。
自宅PCをつけておく必要はありません。スマホのモバイル回線でもアクセスできます。

## 重要な制限
- **まだクラウドに公開していません。** GitHubへの登録と公開設定が必要です。
- 登録銘柄の追加・削除、手動更新、検索での新規銘柄追加はできません。
- 取得済みのデータだけを表示します。株価はリアルタイムではなく定期更新時点のスナップショットです。
- JPXの更新・Yahooなどの外部サイトからの取得はGitHub Actions上で未検証で、失敗する可能性があります。
- GitHub Actionsの定期実行は遅延することがあり、19時25分の厳密な更新は保証できません。
- 公開リポジトリの `data.json` と銘柄一覧は**誰でも閲覧可能**です。個人情報や秘密情報を入れないでください。
- 28銘柄を引き継ぐには、PC版の「登録データをバックアップ」で保存したJSONを、このフォルダの `data.json` と置き換えてください。元のPC版のファイルは消さないでください。
- `data_seed.json` は初期4銘柄のサンプルです。

## GitHub Pages 公開手順
1. https://github.com/signup で無料アカウントを作る。
2. GitHubで新しい **Public** リポジトリを作る（例: `seido-dashboard`）。
3. このZIPを展開して、**隠しフォルダ `.github` を含む全ファイル**をリポジトリのルートにアップロードする。
4. Settings → Actions → General → Workflow permissions で **Read and write permissions** を選ぶ。
5. Settings → Pages → Build and deployment → Source を **GitHub Actions** にする。
6. Actions → Update and publish dashboard → Run workflow を手動実行する。
7. Actions の処理が成功したら、Settings → Pages に表示されるURLをスマホで開く。

**失敗した場合**: Actions のログを確認してください。外部データ取得の失敗、GitHub Pages未有効化、書込権限不足が考えられます。

## 動作確認
HTML内のJavaScriptは静的スナップショットへアクセスするように変更しています。
Pythonのスナップショット作成処理はGitHub Actions上でネットワークアクセスが必要です。
