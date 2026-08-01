# THIRD_PARTY_NOTICES

本ツールは、[pandrabox/Uchinoko](https://github.com/pandrabox/Uchinoko) を基にした非公式改変版です。

Uchinoko本体のコードはMIT Licenseで提供されています。詳細は同梱の [LICENSE](LICENSE) を参照してください。

この文書では、一般ユーザー向け配布ZIPに含まれる第三者コンポーネントと、そのライセンス・出所を記載します。

より詳細な取得元、バージョン、ハッシュ値等については、以下も参照してください。

- `THIRD_PARTY_LICENSES.txt`
- `assets/third_party/SOURCES.md`
- `assets/third_party/pyooz-0.0.8-source/NOTICE.md`
- `PROVENANCE_NOUE_ASSETS.md`

## 配布構成について

本改変版は、ZIPのルート直下に `Uchinoko.exe` を配置するフラット構成です。

旧版で使用されていた、トップレベルのランチャーと `_internal/Uchinoko.exe` を併用する2段構成ではありません。

## pyooz / ooz

PalworldのPAKで使用される圧縮データを処理するため、pyooz由来のコンポーネントを使用しています。

### 同梱ファイル

- `pipeline/py/ooz_worker_gpl.py`
- `assets/blender_patch/ooz.pyd`
- `assets/third_party/pyooz-0.0.8-source/`

### バージョン

- pyooz 0.0.8

### ライセンス

- GPL-3.0-or-later

`pipeline/py/ooz_worker_gpl.py` はGPL-3.0-or-laterとして扱われる独立したワーカープログラムです。

Uchinoko本体からは別プロセスとして起動されます。

pyoozの対応ソースコードは、外部サイトだけに依存せず確認できるよう、以下へ同梱しています。

`assets/third_party/pyooz-0.0.8-source/`

取得元、SHA-256、バージョン確認、および同梱される追加コンポーネントについては、以下を参照してください。

`assets/third_party/pyooz-0.0.8-source/NOTICE.md`

pyoozのソースには、以下の第三者コードが含まれます。

- SIMDe：MIT License
- Hedley：CC0-1.0

詳細はpyooz同梱のNOTICEおよびライセンス文書を参照してください。

## VRM Add-on for Blender

VRMファイルの読み込みに、VRM Add-on for Blenderを使用しています。

### 同梱ファイル

`assets/third_party/VRM_Addon_for_Blender-Extension-4_4_0.zip`

### バージョン

- VRM Add-on for Blender 4.4.0

### ライセンス

- MIT License

### 取得元

- https://github.com/saturday06/VRM-Addon-for-Blender/releases/tag/v4.4.0

MITライセンス全文は、以下に同梱しています。

`assets/third_party/licenses/VRM_Addon_for_Blender_MIT.txt`

## Blender

Blender本体は、この配布ZIPには含まれていません。

初回セットアップ時に `pipeline/cli/ensure_blender.ps1` がBlender公式配布物をダウンロードし、ツールの作業領域へ配置します。

### 使用バージョン

- Blender 4.3.2

### ライセンス

- GNU General Public License

### 取得元

- https://www.blender.org/download/

ダウンロード対象はスクリプト内で指定され、取得後にSHA-256による照合が行われます。

Blender本体およびBlender公式配布物に元から含まれるライブラリは、それぞれのライセンスに従います。

## python3.dll

pyoozをBlender同梱Python環境で使用するため、`python3.dll` を同梱しています。

### 同梱場所

`assets/blender_patch/python3.dll`

### 由来

- CPython 3.11.0 Windows公式配布物由来
- 同梱ファイルのSHA-256: `4055D1B9E553B78C244143AB6B48151604003B39A9BF54879DEE9175455C1281`
- Blender 4.3.2 Windows Portable同梱版のSHA-256: `F01B4E426DE80B96BB2BCAD4682A0422F8FAF570661F1E156ACFA2CB517A93F0`

両者は一致しないため、本ツールに同梱する `python3.dll` をBlender 4.3.2同梱由来とは扱いません。

### ライセンス

- Python Software Foundation License

### 取得元

取得元および対応バージョンの詳細は、`assets/third_party/SOURCES.md` を参照してください。

## Blender同梱Pythonパッケージ

初回セットアップで取得されるBlender公式配布物には、Blender本体に加えて、Pythonおよび複数の第三者ライブラリが含まれます。

これらは本ツールが個別に選定・再配布するものではなく、Blender公式配布物の構成をそのまま利用します。

各コンポーネントには、それぞれのライセンスが適用されます。


## `pipeline/py/noue_master/` 内のUnreal Engine形式アセット

本ツールには、以下の場所に `.uasset`、`.uexp` などのUnreal Engine形式ファイルが含まれます。

`pipeline/py/noue_master/`

これらはPalworld本体から抽出したゲームデータをそのまま再配布するものではありません。

生成方法、出所および検証方針については、以下を参照してください。

`PROVENANCE_NOUE_ASSETS.md`

ファイル形式がPalworldの資産と同じであることだけを理由に、Palworld本体由来のデータであるとは限りません。

## Blender用スクリプトについて

以下のスクリプトは、Blenderの `--python` オプションを通じて実行され、Blenderが提供する `bpy` APIを利用します。

- `pipeline/blender/step01_import_vrm.py`
- `pipeline/blender/step02_retarget.py`

これらはBlenderを外部プロセスとして起動して使用する構成です。

Blender本体および `bpy` にはBlender側のライセンスが適用されます。

## 配布ZIPに含まれない開発・テスト用素材

開発または検証時に使用された可能性のあるサンプルVRM、テスト用アバター、視覚回帰テスト画像等は、一般ユーザー向け配布ZIPには含まれていません。

したがって、以下のような第三者アバターデータは本配布物には同梱されません。

- Shapell
- Kate
- Seed-san
- Vita
- その他の検証用VRM

開発時の取得記録が残されている場合でも、それは配布ZIPに当該モデルが含まれることを意味しません。

## ライセンス文書

配布物に含まれるライセンスおよび通知文書は、以下を参照してください。

- `LICENSE`
- `THIRD_PARTY_LICENSES.txt`
- `THIRD_PARTY_NOTICES.md`
- `PROVENANCE_NOUE_ASSETS.md`
- `assets/third_party/SOURCES.md`
- `assets/third_party/licenses/VRM_Addon_for_Blender_MIT.txt`
- `assets/third_party/pyooz-0.0.8-source/LICENSE`
- `assets/third_party/pyooz-0.0.8-source/NOTICE.md`

## 免責

各第三者コンポーネントの名称、著作権、商標およびライセンスは、それぞれの権利者に帰属します。

本ツールへの同梱または利用は、各権利者がこの非公式改変版を推奨、承認またはサポートしていることを意味しません。
