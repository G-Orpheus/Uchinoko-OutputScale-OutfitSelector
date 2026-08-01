# -*- coding: utf-8 -*-
"""UE内Python(01の後): テクスチャを全てNeverStream化する。
ストリーミングミップ(.ubulk)は手詰めMOD pakから読めない定番トラブルのため、
全ミップを.uexpへ焼き込み .ubulk依存を断つ(PalMod実証)。"""

import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_ue as C

EAL = unreal.EditorAssetLibrary
ar = unreal.AssetRegistryHelpers.get_asset_registry()

count = 0
for ad in ar.get_assets_by_path(C.DIR_MATERIALS, recursive=True):
    obj = ad.get_asset()
    if isinstance(obj, unreal.Texture2D):
        obj.set_editor_property("never_stream", True)
        EAL.save_asset(obj.get_path_name().split(".")[0])
        count += 1

n_expected = len({s["texture"] for s in C.SLOTS.values() if s["texture"]})
if count < n_expected:
    unreal.log_error(f"[07_never_stream] テクスチャ数不足 {count}/{n_expected}")
    raise SystemExit(1)
unreal.log(f"[07_never_stream_textures] done ({count} textures)")
