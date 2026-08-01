# -*- coding: utf-8 -*-
"""UE内Python(3本目): 本体/ダミーHead/ダミーHairを、実行時抽出した
複製リストCSVに従って全ティア・全性別へ複製する。"""

import csv
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_ue as C

JOBS = [
    (f"{C.DIR_OUTFIT['Male']}/{C.NAME_SK['Male']}", C.CSV["outfit_male"]),
    (f"{C.DIR_OUTFIT['Female']}/{C.NAME_SK['Female']}", C.CSV["outfit_female"]),
    (f"{C.DIR_HEAD}/{C.NAME_HEAD['Male']}", C.CSV["head_male"]),
    (f"{C.DIR_HEAD}/{C.NAME_HEAD['Female']}", C.CSV["head_female"]),
    (f"{C.DIR_HAIR}/{C.NAME_HAIR}", C.CSV["hair"]),
    (f"{C.DIR_HEADEQUIP}/{C.NAME_HEADEQUIP}", C.CSV["headequip"]),
]

failed = 0
for source_path, csv_path in JOBS:
    if not unreal.EditorAssetLibrary.does_asset_exist(source_path):
        unreal.log_error(f"複製元が無い: {source_path}")
        failed += 1
        continue
    ok = ng = 0
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            dest = f"{row['Folder'].strip()}/{row['Name'].strip()}"
            if unreal.EditorAssetLibrary.does_asset_exist(dest):
                continue
            if unreal.EditorAssetLibrary.duplicate_asset(source_path, dest):
                ok += 1
            else:
                ng += 1
                unreal.log_error(f"複製失敗: {dest}")
    unreal.log(f"[02_duplicate_tiers] {os.path.basename(source_path)}: ok={ok} ng={ng}")
    failed += ng
unreal.EditorAssetLibrary.save_directory("/Game/Pal", recursive=True)
if failed:
    raise SystemExit(1)
unreal.log("[02_duplicate_tiers] done")
