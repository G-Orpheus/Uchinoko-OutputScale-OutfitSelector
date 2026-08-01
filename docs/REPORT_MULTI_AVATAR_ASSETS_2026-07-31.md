# 複数VRM MOD向けMaterial / Texture固有化

## 実装

- ジョブの `avatar_name` と `vrm_path` から安定した固有namespaceを生成する。
- 各アバターについて、次の8ファイル（4つのUE package pair）を生成する。
  - `Uchinoko/<namespace>/Materials/MI_Body.{uasset,uexp}`
  - `Uchinoko/<namespace>/Textures/T_Base.{uasset,uexp}`
  - `Uchinoko/<namespace>/Textures/T_Normal.{uasset,uexp}`
  - `Uchinoko/<namespace>/Textures/T_ORM.{uasset,uexp}`
- 選択されたOutfit SKの既存Material importを、追加importを作らず固有MIへ再配線する。
- 固有MIのBase Color / Normal / ORM参照を、同じnamespaceの固有Textureへ再配線する。
- 親MaterialはPalworld本体の共通親を参照するだけで上書きしないため、Material本体の複製は不要。
- `Player/Outfit` 配下の元MI/Texture、`Player/ModelMaterials/MainShader` 配下の共通資産、素体MIを最終PAKへ収録しない。
- フル変換と「影のみ更新」の両方で同じ固有化処理を使用する。
- preflight G2/G4/G6/G11/G12/G13を固有資産構成へ対応させた。
- G5bは、同一の元Outfit SKにも存在する衣装固有装飾ボーンのみ許可し、変換後だけに出現する未知ボーンは引き続きFAILとする。

## 競合確認

kalne（Female Ancient001）とcamome（Male Ancient001_v02）の実バイナリから2つのPAKを生成した。

- Outfit SKのMaterial Interface: それぞれの固有MIのみを参照
- 固有MI: それぞれの固有Base / Normal / ORMのみを参照
- 2つのテストPAK間の資産パス重複: 0
- `Player/ModelMaterials/MainShader/t00`: 両PAKとも未収録
- ロード順依存: Material / Texture package pathが交差しないため構造上なし

通常の最終PAK同士では、既存仕様どおりHead / Hair / HeadEquip / Body補助資産など325パスが重複する。ただし、これらは今回のOutfit用Material / Textureではない。Outfit / Materials / Textures / MainShaderに該当する有害な重複は0件だった。

## テスト

- Python構文検査: PASS
- 既存設定・Alpha・Outfit選択・G4ポリシーテスト: 15件PASS
- namespace安定性・アバター間分離・private filter: PASS
- 実UEバイナリ1件: SK全2スロット、MIのBase / Normal / ORM再配線 PASS
- 実UEバイナリ2アバター/2防具: PAK資産パス重複0、両方の固有配線検査 PASS
- 全選択58件PAK: preflight G0～G13 全チェックPASS
  - G4実測/期待: `(58, 52, 37, 64, 1, 3)`
  - G11: 58 SK / 209 Material slotsを固有MIへ再配線
- 正式配布ZIPを別フォルダへ展開:
  - root/internal EXEあり
  - `assets/blender_patch` 6ファイルあり
  - `.tmp_ensure_blender_*` 0件
  - 配布版Pythonモジュール構文検査 PASS
  - GUI起動・防具選択ダイアログ操作スモーク PASS

## 未検証

Palworld実機上で2つのMODのロード順を逆転する確認は、この環境では未実施。PAK package pathと内部参照の分離、およびpreflightまでは実データで確認済み。

UE経由モードは従来どおり個別選択時に誤生成を避ける既存の制御範囲であり、今回の固有資産生成は既定のUE不要モードに実装した。
