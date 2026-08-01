# Uchinoko v2.2.13 旧正常版ベース再統合報告

作業日: 2026-08-01

## 結論

`Uchinoko_for_Palworld_v2.0.0_full_multi-avatar-assets` に対応する
`Uchinoko-2.2.11` 改変ソースをベースに戻し、公式v2.2.13の更新を選択移植した。
公式v2.2.13ツリーをベースには使用していない。

旧版のretarget、Humanoid対応、global fit、pelvis、arm chain、ground snap、
chibi skeleton、bind pose、RefSkeleton、BoneMap、頂点位置、bone index、weight、
Blender→UE座標変換、逐次SK注入は維持した。

## 移植前分類

### A. Palworld互換性に必須

- `app/DiveToPalworld.cs` の最新Palworld互換性判定
- `pipeline/py/known_good_palworld.json`
- `pipeline/py/live_template.py`
- `pipeline/py/extract_vanilla.py` の内容ハッシュmanifest・最新PAK棚卸し
- `noue_template_manifest.json` は旧版と公式v2.2.13で同一だったため変更なし

### B. 配布・セキュリティ

- `build/make_dist.ps1` のflat配布（実行EXEは1件）
- `app/build_app.ps1` とAssemblyInfo
- `pipeline/cli/ensure_blender.ps1`
- `SECURITY.md`、PRIVACY日英、provenance、third-party notices
- 最新日本語・英語manual
- Update Nowボタンを表示しないGUI

### C. パス・文字コード・診断

- `pipeline/cli/convert.ps1` のUTF-8・診断パス処理
- `pipeline/py/dep_resolver.py` と `path_privacy.py`
- preflight標準出力・標準エラーのUTF-8固定
- `vp_core.sha256_file()`（live-templateキャッシュ識別専用）
- `dump_avatar_mesh.py` のNaN/Inf fail-fast検査だけを移植

NaN/Inf検査は異常値を検出して停止するだけで、頂点の削除、clamp、補正、
並べ替え、index変更、weight変更を行わない。

### D. ボーン・ウェイト・座標へ影響するため移植しなかった変更

- `step02_retarget.py` の未知vertex group一括削除
- `vp_bl.py` のv2.2.13版
- `build_avatar_variant.py` の `uniform_scale` と旧output_scale処理の置換
- `dump_avatar_mesh.py` の0 polygon skip、合成UV、tangent再集約
- RefSkeleton/BoneMap/parser群のv2.2.13版
- `vp_modnorm.py` のtargetなしArmature modifier削除
- `step03_export_fbx.py` のoutput_scale方式変更
- v2.2.13の性別別・並列dump／ProcessPool SK注入

### E. 今回不要

- 開発用release/WSB/CI/GitHub issue管理ツール
- `uniform_scale` 隠し設定
- legacy UEソースの移動・削除
- 性別限定PAK機能
- layer cache、probe cache、release telemetry

## 旧版から変更した実装ファイル

- `app/DiveToPalworld.cs`
- `app/AssemblyInfo.cs`
- `app/build_app.ps1`
- `build/make_dist.ps1`
- `pipeline/cli/convert.ps1`
- `pipeline/cli/ensure_blender.ps1`
- `pipeline/py/known_good_palworld.json`
- `pipeline/py/live_template.py`
- `pipeline/py/extract_vanilla.py`
- `pipeline/py/dep_resolver.py`
- `pipeline/py/path_privacy.py`
- `pipeline/py/vp_core.py`（`sha256_file`追加のみ）
- `pipeline/py/dump_avatar_mesh.py`（有限値検査のみ）
- `pipeline/py/preflight_pak.py`（UTF-8出力固定のみ）
- manual・security・privacy・notice・provenance文書

独自のOutfit選択、Alpha/Masked、Neutral Normal/ORM、アバター固有MI/Texture、
fast repack、preflight G0～G13は旧改変版から維持している。

## 骨格保護監査

次は旧正常版とSHA-256完全一致:

- `pipeline/blender/step02_retarget.py`
- `pipeline/blender/vp_bl.py`
- `pipeline/blender/validate_armature.py`
- `pipeline/py/build_avatar_variant.py`
- `pipeline/py/build_pak_from_avatar.py`
- `pipeline/py/convert_noue.py`
- `pipeline/py/patch_refskeleton.py`
- `pipeline/py/vp_meshrestore.py`
- `pipeline/py/stub_skeletal_mesh.py`
- `pipeline/py/parse_sk_full.py`
- `pipeline/py/parse_sk_structure.py`
- `pipeline/py/parse_uasset_header.py`

`dump_avatar_mesh.py` は有限値検査だけが差分であり、正常入力の出力JSONを変えない。
旧版の `output_scale` は頂点位置とchibi-fit後の骨格位置へ従来どおり一度ずつ適用される。

## テスト結果

- Python 57ファイル構文検査: PASS
- C# v2.2.13 build: PASS
- 独自機能テスト18件: PASS
- 非ASCII job/PowerShell 5.1テスト8件: PASS
- GUI内部チェック（i18n、Palworld互換、ApplyLanguage、Blender判定、配布channel、
  clipboard、progress relay、progress label）: PASS
- Outfitダイアログ（初期58件、全解除、全選択、検索、cancel）: PASS
- 最新実Palworld PAKからRefSkeleton抽出: male 73 / female 73 / common 65
- 最新実Palworld PAKからlive-template 447ファイル構築: PASS
- 全選択58 Outfit実PAK: preflight G0～G13すべてPASS
- 部分選択2 Outfit実PAK: preflight G0～G13すべてPASS
- G4: 全選択 `(58,52,37,64,1,3)`、部分選択 `(2,52,37,64,1,3)`
- 正式 `make_dist.ps1` flat配布: PASS

## 未検証

この作業環境とE:\Downloadsには利用可能なVRM入力が無かったため、旧版と再統合版で
同一の実VRMを最初から再変換する試験、step02 blendの実ファイル比較、ゲーム内の
待機・歩行・走行・ジャンプ・攻撃・ロール・騎乗・防具着脱は未確認。

既存の同一sample avatar PAK比較では、58/58 Outfitについてbone名、順序、親index、
RefSkeleton transform、vertex count、position buffer、skin-weight bufferが一致している。
今回の再統合版は、その旧正常版生成経路をソースハッシュ単位で維持した。

今回のクリーン配布先からのBlenderオンライン初回取得は、実行環境のネットワーク制限で
公式・ミラーともTLS接続前に遮断された。`ensure_blender.ps1` とblender_patch素材は、
前回公式Blender 4.3.2アーカイブを使って初回セットアップPASSしたv2.2.13配布版と
同一ハッシュである。ゲーム内確認と同様、この新ZIP自身でのオンライン再取得のみ未完。
