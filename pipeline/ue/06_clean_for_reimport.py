# -*- coding: utf-8 -*-
"""UE内Python(再実行前の掃除): 既存の生成アセットを削除する。
二重化・古いアセット掴み事故の防止。chunk901隔離ラベルは温存する。"""

import csv
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_ue as C

EAL = unreal.EditorAssetLibrary

# 削除順が重要: 依存する側(複製ティア)→ 基点SK/Head/Hair → マテリアルの順。
# マテリアルを先に消すと、残存する複製衣装のロードが走りVerifyImportエラーの嵐
# +削除不全になる(Seed-san初回ビルドで実害確認)
DIRS = []
for csv_path in C.CSV.values():
    if not os.path.exists(csv_path):
        continue
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        DIRS.extend(sorted({row["Folder"].strip() for row in csv.DictReader(f)}))
DIRS += [C.DIR_OUTFIT["Male"], C.DIR_OUTFIT["Female"],
         C.DIR_HEAD, C.DIR_HAIR, C.DIR_HEADEQUIP, C.DIR_MATERIALS]

for d in DIRS:
    if EAL.does_directory_exist(d):
        if EAL.delete_directory(d):
            unreal.log(f"[06_clean] deleted dir: {d}")
        else:
            unreal.log_error(f"[06_clean] delete failed: {d}")

# 親ディレクトリにchunk901隔離ラベルが同居するためアセット単体で消す
ASSETS = [
    f"{C.DIR_SKELETON}/{C.NAME_SKELETON}",
    f"{C.DIR_PHYSICS}/{C.NAME_PHYSICS}",
]
for a in ASSETS:
    if EAL.does_asset_exist(a):
        if EAL.delete_asset(a):
            unreal.log(f"[06_clean] deleted asset: {a}")
        else:
            unreal.log_error(f"[06_clean] delete failed: {a}")

unreal.log("[06_clean_for_reimport] done")
