# mac-maintenance

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

[![Tests](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml/badge.svg)](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Codex 向けの Mac メンテナンススキルです。ハードウェアとソフトウェアの状態確認、更新の検討、旧バージョンの整理を支援し、クリーンアップ前後に再確認できる記録を残します。

補助スクリプトは Python 標準ライブラリのみを使って情報を収集します。実際の更新やクリーンアップは、ユーザーが許可した範囲で、エージェントが適切なメンテナンスツールを使って行います。スクリプト自体はインストール、削除、再起動、サービスの起動を行いません。

**言語について：** この紹介文は 4 言語で提供しています。スキルの指示、詳細な参考文書、スクリプトが生成する Markdown レポートは、現在は簡体字中国語です。CLI のオプション名と JSON のフィールド名は英語です。

## 主な機能

| 機能 | 出力と対象範囲 |
|---|---|
| 読み取り専用の点検 | システム、ハードウェア、バッテリー、アプリ、Homebrew のメタデータ、ディレクトリ使用量を調べ、JSON と中国語の Markdown レポートを出力 |
| 更新の検討 | 公式情報、プラットフォーム、アーキテクチャ、バージョン、プロジェクトとの互換性をエージェントが確認。照合できない項目は未確認として扱う |
| クリーンアップのプレビュー | 対象を個別に指定してメタデータを記録し、リンク、保護対象パスとの交差、対象同士の重複、内部にある別ボリュームのマウント、関連プロセスを確認 |
| 再検証 | プレビュー後のファイル、パス、設定の変化を検出。メタデータに変化がないことは、削除の許可を意味しない |
| 結果の記録 | 申告された操作と観測結果を分け、元のパスの使用量減少、記録上の削除、ボリュームの空き容量の変化を区別 |
| 個人設定 | 更新対象からの除外、メーカー指定の更新ツール、保護対象パスを設定。ユーザーの現在の明示的な指示を優先 |

エージェントが項目ごとに判断し、許可された範囲で操作して結果を記録するメンテナンスに適しています。全キャッシュを一括削除するコマンドはありません。公式の更新ツールやアンインストーラー、プロジェクトのバックアップ、必要な動作確認もメンテナンス手順の一部です。

## Codex へのインストール

Codex に次のように依頼します。

```text
$skill-installer を使って、https://github.com/Sorasukiawa/mac-maintenance のルートにある mac-maintenance スキルをインストールしてください。同名のスキルがすでにある場合は、差分を確認し、個人設定を保持してください。
```

手動でインストールする場合は、現在の [Codex のローカルスキルに関するドキュメント](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)に記載されたユーザーディレクトリを使います。

```sh
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/Sorasukiawa/mac-maintenance.git "$HOME/.agents/skills/mac-maintenance"
```

保存先が空でない場合、`git clone` は停止します。同名のスキルを複数置かず、既存のインストールを更新してください。通常、Codex は変更を自動検出します。スキルが表示されない場合は再起動してください。

依頼の例：

```text
$mac-maintenance を使って、この Mac を読み取り専用で点検し、更新や整理を検討できる項目を一覧にしてください。
```

```text
$mac-maintenance を使い、許可した範囲で更新、整理、クリーンアップを完了してください。指定したアプリは対象から除外してください。新バージョンが実際に動作し、関連する依存関係に影響がないことを確認できた場合は、旧バージョンを削除して構いません。
```

## スクリプトを直接実行する

macOS と、動作する Python 3.10 以降の実行環境が必要です。追加の Python パッケージは不要です。まず `python3 --version` が正常に実行できることを確認してください。システムの実行環境がライセンスや権限の問題で使えない場合は、利用可能な別の実行環境を使います。

リポジトリのディレクトリで実行します。

```sh
mkdir -p work/maintenance
python3 scripts/audit.py --quick \
  --output work/maintenance/audit.json \
  --report work/maintenance/audit.md
```

`--online` を追加すると、利用可能なシステム更新を照会します。`--quick` を省略すると、周辺機器、機能拡張、バックアップ、サービスの詳細も収集します。既存の出力ファイルは上書きしないため、実行ごとに新しいパスを指定してください。一部の確認に失敗した場合は `coverage_gaps` に記録されます。終了コードが成功でも、すべての確認が成功したとは限りません。

クリーンアップ対象を個別に指定する手順：

```sh
python3 scripts/cleanup.py preview --targets work/maintenance/targets.json \
  --output work/maintenance/plan.json
python3 scripts/cleanup.py verify --plan work/maintenance/plan.json
# 用途と使用状況の根拠を確認し、許可されたメンテナンスを実行します。
python3 scripts/cleanup.py record --plan work/maintenance/plan.json \
  --results work/maintenance/results.json --log work/maintenance/actions.jsonl
```

`targets.json`、`results.json` の形式と各状態の意味は、[スクリプトガイド](references/script-usage.md)を参照してください。`review` は引き続き個別の判断を要し、`unchanged` は書き込みを防ぐロックではありません。同じボリューム内での移動では、ディスクの空き容量は増えません。実際に実行できる操作は、利用可能なツールと権限によって異なります。

## 個人設定

公開版の既定設定には、アプリの除外指定や個人のパスは含まれていません。サンプルを Git の追跡対象外のローカル設定にコピーしてから編集します。

```sh
cp -n config/preferences.example.json config/preferences.local.json
python3 scripts/audit.py --quick --preferences config/preferences.local.json
```

`com.example.*` のバンドル ID は架空の例です。実際のアプリから読み取った ID に置き換えてください。同じ作業の `preview` と `verify` では同じ設定を使います。リポジトリの更新で上書きされないよう、個人設定はローカルファイルまたは作業用ディレクトリに保存してください。個人の点検レポートや操作ログはコミットしないでください。

## 検証と制限

```sh
python3 -m unittest discover -v -s tests
```

テストでのファイルの作成、移動、削除は、一時的なテスト用データ内に限定しています。plist 形式、権限エラー、タイムアウト、リンクと大文字・小文字による別名、対象の変化、旧バージョンの代替確認、ログの整合性、容量計算を対象にしています。プラットフォームやファイルシステムに依存するテストは、適用できない環境では明示的にスキップします。Linux の CI は共通の補助処理を検証するもので、Linux 本体のメンテナンスへの対応を示すものではありません。

最初の公開版は、1 台の Mac での読み取り専用の試行と、独立したシナリオレビューをもとに開発しました。ハードウェアとソフトウェアの検証範囲はまだ限られています。完全なハードウェア診断、メーカー製ファームウェアの適合確認、専門アプリのライセンスやプロジェクトとの互換性には、個別の根拠が必要です。スナップショットはメタデータを記録するもので、内容のハッシュやトランザクションではなく、削除後の復元を保証しません。ログにはローカルパスやアプリの情報が含まれるため、共有前に必要に応じて個人情報を取り除いてください。

## コントリビューションとライセンス

再現手順のある Issue や Pull Request を歓迎します。macOS と Python のバージョン、期待する動作、個人情報を除いた最小限のテスト用データを添えてください。手順を変更する場合は具体的な発生条件を説明し、スクリプトを変更する場合は関連するテストを追加してください。テストの削除対象に、実際のプロジェクトライブラリやユーザーのキャッシュを使わないでください。

コードとドキュメントは [MIT ライセンス](LICENSE)で公開しています。

設計では、[mac-storage-cleaner](https://github.com/JubaKitiashvili/mac-storage-cleaner) のプレビュー・ログ・テストの構成と、[mac-performance-maintenance](https://github.com/rioriost/skills/tree/main/plugins/mac-performance-maintenance) の段階的な点検および未確認範囲の記録を参考にしました。本リポジトリのスクリプトは独自に実装しており、これらのプロジェクトのクリーンアップコードや削除ルールは取り込んでいません。
