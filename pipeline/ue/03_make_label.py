# -*- coding: utf-8 -*-
"""UE内Python(4本目): クック対象を束ねるPrimaryAssetLabelを作成する
(Priority=1, Chunk ID=900, Always Cook, 配下ラベリング)。"""

import unreal

LABEL_DIR = "/Game/Pal"
LABEL_NAME = "Label_DiveToPalworld"

path = f"{LABEL_DIR}/{LABEL_NAME}"
if unreal.EditorAssetLibrary.does_asset_exist(path):
    label = unreal.EditorAssetLibrary.load_asset(path)
else:
    label = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        LABEL_NAME, LABEL_DIR, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())

# UE5.1 Python: 構造体は set_editor_property 経由(属性直アクセス不可)
rules = unreal.PrimaryAssetRules()
rules.set_editor_property("priority", 1)
rules.set_editor_property("chunk_id", 900)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", True)
unreal.EditorAssetLibrary.save_asset(path)
unreal.log(f"[03_make_label] done: {path} (chunk 900)")
