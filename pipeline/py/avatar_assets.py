# -*- coding: utf-8 -*-
"""Avatar-private Material Instance/Texture packages for multi-PAK use.

Each generated Outfit SK keeps its existing MaterialImport FPackageIndex and
preload dependency entry, but the referenced Package/Object names are changed
to one avatar-private MI.  No vanilla MI or MainShader texture is overridden.
"""
import hashlib
import os
import re
import struct

import live_template as lt
import vp_matparam


GAME_PREFIX = "/Game/Pal/Model/Character/"


class AvatarAssetError(RuntimeError):
    pass


def namespace_for_job(job):
    """Return an ASCII UE package component stable for this saved avatar job."""
    avatar = str(job.get("avatar_name") or "avatar").strip()
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", avatar).strip("_").lower()
    if not slug:
        slug = "avatar"
    slug = slug[:32]
    # The persisted VRM path distinguishes same-named avatars while remaining
    # stable for full conversion and fast repack even if the file is offline.
    seed = avatar + "\0" + str(job.get("vrm_path") or "")
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{slug}_{digest}"


def package_paths(job):
    ns = namespace_for_job(job)
    root = f"{GAME_PREFIX}Uchinoko/{ns}"
    return {
        "namespace": ns,
        "root": root,
        "mi": root + "/Materials/MI_Body",
        "base": root + "/Textures/T_Base",
        "normal": root + "/Textures/T_Normal",
        "orm": root + "/Textures/T_ORM",
    }


def _read_tables(uasset_bytes):
    h = lt._parse_header_with_offsets(uasset_bytes)
    names, names_end = lt._read_name_table(
        uasset_bytes, h.name_offset, h.name_count)
    if names_end != h.import_offset:
        raise AvatarAssetError(
            f"name table終端({names_end}) != import_offset({h.import_offset})")
    imports = []
    off = h.import_offset
    for _ in range(h.import_count):
        imp, off = lt._parse_import(uasset_bytes, off)
        imports.append(imp)
    if off != h.export_offset:
        raise AvatarAssetError(
            f"import table終端({off}) != export_offset({h.export_offset})")
    return h, names, imports


def _full_import_path(names, imports, fpi):
    imp = imports[-fpi - 1]
    outer = imp["outer_index"]
    if outer >= 0:
        raise AvatarAssetError(f"Material importのouterがPackage importでない: {outer}")
    return names[imports[-outer - 1]["object_name_idx"]]


def patch_outfit_sk_materials(uasset_path, uexp_path, target_mi_path):
    """Repoint every material slot in one generated SK to target_mi_path.

    Existing import indices and preload dependencies are retained.  Only new
    NameMap strings and the ObjectName indices of existing Package/MIC imports
    are changed, avoiding the failed historical new-import approach.
    """
    with open(uasset_path, "rb") as f:
        data = f.read()
    with open(uexp_path, "rb") as f:
        uexp = f.read()
    h, names, imports = _read_tables(data)

    material_fpis = {}
    for i, imp in enumerate(imports):
        ci = imp["class_name_idx"]
        cn = names[ci] if 0 <= ci < len(names) else None
        if cn in lt._MATERIAL_CLASS_NAMES:
            material_fpis[-(i + 1)] = i
    if not material_fpis:
        raise AvatarAssetError(f"Material importが無い: {uasset_path}")

    structure = lt.sks.parse_sk_structure(uexp_path, uasset_path)
    hits = lt._find_material_slot_offsets(
        bytearray(uexp), material_fpis,
        structure["render_sections_count_offset"])
    if len(hits) != len(material_fpis):
        raise AvatarAssetError(
            f"スロット出現数({len(hits)}) != Material import数({len(material_fpis)})")
    hits.sort(key=lambda x: x[0])
    target_import_indices = sorted({-fpi - 1 for _off, fpi in hits})
    original_paths = [_full_import_path(names, imports, -(i + 1))
                      for i in target_import_indices]

    target_short = target_mi_path.rsplit("/", 1)[-1]
    name_index = {name: i for i, name in enumerate(names)}
    new_names = []

    def resolve(name):
        if name in name_index:
            return name_index[name]
        if name not in new_names:
            new_names.append(name)
        return h.name_count + new_names.index(name)

    target_path_idx = resolve(target_mi_path)
    target_short_idx = resolve(target_short)
    name_insert = b"".join(lt._encode_name(name) for name in new_names)
    delta = len(name_insert)
    p1 = h.import_offset
    out = bytearray(data[:p1] + name_insert + data[p1:])

    package_indices = set()
    for material_i in target_import_indices:
        material_imp = imports[material_i]
        outer = material_imp["outer_index"]
        if outer >= 0:
            raise AvatarAssetError("Material importのouterが非import")
        package_i = -outer - 1
        if names[imports[package_i]["class_name_idx"]] != "Package":
            raise AvatarAssetError("Material importのouterがPackageでない")
        package_indices.add(package_i)
        struct.pack_into("<i", out,
                         material_imp["start"] + delta + 20,
                         target_short_idx)
    for package_i in package_indices:
        struct.pack_into("<i", out,
                         imports[package_i]["start"] + delta + 20,
                         target_path_idx)

    def p32(offset, value):
        struct.pack_into("<i", out, offset, value)

    def p64(offset, value):
        struct.pack_into("<q", out, offset, value)

    p32(h.total_header_size_off, len(out))
    p32(h.name_count_off, h.name_count + len(new_names))
    p32(h.soft_object_paths_offset_off, h.import_offset + delta)
    p32(h.import_offset_off, h.import_offset + delta)
    p32(h.export_offset_off, h.export_offset + delta)
    p32(h.depends_offset_off, h.depends_offset + delta)
    if h.soft_package_references_offset != 0:
        p32(h.soft_package_references_offset_off,
            h.soft_package_references_offset + delta)
    if h.searchable_names_offset != 0:
        p32(h.searchable_names_offset_off, h.searchable_names_offset + delta)
    if h.thumbnail_table_offset != 0:
        p32(h.thumbnail_table_offset_off, h.thumbnail_table_offset + delta)
    if h.asset_registry_data_offset != 0:
        p32(h.asset_registry_data_offset_off,
            h.asset_registry_data_offset + delta)
    p64(h.bulk_data_start_offset_off, h.bulk_data_start_offset + delta)
    if h.world_tile_info_data_offset != 0:
        p32(h.world_tile_info_data_offset_off,
            h.world_tile_info_data_offset + delta)
    if h.preload_dependency_offset != 0:
        p32(h.preload_dependency_offset_off,
            h.preload_dependency_offset + delta)
    if h.payload_toc_offset != -1:
        p64(h.payload_toc_offset_off, h.payload_toc_offset + delta)
    vp_matparam._patch_name_count_side_fields(
        out, h, h.name_count + len(new_names))

    export_off = h.export_offset + delta
    for _ in range(h.export_count):
        entry, export_off = lt.puh.parse_export_entry(out, export_off)
        serial_off = entry["serial_size_offset"] + 8
        old = struct.unpack_from("<q", out, serial_off)[0]
        struct.pack_into("<q", out, serial_off, old + delta)

    with open(uasset_path, "wb") as f:
        f.write(out)
    # uexp/FPackageIndex values are deliberately unchanged.
    return {"slots": len(hits), "original_paths": original_paths,
            "target": target_mi_path}


def _rel_from_game_path(path):
    if not path.startswith(GAME_PREFIX):
        raise AvatarAssetError(f"package path prefix mismatch: {path}")
    return path[len(GAME_PREFIX):]


def _write_clone(source_uasset, source_uexp, target_game_path, out_root):
    with open(source_uasset, "rb") as f:
        ua = f.read()
    with open(source_uexp, "rb") as f:
        ue = f.read()
    new_ua, new_ue = lt._clone_mvp_mic_as(ua, ue, target_game_path)
    rel = _rel_from_game_path(target_game_path)
    out = os.path.join(out_root, *rel.split("/"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".uasset", "wb") as f:
        f.write(new_ua)
    with open(out + ".uexp", "wb") as f:
        f.write(new_ue)
    return [(out + ".uasset", rel + ".uasset"),
            (out + ".uexp", rel + ".uexp")]


def build_private_assets(job, template_dir, selected_outfits, variant_dir,
                         injected_base_uexp, mi_override, out_root):
    """Patch selected SKs and build one private MI + Base/Normal/ORM textures."""
    paths = package_paths(job)
    if not injected_base_uexp or not os.path.exists(injected_base_uexp):
        raise AvatarAssetError("アバターBase Colorの注入済みt00.uexpが無い")
    os.makedirs(out_root, exist_ok=True)

    sk_reports = []
    source_mi_paths = []
    for asset_id in sorted(selected_outfits):
        ua = os.path.join(variant_dir, *asset_id.split("/")) + ".uasset"
        ue = ua[:-7] + ".uexp"
        if not (os.path.exists(ua) and os.path.exists(ue)):
            raise AvatarAssetError(f"注入済みOutfit SKが無い: {asset_id}")
        sk_reports.append(patch_outfit_sk_materials(ua, ue, paths["mi"]))
        source_ua = os.path.join(template_dir, *asset_id.split("/")) + ".uasset"
        source_ue = source_ua[:-7] + ".uexp"
        source_mi_paths.extend(
            lt.find_outfit_material_paths_all(source_ua, source_ue))
    if not source_mi_paths:
        raise AvatarAssetError("選択Outfitから複製元MIを特定できない")

    files = []
    t00_base = os.path.join(
        template_dir, "Player", "ModelMaterials", "MainShader", "t00")
    files += _write_clone(t00_base + ".uasset", injected_base_uexp,
                          paths["base"], out_root)
    for source_game_path, target in (
            (lt.NEUTRAL_NORMAL_GAME_PATH, paths["normal"]),
            (lt.NEUTRAL_ORM_GAME_PATH, paths["orm"])):
        source = os.path.join(
            template_dir, *_rel_from_game_path(source_game_path).split("/"))
        files += _write_clone(source + ".uasset", source + ".uexp",
                              target, out_root)

    # Prefer the per-job shadow-lift MI override.  If k=0, use the template's
    # already neutralized unified MI.  Both have the same parameter layout.
    source_game_mi = source_mi_paths[0]
    source_rel = _rel_from_game_path(source_game_mi)
    mi_ua = mi_override.get(source_rel + ".uasset")
    mi_ue = mi_override.get(source_rel + ".uexp")
    if not (mi_ua and mi_ue):
        source = os.path.join(template_dir, *source_rel.split("/"))
        mi_ua, mi_ue = source + ".uasset", source + ".uexp"
    if not (os.path.exists(mi_ua) and os.path.exists(mi_ue)):
        raise AvatarAssetError(f"複製元MIが無い: {source_game_mi}")

    patched_dir = os.path.join(out_root, "_mi_patch")
    os.makedirs(patched_dir, exist_ok=True)
    patched_ua = os.path.join(patched_dir, "MI_Body.uasset")
    patched_ue = os.path.join(patched_dir, "MI_Body.uexp")
    lt._patch_mi_base_texture(
        mi_ua, mi_ue, patched_ua, patched_ue,
        paths["base"], paths["base"].rsplit("/", 1)[-1],
        normal_full_path=paths["normal"],
        orm_full_path=paths["orm"])
    files += _write_clone(patched_ua, patched_ue, paths["mi"], out_root)

    # The temporary source package must never enter the PAK.
    for path in (patched_ua, patched_ue):
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        os.rmdir(patched_dir)
    except OSError:
        pass

    return files, {
        "namespace": paths["namespace"],
        "paths": paths,
        "selected_sk": len(sk_reports),
        "material_slots": sum(r["slots"] for r in sk_reports),
        "source_mi": source_game_mi,
    }
