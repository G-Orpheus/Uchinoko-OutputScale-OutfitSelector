# -*- coding: utf-8 -*-
"""ヘッドレス実行用ランナー: 掃除→フォルダ→取込→NeverStream→複製→ラベル。
UnrealEditor-Cmd.exe <proj> -run=pythonscript -script=このファイル で呼ばれる。
ジョブは環境変数 D2P_JOB で受け取る(vp_ue.py参照)。"""

import os
import sys
import traceback

import unreal

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
SCRIPTS = [
    "06_clean_for_reimport.py",
    "00_setup_project.py",
    "01_import_and_setup.py",
    "07_never_stream_textures.py",
    "02_duplicate_tiers.py",
    "03_make_label.py",
]

for name in SCRIPTS:
    path = os.path.join(_HERE, name)
    unreal.log(f"===== RUN {path} =====")
    try:
        with open(path, encoding="utf-8") as f:
            code = f.read()
        exec(compile(code, path, "exec"), {"__name__": "__main__", "__file__": path})
        unreal.log(f"===== OK {path} =====")
    except Exception:
        unreal.log_error(f"===== FAILED {path} =====")
        unreal.log_error(traceback.format_exc())
        raise SystemExit(1)

# プロジェクトの主(アバター名)を記録 — 08マテリアルのみ更新の前提チェック用
try:
    sys_path = os.path.join(
        unreal.SystemLibrary.get_project_directory(), "d2p_avatar.txt")
    import vp_ue as _C
    with open(sys_path, "w", encoding="utf-8") as f:
        f.write(_C.AVATAR)
except Exception:
    pass

unreal.log("===== ALL_SCRIPTS_DONE =====")
