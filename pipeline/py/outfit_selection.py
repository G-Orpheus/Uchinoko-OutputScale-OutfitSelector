# -*- coding: utf-8 -*-
"""Outfit individual-selection contract shared by packing and preflight.

The catalog is derived from noue_template_manifest.json using the same SK and
collaboration exclusions as the injector.  IDs are extension-less pak-relative
asset paths.  A missing selected_outfits key means all (legacy compatibility);
unknown IDs are ignored, so catalog additions automatically default to selected
only for old jobs that do not contain the key.
"""
import json
import os

import vp_exclusions

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "noue_template_manifest.json")


def normalize_id(value):
    value = str(value or "").replace("\\", "/").strip()
    for ext in (".uasset", ".uexp"):
        if value.lower().endswith(ext):
            value = value[:-len(ext)]
    return value.strip("/")


def catalog(manifest_path=MANIFEST):
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    result = []
    for rel in list(manifest.get("vanilla", [])) + list(manifest.get("project", [])):
        rel = rel.replace("\\", "/")
        if (rel.startswith("Player/Outfit/") and rel.endswith(".uasset")
                and os.path.basename(rel).startswith("SK_")
                and not vp_exclusions.is_excluded(rel)):
            result.append(normalize_id(rel))
    return sorted(set(result))


def selected(job, known=None, reject_empty=True):
    known = list(known if known is not None else catalog())
    if "selected_outfits" not in job:
        return set(known)
    requested = {normalize_id(v) for v in (job.get("selected_outfits") or [])}
    chosen = set(known).intersection(requested)
    if reject_empty and not chosen:
        raise ValueError("上書きする防具が0件です。1件以上選択してください。")
    return chosen


def display_name(asset_id):
    name = os.path.basename(normalize_id(asset_id))
    gender = "Male" if "_Male_" in name else "Female" if "_Female_" in name else "?"
    marker = "_Outfit_"
    short = name.split(marker, 1)[1] if marker in name else name
    return f"{gender} / {short}"


def _mi_ids_for(template_dir, asset_ids):
    """Return the Outfit MI packages referenced by selected SK assets."""
    import live_template
    prefix = "/Game/Pal/Model/Character/"
    result = set()
    for asset_id in asset_ids:
        ua = os.path.join(template_dir, *asset_id.split("/")) + ".uasset"
        ue = ua[:-7] + ".uexp"
        if not (os.path.exists(ua) and os.path.exists(ue)):
            continue
        for package in live_template.find_outfit_material_paths_all(ua, ue):
            if package.startswith(prefix):
                result.add(normalize_id(package[len(prefix):]))
    return result


def required_mi_ids(template_dir, selected_ids):
    """Return selected MI packages and reject unsafe selected/unselected sharing."""
    selected_ids = set(selected_ids)
    chosen = _mi_ids_for(template_dir, selected_ids)
    unselected = set(catalog()) - selected_ids
    shared = chosen.intersection(_mi_ids_for(template_dir, unselected))
    if shared:
        raise RuntimeError(
            "選択中と未選択の防具が同じMaterial Instanceを共有しています。"
            "未選択防具への副作用を防ぐため変換を停止しました: "
            + ", ".join(sorted(shared)[:3]))
    return chosen


def filter_pak_files(files, template_dir, selected_ids, known=None,
                     private_materials=False):
    """Keep selected SK pairs and only their rewritten Outfit MI dependencies.

    With all supported catalog entries selected, non-SK assets remain an exact
    no-op but unsupported/template-only Outfit SK pairs are still removed.
    For a subset, other Outfit assets are omitted so vanilla SKs cannot be
    affected by a globally overridden MI or texture.
    """
    known = set(known if known is not None else catalog())
    selected_ids = set(selected_ids)
    files = list(files)
    if private_materials:
        # Private MI/Texture packages make original Outfit material assets
        # unnecessary. Keeping one would recreate a cross-PAK global override.
        result = []
        for src, rel in files:
            normalized_rel = rel.replace("\\", "/")
            if not normalized_rel.startswith("Player/Outfit/"):
                result.append((src, rel))
            elif (os.path.basename(normalized_rel).startswith("SK_")
                  and normalize_id(normalized_rel) in selected_ids):
                result.append((src, rel))
        return result
    if selected_ids == known:
        # The noue template intentionally still contains four collaboration
        # meshes in vanilla form.  They are not injection targets and must not
        # leak into the final pak merely because every *supported* outfit was
        # selected.  Preserve all other template assets byte-for-byte.
        result = []
        for src, rel in files:
            normalized_rel = rel.replace("\\", "/")
            if (normalized_rel.startswith("Player/Outfit/")
                    and os.path.basename(normalized_rel).startswith("SK_")
                    and normalize_id(normalized_rel) not in selected_ids):
                continue
            result.append((src, rel))
        return result
    required_mi = required_mi_ids(template_dir, selected_ids)
    result = []
    for src, rel in files:
        normalized_rel = rel.replace("\\", "/")
        rel_id = normalize_id(normalized_rel)
        if not normalized_rel.startswith("Player/Outfit/"):
            result.append((src, rel))
        elif os.path.basename(normalized_rel).startswith("SK_"):
            if rel_id in selected_ids:
                result.append((src, rel))
        elif os.path.basename(normalized_rel).startswith("MI_"):
            if rel_id in required_mi:
                result.append((src, rel))
        # Outfit textures and unrelated helper assets are intentionally omitted.
        # Referenced vanilla dependencies remain available from the base game.
    return result
