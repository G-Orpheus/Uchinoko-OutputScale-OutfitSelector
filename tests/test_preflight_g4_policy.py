import csv
import json
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_DIR = os.path.join(ROOT, "pipeline", "py")
sys.path.insert(0, PY_DIR)

import outfit_selection
import preflight_pak


def _inventory():
    outfits = [asset_id + ".uasset" for asset_id in outfit_selection.catalog()]
    head_equips = [
        "Player/HeadEquip/Normal{0:03d}/SK_NormalHeadEquip{0:03d}.uasset".format(i)
        for i in range(64)
    ]
    head_equips.extend([
        "Player/HeadEquip/YakushimaHeadEquip{0:03d}/"
        "SK_YakushimaHeadEquip{0:03d}.uasset".format(i)
        for i in range(1, 7)
    ])
    return {
        "Outfit": outfits,
        "Head": [
            "Player/Head/H{0:03d}/SK_Head{0:03d}.uasset".format(i)
            for i in range(52)
        ],
        "Hair": [
            "Player/Hair/H{0:03d}/SK_Hair{0:03d}.uasset".format(i)
            for i in range(37)
        ],
        "HeadEquip": head_equips,
    }


def test_g4_full_selection_uses_g10_exclusion_policy():
    inventory = _inventory()
    selected = set(outfit_selection.catalog())
    counts = preflight_pak._required_sk_counts(
        inventory, True, selected)
    assert counts == (58, 52, 37, 64)
    assert all(
        not preflight_pak._sk_is_required("HeadEquip", rel, True, selected)
        for rel in inventory["HeadEquip"][-6:]
    )


def test_g4_partial_selection_keeps_non_outfit_policy_counts():
    inventory = _inventory()
    selected = {outfit_selection.catalog()[17]}
    counts = preflight_pak._required_sk_counts(
        inventory, True, selected)
    assert counts == (1, 52, 37, 64)
    assert preflight_pak._sk_is_required(
        "Outfit", outfit_selection.catalog()[17] + ".uasset", True, selected)
    assert not preflight_pak._sk_is_required(
        "Outfit", outfit_selection.catalog()[18] + ".uasset", True, selected)


def test_real_lowercase_inventory_schema_is_normalized():
    source = _inventory()
    raw = {}
    for category, rows in source.items():
        raw[category.lower()] = [
            {"folder": "/Game/Pal/Model/Character",
             "name": os.path.basename(rel)[:-len(".uasset")],
             "rel": rel.replace("/", "\\")}
            for rel in rows
        ]
    with tempfile.TemporaryDirectory() as temp:
        path = os.path.join(temp, "sk_inventory.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        loaded = preflight_pak._load_sk_inventory(temp, [])
    selected = {outfit_selection.catalog()[0]}
    assert sorted(loaded) == ["Hair", "Head", "HeadEquip", "Outfit"]
    assert preflight_pak._required_sk_counts(
        loaded, True, selected) == (1, 52, 37, 64)
    assert all("\\" not in rel for rows in loaded.values() for rel in rows)


def test_zero_inventory_category_is_fatal():
    raw = {
        "outfit": [{"rel": "Player/Outfit/X/SK_X.uasset"}],
        "head": [{"rel": "Player/Head/X/SK_X.uasset"}],
        "hair": [],
        "headequip": [{"rel": "Player/HeadEquip/X/SK_X.uasset"}],
    }
    with tempfile.TemporaryDirectory() as temp:
        with open(os.path.join(temp, "sk_inventory.json"),
                  "w", encoding="utf-8") as f:
            json.dump(raw, f)
        try:
            preflight_pak._load_sk_inventory(temp, [])
        except preflight_pak.PreflightDataError as e:
            assert "0件" in str(e)
            assert os.path.abspath(temp) in str(e)
        else:
            raise AssertionError("zero category must be fatal")


def test_csv_schema_and_zero_rows_are_fatal():
    with tempfile.TemporaryDirectory() as temp:
        good = os.path.join(temp, "good.csv")
        with open(good, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Folder", "Name"])
            writer.writeheader()
            writer.writerow({"Folder": "/Game/Player", "Name": "SK_Test"})
        assert preflight_pak.count_csv(good) == 1

        empty = os.path.join(temp, "empty.csv")
        with open(empty, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["Folder", "Name"])
        try:
            preflight_pak.count_csv(empty)
        except preflight_pak.PreflightDataError as e:
            assert "0件" in str(e)
            assert os.path.abspath(empty) in str(e)
        else:
            raise AssertionError("zero-row CSV must be fatal")
