# -*- coding: utf-8 -*-
"""UE内Python(高速パス): マテリアル(M_VP_*)だけを現在のジョブ設定で作り直す。
影の濃さ(shadow_lift)やアンリットの変更を、メッシュ再インポート無しで反映する。

前提: このプロジェクトで同じアバターのフル変換が一度完了していること
(プロジェクトはアバターごとに分離されているので、通常は自動的に満たされる)。
実行後は差分クック→再パック→preflightに進む(convert.ps1 -MaterialsOnly)。
"""

import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_ue as C
import vp_ue_mat as M

EAL = unreal.EditorAssetLibrary

# 前提チェック1: フル変換済みプロジェクトか(基点SKの存在)
sk_path = f"{C.DIR_OUTFIT['Male']}/{C.NAME_SK['Male']}"
if not EAL.does_asset_exist(sk_path):
    unreal.log_error("このプロジェクトにはまだアセットが無い — 先にフル変換が必要")
    raise SystemExit(1)

# 前提チェック2: プロジェクトの主が同じアバターか(状態ファイル照合)
state_file = os.path.join(
    unreal.SystemLibrary.get_project_directory(), "d2p_avatar.txt")
if os.path.exists(state_file):
    with open(state_file, encoding="utf-8") as f:
        owner = f.read().strip()
    if owner != C.AVATAR:
        unreal.log_error(
            f"プロジェクトの主({owner})と現在のアバター({C.AVATAR})が違う — "
            "先にフル変換が必要")
        raise SystemExit(1)

textures = M.import_textures(C)  # 既存アセットを再利用(新規importは走らない)
mats = {}
for slot, info in C.SLOTS.items():
    tex = textures.get(info["texture"]) if info["texture"] else None
    mats[slot] = M.make_material(C, slot, info, tex, replace=True)
unreal.log(f"[08_update_materials] {len(mats)} materials rebuilt "
           f"(unlit={C.UNLIT} shadow_lift={C.SHADOW_LIFT})")
unreal.log("===== MATERIALS_ONLY_DONE =====")
