# Outfit個別選択 改修報告

## 調査結果

- UE不要経路の実注入対象は `build_pak_from_avatar.py` がライブテンプレートの
  `Player/Outfit` 以下から列挙し、`vp_exclusions.py` のコラボ除外を適用したSKです。
- `noue_template_manifest.json` のOutfit SKは62件、コラボ除外後の選択可能対象は58件です。
- 従来の最終PAK生成はテンプレート全体を収録し、注入済みSKだけを差し替えていました。
  このため注入だけをスキップしても未選択SKがPAKへ残る構造でした。
- Outfit SKのMaterials参照は `live_template.py` がOutfit別MIへ統一し、そのMIを
  VRM共通テクスチャ`t00`へ向けます。部分選択時は、選択SKが実際に参照するMIだけを
  収録します。選択・未選択SK間で同一MI参照が検出された場合は、副作用を避けて停止します。
- `fast_repack.py`にはフル変換時の`job_snapshot.json`との設定差分ゲートが既にあり、
  `selected_outfits`は影だけの許可キーではないため、防具変更時は再利用されません。
- UE経由経路はOutfit一括Cookを前提としているため、部分選択を無視せず明示エラーで停止します。

## 実装

- こだわり設定に「防具を選択...」と`選択中 n / 58`を追加。
- 検索、すべて選択、すべて解除、スクロール、OK/キャンセル、キーボード操作対応。
- 選択IDは拡張子なし・`/`区切りのPAK相対アセットパスとして`job.json`へ保存。
- `selected_outfits`が無い旧ジョブは全選択。不明IDは無視。新規ジョブは全58件選択。
- 0件はGUIと変換処理の両方で拒否。
- 全選択は従来の最終ファイル集合を変更しない。
- 部分選択は選択SKの`.uasset/.uexp`と、そのSKが参照する書換済みMIだけを収録。
- preflightに選択SKの完全一致、未選択SK不在、`.uasset/.uexp`ペア検査を追加。
- 防具選択変更後は「影のみ更新」を無効化し、フル変換が必要な旨を表示。
- 既存`output_scale`のGUI、保存・復元、注入処理への引き渡しを維持。

## 変更ファイル

- `app/DiveToPalworld.cs`
- `pipeline/cli/convert.ps1`
- `pipeline/py/build_pak_from_avatar.py`
- `pipeline/py/fast_repack.py`
- `pipeline/py/preflight_pak.py`
- `pipeline/py/outfit_selection.py`（新規）
- `tests/test_outfit_selection.py`（新規）
- `OUTFIT_SELECTION_REPORT.md`（本書）

## テスト結果

- Python構文検査: PASS
- 選択ロジック5ケース: PASS
  - manifest由来58件とコラボ除外
  - 旧ジョブ全選択
  - 不明ID無視
  - 0件拒否
  - `_v02`単独、1件、複数不規則、全選択のPAKファイル絞り込み
- .NET Framework 4.8 GUIビルド: PASS
- GUI起動スモーク: PASS
- `output_scale`保存・復元・変換引き渡し配線: ソース検査PASS

## 未検証

この環境にはPalworld本体PAK、テスト用VRM、Blender実行環境が無いため、
実データを使うフル変換、実PAKの生成、プレビュー、影のみ更新、ゲーム内表示、
MOD適用・解除は実行していません。最終PAKに対する選択完全一致とバイナリペア検査は
`preflight_pak.py`へ実装済みですが、実データでの通過確認は必要です。

