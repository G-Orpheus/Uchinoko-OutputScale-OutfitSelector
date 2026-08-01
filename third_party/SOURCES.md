# third_party 出所記録

この文書は、本プロジェクトで使用する第三者コンポーネント、および開発・検証時に使用した外部素材の取得元とライセンスを記録するものです。

一般ユーザー向け配布ZIPに実際に同梱されるものと、初回セットアップ時に取得されるもの、開発・検証時にのみ使用し配布物には含めないものを区別して記載します。

関連文書：

- `THIRD_PARTY_LICENSES.txt`
- `THIRD_PARTY_NOTICES.md`
- `PROVENANCE_NOUE_ASSETS.md`

## 一般ユーザー向け配布ZIPに同梱するもの

| ファイル | 出所 | ライセンス | 取得日 |
|---|---|---|---|
| `VRM_Addon_for_Blender-Extension-4_4_0.zip` | https://github.com/saturday06/VRM-Addon-for-Blender/releases/tag/v4.4.0 | MIT。全文は `licenses/VRM_Addon_for_Blender_MIT.txt` | 2026-07-21 |
| `pyooz-0.0.8-source/pyooz-0.0.8.tar.gz` | https://files.pythonhosted.org/packages/97/95/025dc21dbfe92855d6ab7b3c960159a682f647f71ac748714f0512695af6/pyooz-0.0.8.tar.gz（PyPI sdist。`pypi.org/pypi/pyooz/0.0.8/json` 経由） | GPL-3.0-or-later。詳細は `pyooz-0.0.8-source/NOTICE.md` | 2026-07-26 |
| `../blender_patch/python3.dll` | CPython 3.11.0 Windows公式配布物由来。Blender 4.3.2 Windows Portable同梱版とは一致しない | Python Software Foundation License | 取得日不明 |

## VRM Add-on for Blender

VRMファイルの読み込みには、VRM Add-on for Blender 4.4.0を使用します。

一般ユーザー向け配布ZIPには、以下を同梱します。

- `VRM_Addon_for_Blender-Extension-4_4_0.zip`
- `licenses/VRM_Addon_for_Blender_MIT.txt`

取得元：

- https://github.com/saturday06/VRM-Addon-for-Blender/releases/tag/v4.4.0

ライセンス：

- MIT License

## pyoozについて

配布物には、PalworldのPAKで使用される圧縮データを処理するため、pyooz 0.0.8由来のコンポーネントを同梱しています。

主な関連ファイル：

- `../blender_patch/ooz.pyd`
- `../../pipeline/py/ooz_worker_gpl.py`
- `pyooz-0.0.8-source/`

`ooz.pyd` は、`pipeline/py/ooz_worker_gpl.py` から別プロセスを通じて使用されます。

pyoozに対応するソースコードは、外部サイトだけに依存せず確認できるよう、以下へ同梱しています。

- `pyooz-0.0.8-source/pyooz-0.0.8.tar.gz`

取得元URL、SHA-256、バージョン一致の確認記録については、以下を参照してください。

- `pyooz-0.0.8-source/NOTICE.md`

GPLv3のライセンス全文は、以下に同梱しています。

- `pyooz-0.0.8-source/LICENSE`

## pyoozのsdistに含まれる第三者コード

pyooz 0.0.8のsdistには、pyoozおよびooz本体のコードに加え、以下の第三者コードが含まれます。

### ooz / Kraken Decompressor

一部のソースファイルには、次の著作権表示があります。

- `Kraken Decompressor for Windows`
- Copyright (C) 2016, Powzix

pyoozおよびoozのライセンス・著作権表示については、同梱したsdistおよびNOTICEを参照してください。

### SIMDe

- 名称：SIMDe
- ライセンス：MIT License
- 著作権表示：Copyright 2017-2020 Evan Nemerson

### Hedley

- 名称：Hedley
- ライセンス：CC0-1.0
- 著作者：Evan Nemerson

SIMDeおよびHedleyについては、pyoozのsdist内にある各ソースファイル冒頭のライセンスコメントを確認しています。

pyoozのsdistには、これらについて独立したLICENSEファイルが含まれていないため、この文書では確認できた事実のみを記録します。

詳細は以下を参照してください。

- `pyooz-0.0.8-source/NOTICE.md`

## python3.dll

pyoozをBlender同梱Python環境で使用するため、以下のファイルを一般ユーザー向け配布ZIPに同梱しています。

- `../blender_patch/python3.dll`

このファイルは、CPython 3.11.0 Windows公式配布物由来のstable ABI用DLLです。
PEバージョン情報は `3.11.0` / `Python Core` / `Python Software Foundation`で、
CPython 3.11.0 Windows配布物から保存した検証用実体とSHA-256が完全に一致します。

- 同梱ファイル: `4055D1B9E553B78C244143AB6B48151604003B39A9BF54879DEE9175455C1281`
- CPython 3.11.0 Windows検証用実体: `4055D1B9E553B78C244143AB6B48151604003B39A9BF54879DEE9175455C1281`
- Blender 4.3.2 Windows Portable同梱版: `F01B4E426DE80B96BB2BCAD4682A0422F8FAF570661F1E156ACFA2CB517A93F0`

Blender同梱版はバージョン `3.11.9`、サイズ61,568バイトであり、同梱しているバージョン `3.11.0`、
サイズ65,920バイトのファイルとは異なります。そのため「Blender 4.3.2 Windows Portable同梱由来」とは扱いません。

ライセンス：

- Python Software Foundation License

取得日は記録が残っていないため、不明とします。

## 開発・検証時に使用したが、現在の配布物には含まれないVRM

以下のVRMは、変換処理や互換性の検証に使用した記録です。

VRMファイル本体は、一般ユーザー向け配布ZIPおよび現在の公開リポジトリには含めません。

| ファイル | 出所 | ライセンス・利用条件 |
|---|---|---|
| `AliciaSolid_vrm-0.51.vrm` | https://github.com/vrm-c/UniVRM の `Tests/Models` | ニコニ立体ちゃん利用規約：https://3d.nicovideo.jp/alicia/rule.html |
| `Seed-san.vrm` | https://github.com/vrm-c/vrm-specification のsamples | VRM Public License 1.0。著作者：VirtualCast, Inc. |
| `VitaVRM1.0.vrm` | VRoid Hub「歴代サンプルモデル」https://hub.vroid.com/en/characters/4593660874193246717/models/7942721847119018516 | VRoid Hub掲載条件およびVRM埋め込みメタデータ上で、再配布・改変・商用利用を許可 |
| `collected/100Avatars_*.vrm` | Polygonal Mindの「100 Avatars」系公開サンプルモデル群 | VRM埋め込みメタデータ上でCC0 |

### Seed-san

2026-07-31に、VRMファイル内の `extensions.VRMC_vrm.meta` を確認しました。

確認した主な値：

- `avatarPermission: everyone`
- `allowRedistribution: true`
- `modification: allowModificationRedistribution`
- `commercialUsage: corporation`
- `creditNotation: required`

クレジット表記が必要です。

テスト用ファイルそのものは配布しません。

### VitaVRM1.0

取得元：

- https://hub.vroid.com/en/characters/4593660874193246717/models/7942721847119018516

β版VRoid Studioで配布されていたサンプルモデルをVRM 1.0化したものとして公開されています。

アップロード者：

- Coatie（Koh-Tee）

2026-07-31に、VRoid Hub掲載の利用条件およびVRMファイル内の `extensions.VRMC_vrm.meta` を確認しました。

確認した主な値：

- `avatarPermission: everyone`
- `allowRedistribution: true`
- `modification: allowModificationRedistribution`
- `creditNotation: unnecessary`

VRMファイル内のauthors：

- `pixiv inc.`
- `coati`

テスト用ファイルそのものは配布しません。

### 100 Avatars

制作：

- Polygonal Mind
- https://www.polygonalmind.com/

2026-07-31に、VRMファイル内の `extensions.VRM.meta` を確認しました。

確認した主な値：

- `licenseName: CC0`
- `allowedUserName: Everyone`
- `commercialUssageName: Allow`
- `violentUssageName: Allow`
- `sexualUssageName: Allow`

テスト用ファイルそのものは配布しません。

### テスト画像について

これらのVRM本体および変換結果画像は、一般ユーザー向け配布ZIPには含めません。

公開リポジトリへテスト画像等を追加する場合は、各素材のライセンス、クレジット表記、再配布条件を個別に確認します。

## 過去の開発環境で使用したShapell

`Shapell_v1_0_3.zip` は、過去の開発・テスト時に使用した記録がありますが、取得元URLを確認できていません。

2026-07-26に、ZIP内の `Shapell/LICENSE.txt` で以下の記載を確認しました。

- `CC0 1.0 Universal`
- `Public Domain Dedication`
- https://creativecommons.org/publicdomain/zero/1.0/deed.ja

ただし、Shapellに同梱されていた3Dシェーダー「arktoon shader」には、Shapell本体のCC0とは別のライセンスが適用されます。

Shapell側のライセンス文書にも、シェーダーについてはシェーダー独自のライセンスに従う旨が記載されています。

arktoon shader自体のライセンス本文は未確認です。

現在の一般ユーザー向け配布ZIPおよび公開リポジトリには、以下を含めません。

- Shapell
- arktoon shader
- 関連するシェーダーコード
- 関連するテスト素材

## 初回セットアップ時に自動取得するもの

### Blender 4.3.2 Windows Portable

取得元：

- https://www.blender.org/download/

ライセンス：

- GNU General Public License

配布ZIPへの同梱：

- なし

Blender本体は、一般ユーザー向け配布ZIPには同梱しません。

初回セットアップ時に、以下のスクリプトがBlender公式配布物を自動的にダウンロードして配置します。

- `pipeline/cli/ensure_blender.ps1`

ダウンロードURLおよびSHA-256の照合値は、同スクリプト内に記録されています。

ユーザーが手動でBlenderを取得・配置する必要はありません。

Blender公式配布物に含まれるPythonおよび各種第三者ライブラリには、それぞれのライセンスが適用されます。

## Unreal Engineについて

現在の変換パイプラインは、UE非依存のnoue方式のみを使用します。

従来のUnreal Engine経由モードは削除されています。

削除された旧モード：

- `-EngineMode ue`

そのため、一般ユーザーがUchinokoを使用するためにUnreal Engine 5.1を取得・インストールする必要はありません。

`pipeline/py/noue_master/` 内のUnreal Engine形式アセットの由来と検証方法については、以下を参照してください。

- `PROVENANCE_NOUE_ASSETS.md`

## まとめ

一般ユーザー向け配布ZIPに同梱する主な第三者コンポーネントは、以下です。

- VRM Add-on for Blender 4.4.0
- pyooz 0.0.8由来の `ooz.pyd`
- pyooz 0.0.8の対応ソース
- CPython由来の `python3.dll`

開発・テスト用のVRM、Shapell、arktoon shader、テスト画像は、一般ユーザー向け配布ZIPには含めません。

第三者コンポーネントのライセンスと通知については、以下も参照してください。

- `THIRD_PARTY_LICENSES.txt`
- `THIRD_PARTY_NOTICES.md`
- `PROVENANCE_NOUE_ASSETS.md`
