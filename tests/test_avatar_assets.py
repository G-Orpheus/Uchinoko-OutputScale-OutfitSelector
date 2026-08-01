import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "py"))

import avatar_assets
import outfit_selection


def test_namespace_is_stable_and_separates_avatars():
    kalne = {"avatar_name": "kalne", "vrm_path": r"C:\VRM\kalne.vrm"}
    camome = {"avatar_name": "camome", "vrm_path": r"C:\VRM\camome.vrm"}
    assert avatar_assets.namespace_for_job(kalne) \
        == avatar_assets.namespace_for_job(dict(kalne))
    assert avatar_assets.namespace_for_job(kalne) \
        != avatar_assets.namespace_for_job(camome)


def test_private_paths_are_package_unique_and_below_uchinoko():
    a = avatar_assets.package_paths(
        {"avatar_name": "kalne", "vrm_path": r"C:\VRM\kalne.vrm"})
    b = avatar_assets.package_paths(
        {"avatar_name": "camome", "vrm_path": r"C:\VRM\camome.vrm"})
    for key in ("mi", "base", "normal", "orm"):
        assert a[key].startswith(
            "/Game/Pal/Model/Character/Uchinoko/" + a["namespace"] + "/")
        assert a[key] != b[key]


def test_private_filter_keeps_only_selected_outfit_sk_pairs():
    ids = outfit_selection.catalog()
    selected = {ids[0], ids[7]}
    files = []
    for asset_id in ids[:10]:
        for ext in (".uasset", ".uexp"):
            files.append(("src", asset_id + ext))
    files += [
        ("src", "Player/Outfit/X/MI_Shared.uasset"),
        ("src", "Player/Outfit/X/MI_Shared.uexp"),
        ("src", "Player/Head/X/SK_Head.uasset"),
    ]
    result = outfit_selection.filter_pak_files(
        files, "unused", selected, ids, private_materials=True)
    rels = {rel for _src, rel in result}
    assert {asset_id + ext for asset_id in selected
            for ext in (".uasset", ".uexp")} <= rels
    assert not any("MI_Shared" in rel for rel in rels)
    assert "Player/Head/X/SK_Head.uasset" in rels
