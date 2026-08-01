# Security Policy / セキュリティポリシー

## 日本語

### 対象バージョン

セキュリティ修正は、この非公式改変版の最新リリースを対象とします。

### 脆弱性の報告

[改変版GitHub Issues](https://github.com/Guldin-Orpheus/Uchinoko-OutputScale-OutfitSelector/issues)へ、影響するバージョン、再現手順、必要に応じて伏字確認済みの診断ログを報告してください。機密性が高い内容では、GitHubのPrivate vulnerability reportingが利用可能な場合に限り、その経路を使用してください。個人情報、VRM、生成PAK、セーブデータは添付しないでください。

本アプリには診断情報の送信機能や自動更新機能はありません。通常の変換はローカルで完結し、初回のBlender導入時だけBlender公式配布元へアクセスする可能性があります。詳細は `PRIVACY.md` を参照してください。

本改変版は元作者の公式サポート対象外です。本改変版の問題を元作者へ報告しないでください。

### Windows Defender等の警告

本アプリは未署名の.NET実行ファイルで、PowerShellやBlenderを子プロセスとして起動するため、環境によってヒューリスティック検知される可能性があります。警告だけを理由に除外設定を追加せず、配布元、ZIPハッシュ、同梱ライセンス、ソースを確認してください。異常な通信や改ざんを疑う場合は実行を中止し、上記GitHub Issuesへ報告してください。

## English

### Supported versions

Security fixes target the latest release of this unofficial modified edition.

### Reporting a vulnerability

Report the affected version, reproduction steps, and—when useful—a reviewed and redacted diagnostic log through the [modified edition's GitHub Issues](https://github.com/Guldin-Orpheus/Uchinoko-OutputScale-OutfitSelector/issues). For sensitive matters, use GitHub Private vulnerability reporting only if it is available. Do not attach personal data, VRM files, generated PAK files, or save data.

The application has no diagnostic submission feature and no automatic update feature. Normal conversion is local. It may access Blender's official download host only during first-time Blender setup. See `PRIVACY.en.md` for details.

This modified edition is unofficial and is not supported by the original developer. Do not report problems with this edition to the original developer.

### Antivirus warnings

This application is an unsigned .NET executable and starts PowerShell and Blender as child processes. Heuristic products may flag it in some environments. Do not add exclusions solely because of a warning; verify the distribution source, ZIP hash, bundled licenses, and source code. If you suspect unexpected network activity or tampering, stop running it and report the observation through the GitHub Issues page above.
