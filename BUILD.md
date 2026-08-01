# ビルド手順

この文書は、非公式改変版 `Uchinoko for Palworld v2.2.13 no_contact` のソースから、一般ユーザー向け配布物を再作成する手順です。

## 必要環境

- Windows 10またはWindows 11（64-bit）
- .NET Framework 4.8
- Windows PowerShell 5.1以上、またはPowerShell 7
- ZIPを作成できる空き容量

追加のNuGetパッケージやVisual Studioプロジェクト生成は不要です。GUIはWindows付属の.NET Framework C#コンパイラでビルドします。配布に必要な `ooz.pyd`、`python3.dll`、`pyooz-*.dist-info` は `assets\blender_patch\` に収録されています。

## GUI実行ファイルだけをビルドする

ソースZIPを展開し、そのルートで次を実行します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\app\build_app.ps1
```

成功すると、ソースルートに `Uchinoko.exe` が生成されます。

## 一般ユーザー向け配布ZIPを作る

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\make_dist.ps1 `
  -Version v2.2.13 `
  -Suffix _no_contact
```

生成先:

```text
dist\Uchinoko_for_Palworld_v2.2.13_full_no_contact.zip
```

公開時は、このファイルを次の名前へ変更します。

```text
Uchinoko_for_Palworld_v2.2.13_no_contact.zip
```

`make_dist.ps1` は、GUIを改めてコンパイルした後、実行時に必要なファイルだけをステージングし、テスト、開発ツール、キャッシュ、ログ、一時展開フォルダを除外してZIPを作成します。

## 問い合わせ・更新機能について

この版には、診断情報の外部送信機能、元作者側サービスへの送信処理、元作者側の更新確認、更新通知、自動更新は含まれていません。診断ログはクリップボードへコピーするだけです。

Blender未導入時の初回実行では、`pipeline\cli\ensure_blender.ps1` がBlender公式配布元からBlender 4.3.2を取得する場合があります。これはアプリの実行時セットアップであり、ソースや配布ZIPのビルドには不要です。

## ビルド後の最低限の確認

```powershell
.\Uchinoko.exe --check-i18n .\work\check-i18n
.\Uchinoko.exe --check-palworld-compat .\work\check-palworld-compat
.\Uchinoko.exe --check-apply-language .\work\check-apply-language
.\Uchinoko.exe --check-sanitize-clipboard .\work\check-sanitize
```

各コマンドの終了コードが `0` であることを確認してください。実ゲーム内確認には、利用者が権利を持つVRMとPalworldのインストールが別途必要です。
