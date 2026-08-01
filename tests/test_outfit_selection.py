import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "py"))
import outfit_selection as outfits


def test_catalog_is_manifest_driven_and_excludes_collaborations():
    ids = outfits.catalog()
    assert len(ids) == 58
    assert all(not x.endswith((".uasset", ".uexp")) for x in ids)
    assert not any("Yakushima" in x or "Octavia" in x for x in ids)


def test_legacy_job_selects_all_and_unknown_ids_are_ignored():
    ids = outfits.catalog()
    assert outfits.selected({}) == set(ids)
    assert outfits.selected({"selected_outfits": [ids[0], "Unknown/Thing"]}) == {ids[0]}


def test_empty_selection_is_rejected():
    try:
        outfits.selected({"selected_outfits": []})
    except ValueError as e:
        assert "0件" in str(e)
    else:
        raise AssertionError("empty selection must be rejected")


def test_normalization_and_v02_individual_selection():
    target = next(x for x in outfits.catalog() if x.endswith("Cloth001_v02"))
    assert outfits.selected({"selected_outfits": [target + ".uasset"]}) == {target}


def test_pak_filter_all_one_and_irregular(monkeypatch=None):
    ids = outfits.catalog()
    files = []
    for asset_id in ids[:4]:
        files.extend([("src", asset_id + ".uasset"), ("src", asset_id + ".uexp")])
    excluded_ids = [
        "Player/Outfit/SK_Player_Female_Outfit_Yakushima001/"
        "SK_Player_Female_Outfit_Yakushima001",
        "Player/Outfit/SK_Player_Male_Outfit_Octavia001/"
        "SK_Player_Male_Outfit_Octavia001_v01",
        "Player/Outfit/SK_Player_Male_Outfit_Octavia001/"
        "SK_Player_Male_Outfit_Octavia001_v02",
        "Player/Outfit/SK_Player_Male_Outfit_Yakushima001/"
        "SK_Player_Male_Outfit_Yakushima001",
    ]
    for asset_id in excluded_ids:
        files.extend([("src", asset_id + ".uasset"),
                      ("src", asset_id + ".uexp")])
    files += [("src", "Player/Outfit/X/MI_A.uasset"),
              ("src", "Player/Outfit/X/MI_A.uexp"),
              ("src", "Player/ModelMaterials/MainShader/t00.uasset")]
    # Full supported selection preserves every non-SK asset, but removes both
    # halves of unsupported collaboration SKs left in the template.
    full = outfits.filter_pak_files(files, ".", set(ids), ids)
    full_rels = {r for _s, r in full}
    for asset_id in excluded_ids:
        assert asset_id + ".uasset" not in full_rels
        assert asset_id + ".uexp" not in full_rels
    assert "Player/Outfit/X/MI_A.uasset" in full_rels
    assert "Player/Outfit/X/MI_A.uexp" in full_rels
    assert "Player/ModelMaterials/MainShader/t00.uasset" in full_rels
    original = outfits.required_mi_ids
    outfits.required_mi_ids = lambda _root, _selected: {"Player/Outfit/X/MI_A"}
    try:
        one = outfits.filter_pak_files(files, ".", {ids[1]}, ids)
        one_rels = {r for _s, r in one}
        assert ids[1] + ".uasset" in one_rels and ids[1] + ".uexp" in one_rels
        assert ids[0] + ".uasset" not in one_rels
        irregular = outfits.filter_pak_files(files, ".", {ids[0], ids[3]}, ids)
        irregular_rels = {r for _s, r in irregular}
        assert ids[0] + ".uasset" in irregular_rels
        assert ids[3] + ".uexp" in irregular_rels
        assert ids[1] + ".uasset" not in irregular_rels
        assert "Player/Outfit/X/MI_A.uasset" in irregular_rels
        assert "Player/ModelMaterials/MainShader/t00.uasset" in irregular_rels
    finally:
        outfits.required_mi_ids = original


def test_full_selection_filters_real_manifest_from_62_to_58_pairs():
    with open(outfits.MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    rels = list(manifest.get("vanilla", [])) + list(manifest.get("project", []))
    files = [("template", rel.replace("\\", "/")) for rel in rels]
    before = {
        outfits.normalize_id(rel)
        for _src, rel in files
        if rel.startswith("Player/Outfit/")
        and rel.endswith(".uasset")
        and os.path.basename(rel).startswith("SK_")
    }
    known = outfits.catalog()
    filtered = outfits.filter_pak_files(files, ".", set(known), known)
    after_uasset = {
        outfits.normalize_id(rel)
        for _src, rel in filtered
        if rel.startswith("Player/Outfit/")
        and rel.endswith(".uasset")
        and os.path.basename(rel).startswith("SK_")
    }
    after_uexp = {
        outfits.normalize_id(rel)
        for _src, rel in filtered
        if rel.startswith("Player/Outfit/")
        and rel.endswith(".uexp")
        and os.path.basename(rel).startswith("SK_")
    }
    removed = before - after_uasset
    assert len(before) == 62
    assert len(after_uasset) == 58
    assert after_uasset == set(known)
    assert after_uexp == set(known)
    assert {
        os.path.basename(asset_id) for asset_id in removed
    } == {
        "SK_Player_Female_Outfit_Yakushima001",
        "SK_Player_Male_Outfit_Octavia001_v01",
        "SK_Player_Male_Outfit_Octavia001_v02",
        "SK_Player_Male_Outfit_Yakushima001",
    }
