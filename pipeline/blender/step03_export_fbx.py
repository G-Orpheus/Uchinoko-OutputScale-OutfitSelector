# -*- coding: utf-8 -*-
"""Step03: UE取り込み用FBXをエクスポートする(性別ごと)。

実行: blender --background --factory-startup --python-exit-code 1 --python step03_export_fbx.py -- <job.json> <Male|Female>
入力: converted/step02_{gender}.blend
出力: converted/Avatar_{gender}.fbx
"""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_bl
from vp_bl import core

TAG = "step03"


def remove_hair_bones():
    """hair_*ボーンを削除する(本体FBX用。バインドを共通65本に保ちG5bを守る)。"""
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    doomed = [b for b in arm.data.edit_bones if b.name.startswith("hair_")]
    n = len(doomed)
    for b in doomed:
        arm.data.edit_bones.remove(b)
    bpy.ops.object.mode_set(mode="OBJECT")
    if n:
        print(f"[{TAG}] hair bones removed for body export: {n}")


def export_fbx(filepath, output_scale=1.0):
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    # cm系で作業しているため基準Scale=0.01。output_scaleはユーザー指定の最終倍率。
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=True,
        global_scale=0.01 * output_scale,
        apply_scale_options="FBX_SCALE_NONE",
        add_leaf_bones=False,
        armature_nodetype="NULL",
        bake_anim=False,
        mesh_smooth_type="FACE",
        use_tspace=True,
        path_mode="COPY",
        embed_textures=False,
    )
    print(f"[{TAG}] exported: {filepath} ({len(meshes)} meshes, output_scale={output_scale})")


def main():
    job, rest = vp_bl.load_job_from_argv()
    gender = rest[0] if rest else "Male"
    conv = core.job_subdir(job, "converted")
    output_scale = float(job.get("output_scale", 1.0))
    if not (0.01 <= output_scale <= 100.0):
        core.die(TAG, f"output_scaleは0.01〜100.0で指定してください: {output_scale}")
    blend = os.path.join(conv, f"step02_{gender.lower()}.blend")
    if not os.path.exists(blend):
        core.die(TAG, f"step02の出力が無い: {blend}")

    # 1) 本体: HairSwayとhair_*ボーンを除いて出力(衣装スロット用)
    bpy.ops.wm.open_mainfile(filepath=blend)
    hair_exists = "HairSway" in bpy.data.objects
    if hair_exists:
        bpy.data.objects.remove(bpy.data.objects["HairSway"], do_unlink=True)
    remove_hair_bones()
    export_fbx(os.path.join(conv, f"Avatar_{gender}.fbx"), output_scale)

    # 2) 揺れ髪(Hairスロットは男女共用なのでMale側だけ出力)
    if gender == "Male":
        out_hair = os.path.join(conv, "HairSway.fbx")
        if hair_exists:
            bpy.ops.wm.open_mainfile(filepath=blend)
            for o in [o for o in bpy.data.objects
                      if o.type == "MESH" and o.name != "HairSway"]:
                bpy.data.objects.remove(o, do_unlink=True)
            export_fbx(out_hair, output_scale)
        elif os.path.exists(out_hair):
            os.remove(out_hair)  # 揺れ髪無効時の残骸で誤インポートしない


main()
