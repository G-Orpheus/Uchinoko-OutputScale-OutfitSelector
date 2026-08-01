# -*- coding: utf-8 -*-
"""UE内Python(2本目): FBX・テクスチャのインポート、マテリアル生成・割当、
ダミーHead/Hairの配置。Male/Female両対応。

マテリアル方針(スペック準拠):
  - マット化Lit(デフォルト): Roughness=1 / Specular=0 固定。プラスチック的な
    スペキュラを排除しつつ環境ライティングは反映する
  - アンリット(オプション): Emissiveへ直結。暗所で自キャラのみフルブライトになる
  - used_with_skeletal_mesh=True 明示必須(無いとシップビルドでチェッカー化)
"""

import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_ue as C
import vp_ue_mat as M

ASSET_TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary


def import_fbx(fbx_path, dest_dir, skeleton=None):
    opts = unreal.FbxImportUI()
    opts.import_mesh = True
    opts.import_as_skeletal = True
    opts.import_materials = False
    opts.import_textures = False
    opts.import_animations = False
    opts.create_physics_asset = skeleton is None
    if skeleton is not None:
        opts.skeleton = skeleton
    opts.skeletal_mesh_import_data.set_editor_property("import_morph_targets", False)
    opts.skeletal_mesh_import_data.set_editor_property("convert_scene", True)

    task = unreal.AssetImportTask()
    task.filename = fbx_path
    task.destination_path = dest_dir
    task.automated = True
    task.save = True
    task.options = opts
    ASSET_TOOLS.import_asset_tasks([task])
    unreal.log(f"imported: {list(task.imported_object_paths)}")


def find_asset(dest_dir, cls):
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    for ad in ar.get_assets_by_path(dest_dir, recursive=False):
        obj = ad.get_asset()
        if isinstance(obj, cls):
            return obj
    return None


def rename_asset(obj, new_dir, new_name):
    old_path = obj.get_path_name().split(".")[0]
    new_path = f"{new_dir}/{new_name}"
    if old_path == new_path:
        return obj
    if not EAL.rename_asset(old_path, new_path):
        unreal.log_error(f"rename failed: {old_path} -> {new_path}")
        return obj
    unreal.log(f"renamed: {old_path} -> {new_path}")
    return EAL.load_asset(new_path)


# マテリアル生成・割当は vp_ue_mat に共通化(08マテリアルのみ更新と共用)
import_textures = lambda: M.import_textures(C)  # noqa: E731
make_material = lambda slot, info, tex: M.make_material(C, slot, info, tex)  # noqa: E731
assign_materials = M.assign_materials


def main():
    skel = None
    sks = {}
    for i, g in enumerate(C.GENDERS):
        import_fbx(C.FBX[g], C.DIR_OUTFIT[g],
                   skeleton=skel if i > 0 else None)
        sk = find_asset(C.DIR_OUTFIT[g], unreal.SkeletalMesh)
        if sk is None:
            unreal.log_error(f"{g}のSkeletalMeshが見つからない")
            raise SystemExit(1)
        sks[g] = rename_asset(sk, C.DIR_OUTFIT[g], C.NAME_SK[g])
        if i == 0:
            skel = find_asset(C.DIR_OUTFIT[g], unreal.Skeleton)
            if skel is not None:
                skel = rename_asset(skel, C.DIR_SKELETON, C.NAME_SKELETON)
            phys = find_asset(C.DIR_OUTFIT[g], unreal.PhysicsAsset)
            if phys is not None:
                rename_asset(phys, C.DIR_PHYSICS, C.NAME_PHYSICS)

    # 物理アセット参照を両性別の衣装SKへ明示付与(2026-07-22):
    # バニラ衣装SKは SK_Player_Female_PhysicsAsset(1本のみ、パスはBody/Female)を
    # 参照しており、服揺れボーン(OldCloth001_*)はこれ経由で駆動される。
    # 従来はMale(初回インポートの自動生成分)にしか参照が付かず、
    # Female衣装は実機で揺れなかった(ぱん検査で判明)。実体はpak非同梱で
    # バニラ解決(G3が除去)
    phys_path = f"{C.DIR_PHYSICS}/{C.NAME_PHYSICS}"
    phys_obj = EAL.load_asset(phys_path)
    if phys_obj is None:
        unreal.log_error(f"PhysicsAssetが無い: {phys_path}")
    else:
        for g, sk in sks.items():
            sk.set_editor_property("physics_asset", phys_obj)
            EAL.save_loaded_asset(sk)
            unreal.log(f"physics asset assigned: {g} -> {phys_path}")

    textures = import_textures()
    mats = {}
    for slot, info in C.SLOTS.items():
        tex = textures.get(info["texture"]) if info["texture"] else None
        mats[slot] = make_material(slot, info, tex)
    for sk in sks.values():
        assign_materials(sk, mats)

    # ダミーHead/Hair(スケルトンを合わせてインポート→両性別のHead001+Hair001へ)
    if skel is None:
        unreal.log_error("スケルトンが無い")
        raise SystemExit(1)
    import_fbx(C.FBX_DUMMY, C.DIR_HEAD, skeleton=skel)
    head = find_asset(C.DIR_HEAD, unreal.SkeletalMesh)
    if head:
        head = rename_asset(head, C.DIR_HEAD, C.NAME_HEAD[C.GENDERS[0]])
        for g in C.GENDERS[1:]:
            dest = f"{C.DIR_HEAD}/{C.NAME_HEAD[g]}"
            if not EAL.does_asset_exist(dest):
                EAL.duplicate_asset(head.get_path_name().split(".")[0], dest)
                EAL.save_asset(dest)
                unreal.log(f"dummy head duplicated: {dest}")
    hair_src = C.FBX_HAIRSWAY if C.HAIR_SWAY else C.FBX_DUMMY
    import_fbx(hair_src, C.DIR_HAIR, skeleton=skel)
    hair = find_asset(C.DIR_HAIR, unreal.SkeletalMesh)
    if hair:
        hair = rename_asset(hair, C.DIR_HAIR, C.NAME_HAIR)
        if C.HAIR_SWAY:
            assign_materials(hair, mats)
            unreal.log("hair: 揺れ髪メッシュ(HairSway.fbx)を使用")

    # 頭装備(兜)ダミー: これを複製元に02が全HeadEquipへ展開する。
    # 各装備の専用Skeleton/Physicsはpakに入れずバニラ解決させる
    import_fbx(C.FBX_DUMMY, C.DIR_HEADEQUIP, skeleton=skel)
    he = find_asset(C.DIR_HEADEQUIP, unreal.SkeletalMesh)
    if he:
        rename_asset(he, C.DIR_HEADEQUIP, C.NAME_HEADEQUIP)

    unreal.log("[01_import_and_setup] done")


main()
