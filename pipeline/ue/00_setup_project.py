# -*- coding: utf-8 -*-
"""UE内Python(1本目): フォルダ構造+スケルトン/素体のchunk901隔離ラベルを作る。
(隔離ラベル: 共有スケルトンをpakchunk900に同梱させない。共有資産の置換は
全人型モデルを破壊する — PalMod検査①の実害で確認済みの絶対原則)"""

import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_ue as C

EAL = unreal.EditorAssetLibrary

DIRS = [C.DIR_OUTFIT["Male"], C.DIR_OUTFIT["Female"], C.DIR_SKELETON,
        C.DIR_PHYSICS, C.DIR_HEAD, C.DIR_HAIR, C.DIR_HEADEQUIP, C.DIR_MATERIALS]
for d in DIRS:
    if not EAL.does_directory_exist(d):
        EAL.make_directory(d)
        unreal.log(f"created: {d}")

EXCLUDES = [
    (f"{C.BASE}/Skeleton", "Label_ExcludeSkeleton"),
    (f"{C.BASE}/Player/Body", "Label_ExcludeBody"),
]
for dir_path, label_name in EXCLUDES:
    path = f"{dir_path}/{label_name}"
    if EAL.does_asset_exist(path):
        label = EAL.load_asset(path)
    else:
        label = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            label_name, dir_path, unreal.PrimaryAssetLabel,
            unreal.DataAssetFactory())
    rules = unreal.PrimaryAssetRules()
    rules.set_editor_property("priority", 10)
    rules.set_editor_property("chunk_id", 901)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    EAL.save_asset(path)
    unreal.log(f"exclude label: {path} (chunk 901)")

unreal.log("[00_setup_project] done")
