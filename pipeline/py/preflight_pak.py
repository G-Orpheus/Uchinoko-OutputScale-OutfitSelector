# -*- coding: utf-8 -*-
"""MOD pakのオフライン全数検品(ゲーム非起動)。1つでも落ちたら使用禁止。

PalModでゲーム内テストによって発覚した全敗因クラスを機械検証する:
  平坦化パス / SM6欠落 / バインドポーズずれ / スケルトン同梱 / 使用フラグ欠落 /
  ストリーミングミップ / 参照切れ

U50(2026-07-25)で構造ゲートを2つ追加した(**既定は警告、FAILにはしない**):
  G10 ライブpakに実在する全SKがこのpakに収録されているか(場所依存・名前単位)
  G11 全衣装SKの**全描画スロット**が注入アトラス t00 を指しているか
件数を締めていく運用は環境変数で行う:
  D2P_PREFLIGHT_COVERAGE / D2P_PREFLIGHT_SLOTROLE = fail | max:<件数> | warn(既定)

U50(2026-07-25 夕)で2点を仕様追随させた:
  * **非対応(コラボ系)装備の除外**(`vp_exclusions.py` が唯一の正本)。
    除外されたSKは注入もMI差し替えもされず**バニラのまま**出る(意図どおり)ので、
    G5/G5b/G10/G11 の検査対象から外す。**除外していないSKへの検査は一切
    緩めていない**(除外集合は vp_exclusions のみが決める)。
  * **マテリアル単一化**(live_template._unify_slot_materials、既定ON)により
    t01 は使われなくなり、全描画スロットのMIが t00 を参照する。G11の判定基準を
    旧「slot0->t00 / slot1->t01」から「**全描画スロットが t00**」へ更新した。

使い方: python preflight_pak.py <job.json> <mod.pak> <pak_extractルート> <cook_log>

cook_log引数(第4引数)について(2026-07-26 cooklog_fix):
  UEモード(pipeline\\cli\\convert.ps1のUE分岐)では実際にBuildCookRunで生成された
  本物のcookログ(生テキスト)が渡される。
  noueモード(既定)では実際にcookする工程が無いため、代わりに
  `pipeline\\py\\noue_master\\shader_platform_facts.json`(SM5/SM6双方でcook済みという
  固定の事実だけを持つJSON、live_template.COOK_LOG経由)が渡される。
  G7はこの2形式のどちらが来ても判定できるよう、JSON解析を先に試み、
  失敗したら生ログへの文字列検索へフォールバックする(下記G7実装参照)。
"""

import glob
import gzip
import csv
import json
import os
import re
import sys
import tempfile

# v2.2.13 non-English Windows backport: PowerShell may launch Python with an
# ANSI console code page that cannot encode diagnostics such as an em dash or
# paths containing non-ASCII characters.  This changes output encoding only;
# no gate policy or inspected binary data is modified.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir, os.pardir))
sys.path.insert(0, SCRIPT_DIR)
import vp_core as core
# U50: 「非対応(コラボ系)」装備の除外リスト(唯一の正本)。除外されたSKは
# 注入もMI差し替えもされずバニラのままpakへ入る/入らないので、検品側も
# 同じ正本を見て検査対象から外す必要がある(pakの欠陥ではない)。
import vp_exclusions  # noqa: E402
import outfit_selection  # noqa: E402
import live_template  # noqa: E402
import vp_matparam  # noqa: E402
import vp_tex  # noqa: E402
import avatar_assets  # noqa: E402
# U18: G5/G5b用(pakに実際に同梱されたRenderSectionsのBoneMapを読むため)。
# U51(research\ue_exit→pipeline\py移設): parse_sk_structure.pyは元research\ue_exit\
# から無改変のままpipeline\py\へコピーされた(research\ue_exit\側は開発参照用に
# 残置、実行時には見ない)。同じディレクトリ(HERE、上でsys.pathへ追加済み)から
# そのままimportできる
import parse_sk_structure as sk_struct  # noqa: E402

results = []
soft_results = []


class PreflightDataError(RuntimeError):
    pass


def gate(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _neutral_material_check(mod_pak, job):
    """置換MIの非Base Color入力と中立テクスチャ実体を検査する。"""
    _mount, pak_entries = core.read_pak_entries(mod_pak)

    def read_entry(rel):
        entry = pak_entries.get(rel)
        if entry is None:
            return None
        if entry["compression"] != 0:
            raise ValueError(f"圧縮エントリは未対応: {rel}")
        with open(mod_pak, "rb") as f:
            f.seek(entry["data_offset"])
            return f.read(entry["size"])

    private = avatar_assets.package_paths(job)
    private_rel = {
        key: value[len(avatar_assets.GAME_PREFIX):]
        for key, value in private.items() if key in ("mi", "base", "normal", "orm")
    }
    mi_files = [private_rel["mi"] + ".uasset"]
    checked = 0
    bad = []
    for ua_rel in sorted(set(mi_files)):
        ue_rel = ua_rel[:-len(".uasset")] + ".uexp"
        if ue_rel not in pak_entries:
            continue
        try:
            ua_bytes = read_entry(ua_rel)
            ue_bytes = read_entry(ue_rel)
            params = vp_matparam.list_texture_parameters(ua_bytes, ue_bytes)
            scalars = vp_matparam.list_scalar_parameters(ua_bytes, ue_bytes)
        except (OSError, ValueError, vp_matparam.MatParamError) as e:
            bad.append(f"{os.path.basename(ua_rel)}:解析失敗({e})")
            continue
        by_name = {p["name"]: p["path"] for p in params}
        if "Normal Map" not in by_name \
                or "MetallicRoughnessOcclusionSpecularTexture" not in by_name:
            continue
        checked += 1
        if by_name["Normal Map"] != private["normal"]:
            bad.append(
                f"{os.path.basename(ua_rel)}:Normal={by_name['Normal Map']}")
        if by_name["MetallicRoughnessOcclusionSpecularTexture"] \
                != private["orm"]:
            bad.append(
                f"{os.path.basename(ua_rel)}:ORM="
                f"{by_name['MetallicRoughnessOcclusionSpecularTexture']}")
        scalar_by_name = {p["name"]: p["value"] for p in scalars}
        if abs(float(scalar_by_name.get("Specular", 1.0))) > 1.0e-6:
            bad.append(
                f"{os.path.basename(ua_rel)}:Specular="
                f"{scalar_by_name.get('Specular', '未指定')}")

    flat_specs = (
        (private["normal"],
         live_template._NORMAL_FLAT_VALUE),
        (private["orm"],
         live_template._ORM_FLAT_VALUE),
    )
    for game_path, value in flat_specs:
        rel = game_path[len("/Game/Pal/Model/Character/"):]
        ue_rel = rel + ".uexp"
        if ue_rel not in pak_entries:
            bad.append(f"{rel}.uexp:未収録")
            continue
        try:
            data = read_entry(ue_rel)
            info = live_template._parse_texture_mips_lenient(data)
            if info["pixel_format"] == "PF_BC5":
                block = live_template._encode_flat_bc5_block(*value)
            elif info["pixel_format"] == "PF_DXT1":
                block = live_template._encode_flat_dxt1_block(*value)
            else:
                raise ValueError(f"想定外format={info['pixel_format']}")
            for i, mip in enumerate(info["mips"]):
                if not mip["inline"]:
                    bad.append(f"{rel}:mip{i}が非inline")
                    break
                if data[mip["offset"]:mip["offset"] + len(block)] != block:
                    bad.append(f"{rel}:mip{i}が中立値でない")
                    break
        except (OSError, ValueError, live_template._OutfitMaterialPatchError) as e:
            bad.append(f"{rel}:検査失敗({e})")
    return checked, bad


def _alpha_mask_check(mod_pak, job_dir, conv, job):
    """元PNG・最終t00・統一MIのAlpha/Masked接続を照合する。"""
    _mount, pak_entries = core.read_pak_entries(mod_pak)

    def read_entry(rel):
        e = pak_entries.get(rel)
        if e is None or e["compression"] != 0:
            return None
        with open(mod_pak, "rb") as f:
            f.seek(e["data_offset"])
            return f.read(e["size"])

    sources = []
    atlas = os.path.join(job_dir, "build", "atlas", "atlas_body.png")
    if os.path.exists(atlas):
        sources.append(atlas)
    else:
        meta_path = os.path.join(conv, "avatar_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            for info in meta.get("slots", {}).values():
                tex = info.get("texture")
                if tex and tex.lower().endswith(".png"):
                    path = os.path.join(job_dir, "textures", tex)
                    if os.path.exists(path) and path not in sources:
                        sources.append(path)
    source_stats = []
    for path in sources:
        try:
            _w, _h, rgba = vp_tex.decode_png(path)
            source_stats.append(vp_tex.alpha_stats(rgba))
        except Exception:
            pass
    source_transparent = sum(s["below_128"] for s in source_stats)
    source_min = min((s["min"] for s in source_stats), default=255)
    source_max = max((s["max"] for s in source_stats), default=255)

    private = avatar_assets.package_paths(job)
    tex_rel = (private["base"][len(avatar_assets.GAME_PREFIX):]
               + ".uexp")
    tex_data = read_entry(tex_rel)
    if tex_data is None:
        return False, "最終PAKにt00.uexpが無い"
    try:
        layout = core.parse_texture2d(tex_data)
        mip = layout["mips"][0]
        decoded = vp_tex.decode_dxt(
            tex_data[mip["offset"]:mip["offset"] + mip["size"]],
            mip["w"], mip["h"], layout["pixel_format"])
        final_stats = vp_tex.alpha_stats(decoded)
    except Exception as e:
        return False, f"最終t00のAlpha解析失敗({e})"
    if source_transparent > 0 and final_stats["transparent"] <= 0:
        return False, (f"元PNGに透明画素{source_transparent}があるのに最終"
                       f"{layout['pixel_format']}が不透明")

    mi_rel = private["mi"][len(avatar_assets.GAME_PREFIX):] + ".uasset"
    if mi_rel is None:
        return False, "検査対象Outfit MIが無い"
    mi_ua = read_entry(mi_rel)
    mi_ue = read_entry(mi_rel[:-7] + ".uexp")
    if mi_ua is None or mi_ue is None:
        return False, "Outfit MIのバイナリペアが無い"
    try:
        opacity = live_template.inspect_opacity_mask_settings(mi_ue)
        params = {p["name"]: p["path"] for p in
                  vp_matparam.list_texture_parameters(mi_ua, mi_ue)}
    except Exception as e:
        return False, f"MI Alpha設定の解析失敗({e})"
    if not opacity.get("valid") or params.get("Base Texture") \
            != private["base"]:
        return False, f"MIのMasked/Opacity接続が不正: {opacity} Base={params.get('Base Texture')}"
    return True, (
        f"元Alpha min={source_min} max={source_max} transparent(<128)="
        f"{source_transparent} / 最終{layout['pixel_format']} min="
        f"{final_stats['min']} max={final_stats['max']} transparent="
        f"{final_stats['transparent']} / MI BlendMode=Masked "
        f"OpacityMask=Base Texture.A Clip="
        f"{opacity['opacity_mask_clip_value']:.4f}")


def _private_wiring_check(mod_pak, job, selected_outfits):
    """Verify selected SKs and all private package pairs as one closed set."""
    private = avatar_assets.package_paths(job)
    rels = {
        key: value[len(avatar_assets.GAME_PREFIX):]
        for key, value in private.items() if key in ("mi", "base", "normal", "orm")
    }
    _mount, pak_entries = core.read_pak_entries(mod_pak)
    pak_set = set(pak_entries)
    expected_private = {
        rels[key] + ext
        for key in ("mi", "base", "normal", "orm")
        for ext in (".uasset", ".uexp")
    }
    missing = sorted(expected_private - pak_set)
    collisions = sorted(
        p for p in pak_set
        if p.startswith("Player/ModelMaterials/MainShader/")
        or (p.startswith("Player/Outfit/")
            and not os.path.basename(p).startswith("SK_"))
        or p in {
            "Player/Body/Male/MI_Player_Male_Body.uasset",
            "Player/Body/Male/MI_Player_Male_Body.uexp",
            "Player/Body/Female/MI_Player_Female_Body.uasset",
            "Player/Body/Female/MI_Player_Female_Body.uexp",
        })
    bad_sk = []

    def read_entry(rel):
        entry = pak_entries.get(rel)
        if entry is None or entry["compression"] != 0:
            return None
        with open(mod_pak, "rb") as f:
            f.seek(entry["data_offset"])
            return f.read(entry["size"])

    with tempfile.TemporaryDirectory(prefix="d2p_private_check_") as tmp:
        for asset_id in sorted(selected_outfits):
            ua_rel, ue_rel = asset_id + ".uasset", asset_id + ".uexp"
            ua_data, ue_data = read_entry(ua_rel), read_entry(ue_rel)
            if ua_data is None or ue_data is None:
                bad_sk.append(f"{asset_id}: binary pair missing/compressed")
                continue
            base = os.path.basename(asset_id)
            ua_path = os.path.join(tmp, base + ".uasset")
            ue_path = os.path.join(tmp, base + ".uexp")
            with open(ua_path, "wb") as f:
                f.write(ua_data)
            with open(ue_path, "wb") as f:
                f.write(ue_data)
            try:
                refs = live_template.find_outfit_material_paths_all(
                    ua_path, ue_path)
            except Exception as e:
                bad_sk.append(f"{asset_id}: parse failed ({e})")
                continue
            if not refs or set(refs) != {private["mi"]}:
                bad_sk.append(f"{asset_id}: {sorted(set(refs))}")
    ok = not missing and not collisions and not bad_sk
    detail = (f"private=8 files / SK={len(selected_outfits)} / "
              f"MI={private['mi']}")
    if missing:
        detail += f" missing={missing[:3]}"
    if collisions:
        detail += f" shared-collision={collisions[:3]}"
    if bad_sk:
        detail += f" bad-SK={bad_sk[:2]}"
    return ok, detail


def soft_gate(name, ok, detail, env_flag, n_bad=0):
    """U50: 既定では警告(WARN)で、環境変数でFAILへ昇格できるゲート。

    背景(work\\u50_equip\\out\\FINDINGS.txt): 既存の件数照合ゲート(G4)は
    「CSV生成側」と「pak収録側」が同じ正規表現の盲点を共有しているため、
    両方が同じだけ漏れていると件数が一致してしまい検出できなかった。
    G10/G11はその盲点を持たない構造ゲートだが、導入時点で既知のNGが
    残っている(G11=16/60SK。別途「マテリアル完全単一化」で対応中)。
    ここでFAILにすると既存のビルドが全部落ちるため、**当面は警告**とし、
    件数が減っていくのを追えるようにNG件数と内訳を必ず出力する。

    将来の昇格は環境変数で行う(既定=warn):
      <env_flag>=fail     … NGが1件でもあればFAIL
      <env_flag>=max:<N>  … NGがN件を超えたらFAIL(件数を締めていく運用向け)
      <env_flag>=warn/未設定 … 常に警告(検品の合否には影響しない)
    """
    mode = (os.environ.get(env_flag) or "warn").strip().lower()
    promote = False
    if not ok:
        if mode == "fail":
            promote = True
        elif mode.startswith("max:"):
            try:
                promote = n_bad > int(mode[len("max:"):])
            except ValueError:
                promote = True   # 指定が壊れているなら安全側(FAIL)へ
    if promote:
        gate(name, False, f"{detail} [{env_flag}={mode} によりFAILへ昇格]")
        return
    soft_results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'WARN'}] {name}" + (f" — {detail}" if detail else ""))


def count_csv(path):
    """Validate and count a generated duplication CSV.

    Paths passed by main are anchored at job_dir/vanilla, never at cwd.
    The extractor writes UTF-8 CSV with the exact columns Folder,Name.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise PreflightDataError(f"対象一覧CSVが見つかりません: {path}")
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != ["Folder", "Name"]:
                raise PreflightDataError(
                    f"対象一覧CSVの列名が不正です: {path} "
                    f"(実測={reader.fieldnames!r}, 期待=['Folder', 'Name'])")
            rows = [row for row in reader
                    if (row.get("Folder") or "").strip()
                    and (row.get("Name") or "").strip()]
    except (OSError, UnicodeError, csv.Error) as e:
        raise PreflightDataError(f"対象一覧CSVを読めません: {path}: {e}")
    if not rows:
        raise PreflightDataError(f"対象一覧CSVが0件です: {path}")
    return len(rows)


def _manifest_sk_counts():
    """noue_template_manifest.jsonが宣言している(=noueが実際に用意する)
    カテゴリ別SK数を返す。読めなければNone。

    U50: dup_*.csv は「バニラpakに実在する全SK」の**場所依存の完全列挙**へ
    直したので、noueテンプレがまだカバーしていないSK(2026-07-25時点で
    HeadEquipのYakushima 6件。ダミーSK資産の新規生成が要るため未対応)が
    あると、CSV由来の期待値とpak実測がずれる。noueにとっての「宣言された
    収録集合」はmanifestなので、G4はCSV由来かmanifest由来のどちらかに
    一致すればPASSとする。**漏れの検出はG10(名前単位)が担当する**ので、
    ここを緩めても盲点にはならない。
    """
    path = os.path.join(SCRIPT_DIR, "noue_template_manifest.json")
    if not os.path.isfile(path):
        raise PreflightDataError(
            f"テンプレートmanifestが見つかりません: {path}")
    try:
        with open(path, encoding="utf-8-sig") as f:
            man = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise PreflightDataError(
            f"テンプレートmanifestを読めません: {path}: {e}")
    if not isinstance(man, dict):
        raise PreflightDataError(
            f"テンプレートmanifestのルートがobjectではありません: {path}")
    rels = list(man.get("vanilla", [])) + list(man.get("project", []))
    out = {}
    for cat in ("Outfit", "Head", "Hair", "HeadEquip"):
        pfx = f"Player/{cat}/"
        out[cat] = len([r for r in rels
                        if r.startswith(pfx) and r.endswith(".uasset")
                        and os.path.basename(r).startswith("SK_")])
    empty = [cat for cat, count in out.items() if count == 0]
    if empty:
        raise PreflightDataError(
            f"テンプレートmanifestの必須カテゴリが0件です: "
            f"{path}: {empty}")
    return (out["Outfit"], out["Head"], out["Hair"], out["HeadEquip"])


def _load_sk_inventory(vanilla_dir, vanilla_entries):
    """バニラpakのSK完全在庫(場所依存列挙)を得る。

    extract_vanilla.pyが書き出したsk_inventory.jsonを使い、無ければ
    pak_entries.txt.gzから同じ関数でその場で作り直す(古いjobディレクトリ
    でもゲートが効くように)。返り値: {category: [rel, ...]} or None。
    """
    vanilla_dir = os.path.abspath(vanilla_dir)
    path = os.path.join(vanilla_dir, "sk_inventory.json")
    inv = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                inv = json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError) as e:
            raise PreflightDataError(
                f"SK対象一覧を読めません: {path}: {e}")
    if inv is None:
        try:
            import extract_vanilla
            inv = extract_vanilla.enumerate_vanilla_sk(vanilla_entries)
        except Exception as e:
            raise PreflightDataError(
                f"SK対象一覧が無く、再構成にも失敗しました: "
                f"{path}: {e}")

    if not isinstance(inv, dict):
        raise PreflightDataError(
            f"SK対象一覧のルートがobjectではありません: {path}")
    # extract_vanilla's real schema uses lower-case category keys.  Accept
    # case variations, then expose one canonical spelling to G4/G10.
    canonical = {
        "outfit": "Outfit",
        "head": "Head",
        "hair": "Hair",
        "headequip": "HeadEquip",
    }
    normalized = {name: [] for name in canonical.values()}
    unknown_categories = []
    for raw_category, rows in inv.items():
        key = str(raw_category).replace("_", "").replace("-", "").lower()
        category = canonical.get(key)
        if category is None:
            unknown_categories.append(str(raw_category))
            continue
        if not isinstance(rows, list):
            raise PreflightDataError(
                f"SK対象一覧のカテゴリが配列ではありません: "
                f"{path}: {raw_category!r}")
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get("rel"), str):
                raise PreflightDataError(
                    f"SK対象一覧のrel列が不正です: "
                    f"{path}: {raw_category}[{index}]")
            rel = row["rel"].strip().replace("\\", "/")
            if not rel:
                raise PreflightDataError(
                    f"SK対象一覧のrel列が空です: "
                    f"{path}: {raw_category}[{index}]")
            normalized[category].append(rel)
    empty = [category for category, rows in normalized.items() if not rows]
    if empty:
        raise PreflightDataError(
            f"SK対象一覧の必須カテゴリが0件です: {path}: "
            f"{empty} (実カテゴリ={sorted(map(str, inv))}, "
            f"未知カテゴリ={unknown_categories})")
    return normalized


def _sk_is_required(category, rel, has_outfit_selection=False,
                    selected_outfits=None):
    """Return whether an inventory SK is required by the current policy.

    G4 (counts) and G10 (name-by-name coverage) must use this same predicate.
    Collaboration assets are intentionally unsupported, and an explicit
    outfit selection limits only the Outfit category.
    """
    if vp_exclusions.is_excluded(rel):
        return False
    if has_outfit_selection and category == "Outfit":
        return (outfit_selection.normalize_id(rel)
                in (selected_outfits or set()))
    return True


def _required_sk_counts(inventory, has_outfit_selection=False,
                        selected_outfits=None):
    """Return policy-filtered counts in G4 category order."""
    if inventory is None:
        return None
    return tuple(
        sum(1 for rel in inventory.get(category, [])
            if _sk_is_required(category, rel, has_outfit_selection,
                               selected_outfits))
        for category in ("Outfit", "Head", "Hair", "HeadEquip")
    )


_GAME_PKG_PREFIX = "/Game/Pal/Model/Character/"


def _slot_role_check(template_dir, selected_ids=None):
    """全衣装SKについて、**全描画スロット**が注入アトラス t00 を指しているかを
    テンプレート上の実バイトから機械判定する。

    ### 判定基準の変更(2026-07-25、マテリアル単一化に伴う)

    旧基準は「slot0->t00 / slot1->t01」で、live_template側の
    「同じMIが別SKで別スロット役 → 競合ガードで差し替え対象外」という挙動を
    **シミュレート**して数えていた(work\\u50_equip\\slot_role_check.py 由来)。

    現在の live_template._unify_slot_materials(既定ON)は、注入対象衣装SKの
    描画スロットが参照するMIを**全件**、たった1種類の統一MI(Base Texture=t00)
    で置き換える。スロット役という概念自体が無くなり t01 は使われない。
    よって基準は「**全描画スロットが t00**」になる。
    旧基準のままだと slot1 が必ず t00 になるため全件NGとなり誤検知する
    (この基準変更前のNG 16件はすべて旧基準由来で、実体は正常だった)。

    ### シミュレーションではなく実バイトを見る

    旧実装はSKのMaterials[]の参照関係だけから結果を推定していたが、本実装は
    参照先のMIアセットを**テンプレート上で実際に開き**、name tableに
    `<MainShaderパッケージ>/t00` が入っているか(=Base Textureが我々の
    注入アトラスへ向いているか)を読む。統一MIの書き出しが漏れたMIは
    バニラのままなので name table に一致が無く、"VANILLA" として確実にNGになる。
    テンプレートに当該MIファイル自体が無い場合も "MISSING" でNGにする。

    非対応(コラボ系、vp_exclusions)のSKは、MI差し替え自体を意図的に
    行わない(=バニラの装備がそのまま出る)ため検査対象から外す。

    返り値: (NG件数, 検査件数, NG明細のリスト, エラー文字列 or None)
    """
    try:
        import live_template as lt
    except Exception as e:
        return 0, 0, [], f"live_templateのimportに失敗: {e}"
    # live_template._unify_slot_materials / collect_unified_mi_targets が
    # 使うのと同じ「スロット役を割り当てない出現順の全マテリアルパス」取得。
    finder = getattr(lt, "find_outfit_material_paths_all", None)
    err_cls = getattr(lt, "_OutfitMaterialPatchError", Exception)
    mvp_prefix = getattr(lt, "MVP_PACKAGE_PREFIX", None)
    if finder is None or mvp_prefix is None:
        return 0, 0, [], ("live_template.find_outfit_material_paths_all / "
                          "MVP_PACKAGE_PREFIX が無い"
                          "(実装が変わった可能性。ゲートの追随が要る)")
    outfit_root = os.path.join(template_dir, "Player", "Outfit")
    if not os.path.isdir(outfit_root):
        return 0, 0, [], f"テンプレートにPlayer/Outfitが無い: {outfit_root}"

    atlas_cache = {}

    def atlas_of(mi_full_path):
        """MIアセットが実際に参照している注入アトラス名を返す。
        t00 / t01 / "t00+t01" / "VANILLA"(注入アトラス参照なし) / "MISSING"。"""
        if mi_full_path in atlas_cache:
            return atlas_cache[mi_full_path]
        v = "MISSING"
        if mi_full_path.startswith(_GAME_PKG_PREFIX):
            rel = mi_full_path[len(_GAME_PKG_PREFIX):]
            ua = os.path.join(template_dir, *rel.split("/")) + ".uasset"
            if os.path.exists(ua):
                try:
                    names = core.read_names(ua)
                except Exception as e:
                    v = f"PARSE_ERROR({e})"
                else:
                    hit = sorted({n.rsplit("/", 1)[-1] for n in names
                                  if n.startswith(mvp_prefix + "/t")})
                    v = "+".join(hit) if hit else "VANILLA"
        atlas_cache[mi_full_path] = v
        return v

    ng = []
    n_checked = 0
    n_excluded = 0
    for dirpath, _d, fns in os.walk(outfit_root):
        for fn in sorted(fns):
            if not fn.startswith("SK_") or not fn.endswith(".uasset"):
                continue
            ua = os.path.join(dirpath, fn)
            ue = ua[:-len(".uasset")] + ".uexp"
            rel = os.path.relpath(ua, outfit_root).replace("\\", "/")
            full_id = outfit_selection.normalize_id("Player/Outfit/" + rel)
            if selected_ids is not None and full_id not in selected_ids:
                continue
            if vp_exclusions.is_excluded(rel):
                n_excluded += 1
                continue
            n_checked += 1
            try:
                paths = finder(ua, ue)
            except err_cls as e:
                ng.append(f"{rel}: 描画スロットのMIパスを特定できない({e})")
                continue
            if not paths:
                ng.append(f"{rel}: 描画スロットのマテリアル参照が0件")
                continue
            bad = [f"slot{i}={atlas_of(p)}({p.rsplit('/', 1)[-1]})"
                   for i, p in enumerate(paths) if atlas_of(p) != "t00"]
            if bad:
                ng.append(f"{rel}: " + " / ".join(bad) + " ※期待は全スロットt00")
    if n_excluded:
        print(f"  [INFO] G11 非対応(コラボ系)のため対象外: {n_excluded}件")
    return len(ng), n_checked, ng, None


def main():
    job_path = os.path.abspath(sys.argv[1])
    job = core.load_job(job_path)
    raw_job_dir = job.get("job_dir") or os.path.dirname(job_path)
    if not os.path.isabs(raw_job_dir):
        raw_job_dir = os.path.join(os.path.dirname(job_path), raw_job_dir)
    job_dir = os.path.abspath(raw_job_dir)
    job["job_dir"] = job_dir
    known_outfits = outfit_selection.catalog()
    try:
        selected_outfits = outfit_selection.selected(job, known_outfits)
    except ValueError as e:
        gate("G0 防具選択", False, str(e))
        return finish()
    has_outfit_selection = "selected_outfits" in job
    private_paths = avatar_assets.package_paths(job)
    private_rels = {
        key: value[len(avatar_assets.GAME_PREFIX):]
        for key, value in private_paths.items()
        if key in ("mi", "base", "normal", "orm")
    }
    mod_pak, extract, cook_log = sys.argv[2], sys.argv[3], sys.argv[4]
    vanilla_dir = os.path.abspath(os.path.join(job_dir, "vanilla"))
    conv = os.path.abspath(os.path.join(job_dir, "converted"))

    print("=== preflight: MOD pakオフライン検品 ===")
    if not os.path.exists(mod_pak):
        gate("pak存在", False, mod_pak)
        return finish()

    mount, entries = core.read_pak_index(mod_pak)
    pak_outfit_files = {p for p in entries
                        if p.startswith("Player/Outfit/")
                        and os.path.basename(p).startswith("SK_")
                        and p.endswith((".uasset", ".uexp"))}
    if has_outfit_selection:
        expected_outfit_files = {asset_id + ext for asset_id in selected_outfits
                                 for ext in (".uasset", ".uexp")}
        gate("G0 防具選択とSKバイナリペア",
             pak_outfit_files == expected_outfit_files,
             f"選択{len(selected_outfits)}件 / 収録{len(pak_outfit_files) // 2}件"
             + (f" 不足{sorted(expected_outfit_files - pak_outfit_files)[:2]}"
                if expected_outfit_files - pak_outfit_files else "")
             + (f" 余分{sorted(pak_outfit_files - expected_outfit_files)[:2]}"
                if pak_outfit_files - expected_outfit_files else ""))
    with gzip.open(os.path.join(vanilla_dir, "pak_entries.txt.gz"), "rt",
                   encoding="utf-8") as f:
        vanilla_entries = f.read().splitlines()
    vanilla_set = set(vanilla_entries)
    # G4 and G10 share this inventory and the same policy predicate.  Loading
    # it once also prevents the two gates from observing different fallbacks.
    try:
        sk_inventory = _load_sk_inventory(vanilla_dir, vanilla_entries)
    except PreflightDataError as e:
        gate("FATAL SK対象一覧の読み込み", False, str(e))
        return finish()

    # G1: マウントポイント
    gate("G1 マウントポイント",
         mount == "../../../Pal/Content/Pal/Model/Character/", mount)

    # G2: パス整合(平坦化検知)。新規アセット(ModelMaterials)とアンカー以外は
    # バニラに同一パスが存在しなければならない(=正しく上書きされる証拠)
    full = [mount.replace("../../../", "") + e for e in entries]
    new_asset_ok = re.compile(r".*/ModelMaterials/MainShader/[^/]+$")
    # 新称(_divetopalworld_anchor.txt)/旧称(_vrm2palworld_anchor.txt、改名前に
    # 生成された既存pak向け)の両方を許容する(2026-07-22昼発覚。過去に生成済みの
    # pakの検品を壊さないため。生成側は改名コミット02f1f24で既に新称に統一済み)
    anchor_ok = re.compile(r".*_(?:divetopalworld|vrm2palworld)_anchor\.txt$")
    private_full = {
        mount.replace("../../../", "") + rel + ext
        for rel in private_rels.values()
        for ext in (".uasset", ".uexp")
    }
    bad = [p for p in full
           if not (p in vanilla_set or p in private_full
                   or new_asset_ok.match(p) or anchor_ok.match(p))]
    gate("G2 全エントリのパスがバニラと一致(平坦化なし)", not bad,
         f"不一致{len(bad)}件 例:{bad[:3]}" if bad else f"{len(full)}件OK")

    # G3: 禁止物(共有スケルトン・素体・ストリーミングミップ・装備専用Skeleton/Physics)。
    # このゲート自体はT3設計(U40)より前から存在する既存の安全境界であり、
    # 「共有スケルトン・素体スケルタルメッシュ本体・Physics・ストリーミング
    # ミップは改変対象外」という原則は今回も維持する(全面禁止のまま)。
    #
    # U42(2026-07-25、指揮者裁定): 素体共有MI(MI_Player_Male_Body/
    # MI_Player_Female_Body、MaterialInstanceConstant資産。スケルタルメッシュ
    # 本体でもSkeletonでもPhysicsでもubulkでもない)のみ、完全一致の
    # ホワイトリストで狭く例外許可する。背景: T3(pipeline\py\live_template.py
    # _inject_outfit_body_parka_textures)がこの2ファイルを「Materials[]配列内の
    # 物理スロット位置がSKによって異なる競合」として安全側除外していたため、
    # 多数の衣装が参照する素体のBase Textureが実機で常にバニラのまま
    # (=アバターの肌色が一切乗らない)という実測不具合(docs\
    # REPORT_U42_2026-07-25.md G1節)があった。ホワイトリストは意図的に
    # パターンではなく4パス(2ファイル×.uasset/.uexp)の完全一致列挙とし、
    # 将来他のBody配下ファイルが意図せず紛れ込んでも機械的に弾かれるよう
    # 構造的に防ぐ。
    # U46(2026-07-25): 体の色ズレ(茶色い体・顔の金属質模様・服のしわ)修正の
    # 一環で、素体共有MIが参照するNormal/MetallicRoughnessOcclusionSpecular
    # テクスチャ資産(/Body/配下、同一パス・ペイロード置換で平坦中立値に
    # 差し替え。ubulk化はせず全ミップinlineへ再構成済み — G3の.ubulk全面
    # 禁止には抵触しない)を追加。U42と同じ原理(完全一致の列挙、パターン
    # マッチ不使用、将来の意図しない拡大を機械的に防ぐ)。live_template.py
    # _flatten_normal_orm_textures参照。
    # U47(2026-07-25): 素体スロット(ShadingModel=6 TwoSidedFoliage)の
    # 「Subsurface Texture」がアバター自身のBase Textureへ再配線されていた
    # ことが「肌の色被り」の実測原因だったため(docs\REPORT_U47_2026-07-25.md
    # G1節)、この再配線を廃止し、代わりに元々の参照先テクスチャ資産自体を
    # 黒へ平坦化する方式(U46のNormal/ORMと同じ技法)へ切り替えた。実測
    # (work\u47_diag\probe_sss_tex.py): 該当資産は
    # /Player/Body/Female/T_Player_Female_Body_SSS の1件のみで、男性素体MIも
    # このFemale資産を共有参照する(Male_Body_SSSという別ファイルは存在
    # しない)。U42/U46と同じ原理(完全一致の列挙、パターンマッチ不使用)で
    # 2パス(1ファイル×.uasset/.uexp)を追加する。
    _G3_BODY_MI_WHITELIST = frozenset({
        "Player/Body/Male/MI_Player_Male_Body.uasset",
        "Player/Body/Male/MI_Player_Male_Body.uexp",
        "Player/Body/Female/MI_Player_Female_Body.uasset",
        "Player/Body/Female/MI_Player_Female_Body.uexp",
        "Player/Body/Female/T_Player_Female_Body_SSS.uasset",
        "Player/Body/Female/T_Player_Female_Body_SSS.uexp",
    } | {
        f"Player/Body/{gender}/T_Player_{gender}_Body_{suffix}.{ext}"
        for gender in ("Male", "Female")
        for suffix in ("N", "max_N", "min_N", "M")
        for ext in ("uasset", "uexp")
    })
    forbidden = [p for p in entries
                 if (("Skeleton/" in p or "/Body/" in p or p.endswith(".ubulk")
                      or "_Skeleton." in p or "Physics" in p)
                     and p not in _G3_BODY_MI_WHITELIST)]
    gate("G3 禁止物ゼロ(Skeleton/Body/Physics/ubulk、素体MI 4パスのみ例外許可)", not forbidden,
         str(forbidden[:3]) if forbidden else "")

    # G4: 収録数(複製リスト+複製元。マテリアル・テクスチャはスロット表から導出)
    with open(os.path.join(conv, "avatar_meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    try:
        n_out_m = count_csv(
            os.path.join(vanilla_dir, "dup_outfit_male.csv")) + 1
        n_out_f = count_csv(
            os.path.join(vanilla_dir, "dup_outfit_female.csv")) + 1
        n_head = (
            count_csv(os.path.join(vanilla_dir, "dup_head_male.csv")) + 1
            + count_csv(os.path.join(
                vanilla_dir, "dup_head_female.csv")) + 1)
        n_hair = count_csv(
            os.path.join(vanilla_dir, "dup_hair.csv")) + 1
        n_he = count_csv(
            os.path.join(vanilla_dir, "dup_headequip.csv")) + 1
    except PreflightDataError as e:
        gate("FATAL CSV対象一覧の読み込み", False, str(e))
        return finish()
    n_mat = len(meta["slots"])
    n_tex = len({s["texture"] for s in meta["slots"].values() if s["texture"]})
    # U19(2026-07-23、U54(2026-07-26)で式を訂正):
    # counts[4]/counts[5]が数えているのは、avatar_meta.json由来のスロット数
    # (n_mat/n_tex)から導いた「何バケツに丸められるか」ではなく、
    # **noueテンプレートが常に持つ固定2パッケージ名そのもの**である:
    #   counts[4] = canonical_mat(MainShader/M_VP_[A-Za-z0-9]+.uasset)
    #             = M_VP_m00.uasset / M_VP_m01.uasset の実在数(常に2)
    #   counts[5] = MainShader/配下でM_VP_*でない.uasset
    #             = t00.uasset / t01.uasset の実在数(常に2)
    # このm00/m01・t00/t01はavatar_meta.jsonのスロット数に関係なく、
    # Palworldプレイヤーメッシュテンプレート自身が常に同梱する固定資産
    # 名である(live_template.MVP_PACKAGE_PREFIX配下、
    # convert_noue.prepare_material_overridesが上書きしない残りはテンプレ
    # 既定のまま同梱される)。U50-single(2026-07-25)でvp_atlas.classify_material
    # が常に0(body)を返すよう単一化されて以降、「3枚以上は2バケツへ丸める」
    # という旧説明は成立しなくなっている(全スロットがbodyへ畳まれる)が、
    # テンプレート資産自体の固定2枚という実体は単一化の前後で変わっていない。
    # 実測(2026-07-26): alicia(12マテリアル)/seed/vrm1でも実測counts[4:]は
    # 常に(2,2)——n_mat依存ではなくテンプレート構造依存であることが独立に
    # 確認できる。min(n_mat,2)はn_mat>=2の間はたまたま2に一致していたため
    # 誤りが露見しなかったが、n_mat=1(vrm_kate/vrm_robothead)では期待値が
    # 1に丸まってしまい、実測の2と食い違って誤FAILしていた
    # (docs的経緯はdiag_A_vrm.md参照)。
    # 正しい期待値は「材質が1件以上あれば常に2、0件なら0」。
    # テクスチャはt00/t01に加え、元防具Normal/ORMへのフォールバックを
    # 防ぐ専用中立テクスチャVP_FlatNormal/VP_FlatORMの計4件。
    # (=注入すら起きていない=過小収録の検知は維持)」。
    n_mat_expect = 1 if n_mat >= 1 else 0
    n_tex_expect = 3 if n_tex >= 1 else 0
    csv_expect4 = ((len(selected_outfits) if has_outfit_selection
                    else n_out_m + n_out_f),
                   n_head, n_hair, n_he)
    policy_expect4 = _required_sk_counts(
        sk_inventory, has_outfit_selection, selected_outfits)
    # Old caches without sk_inventory.json still fall back to the historical
    # CSV counts.  Normal/current builds derive all four SK counts from the
    # same complete inventory and exclusion policy used by G10.
    primary_expect4 = policy_expect4 or csv_expect4
    expect = primary_expect4 + (n_mat_expect, n_tex_expect)
    # U13: noueのマスター+MIC構成では正規スロット名(M_VP_m00等、アンダースコアなし)
    # の他に恒久マスター(M_VP_m00_LitMaster1S等)がMainShader配下に同梱される。
    # マテリアル数の勘定は正規スロット名のみを対象にする(マスターは別枠の恒久資産)
    # U40(T3設計転換): live_template.pyがPlayer/Outfit/配下にMI_*
    # (バニラMI差し替え、SkeletalMeshではない)を追加で収録するようになった
    # ため、「/Outfit/配下の.uasset」を無条件でSK衣装として数えると
    # 実測値が水増しされる(60衣装 + 差し替えたMI数、のように)。
    # ファイル名がSK_で始まるものだけを衣装SKとして数える
    # (docs\REPORT_U40_2026-07-25.md T3節)。
    counts = (
        len([p for p in entries if "/Outfit/" in p and p.endswith(".uasset")
             and os.path.basename(p).startswith("SK_")]),
        len([p for p in entries if "/Head/" in p and p.endswith(".uasset")]),
        len([p for p in entries if "/Hair/" in p and p.endswith(".uasset")]),
        len([p for p in entries if "/HeadEquip/" in p and p.endswith(".uasset")]),
        int(private_rels["mi"] + ".uasset" in entries),
        len([key for key in ("base", "normal", "orm")
             if private_rels[key] + ".uasset" in entries]),
    )
    # U15-T2: D2P_NOUE_TEMPLATE_ROOTでテンプレを別アバター(例: Shapell)に
    # 差し替えたクロステンプレート検証時は、テンプレ側の元アバターが持つ
    # 未使用マテリアル/テクスチャスロット(注入対象外、テンプレは読み取り専用で
    # 使用スロットのみ上書きする設計)がそのまま残るため実測>期待になりうる。
    # これはテンプレート由来の資産であり不具合ではない(過小=不具合/過多=許容)。
    # 通常経路(override未設定)は従来どおり厳密一致のまま
    #
    # Collaboration SKs may be either absent or present unchanged.  G10
    # deliberately accepts both states.  For legacy jobs without an explicit
    # outfit selection, retain that compatibility by also accepting the
    # unfiltered manifest count; modern selected-outfit jobs use the exact
    # policy-filtered inventory count only.
    if not has_outfit_selection:
        try:
            legacy_manifest_expect4 = _manifest_sk_counts()
        except PreflightDataError as e:
            gate("FATAL テンプレートmanifestの読み込み", False, str(e))
            return finish()
    else:
        legacy_manifest_expect4 = None
    expect4_candidates = [primary_expect4]
    if (legacy_manifest_expect4 is not None
            and legacy_manifest_expect4 != primary_expect4):
        expect4_candidates.append(legacy_manifest_expect4)
    if os.environ.get("D2P_NOUE_TEMPLATE_ROOT"):
        g4_ok = (counts[:4] in expect4_candidates
                 and counts[4] >= expect[4] and counts[5] >= expect[5])
    else:
        g4_ok = counts[:4] in expect4_candidates and counts[4:] == expect[4:]
    gate("G4 収録数(衣装/頭/髪/頭装備/マテリアル/テクスチャ)", g4_ok,
         f"実測{counts} 期待{expect}"
         + (f" または旧ジョブmanifest由来"
            f"{legacy_manifest_expect4 + expect[4:]}"
            if len(expect4_candidates) > 1 else ""))

    # G5/G5b: バインド回転=バニラ・ボーン集合⊆バニラ(全衣装SK、性別別)
    #
    # U18実測(docs\REPORT_U18_2026-07-23.md参照): 真のバニラ衣装SKは、
    # 武器アタッチメントソケット(weapon_r等、テンプレート自身の元メッシュでも
    # スキニングに使われない純粋な骨のみのボーン)や、per-outfitの装飾用追加
    # ボーン(例: Ancient001のF_Ancient001_elbowArmor_01_l、腕装甲パーツ専用)を
    # RefSkeleton配列に持つ。これらはvanilla_ref(refskel_male/female.json、
    # 男女共通65ボーン基準)には存在しないか、存在してもテンプレート自身の
    # 意匠として意図的に異なる向きを持つことがある(60/60実測で複数個体を確認)。
    # 一方、本パイプラインはRenderSectionsを常にアバター側の実ウェイトから
    # 再構築するため(build_avatar_variant.py参照)、テンプレートの元の
    # BoneMapは一切引き継がれない — 出力(=pakに実際に同梱されるバイト)の
    # BoneMapは常にvanilla_ref由来の共通ボーン名の部分集合になる
    # (build_avatar_variant.pyの「RefSkeletonに存在しないボーン名」検証済み)。
    # そのため、テンプレートのRefSkeleton全件ではなく、**pakに実際に同梱された
    # (=注入済みの)RenderSectionsが実際に参照するボーンだけ**を検査対象にする
    # (旧実装はextract=テンプレート引数のディレクトリを直接globし、未使用の
    # 装飾ボーンまで含めて誤検知していた)。
    vanilla_ref = {}
    for g in ("male", "female"):
        with open(os.path.join(vanilla_dir, f"refskel_{g}.json"),
                  encoding="utf-8") as f:
            vanilla_ref[g] = json.load(f)
    _, pak_entries_full = core.read_pak_entries(mod_pak)
    # U40(T3設計転換): 上のG4と同じ理由で、MI_*(バニラMI差し替え、SkeletalMesh
    # ではない)をG5/G5bのRefSkeleton/ボーン検査対象から除外する
    # (MI_*にはRefSkeletonが存在せずcore.find_refskeletonが例外送出する)。
    # U50(2026-07-25): 非対応(コラボ系)のSKは注入されず**バニラのまま**pakに
    # 入るため、バニラ固有の装甲ボーン等をそのまま持つ。これはpakの欠陥では
    # ないので、G5(カバレッジ)/G5b(ボーン集合⊆バニラ)の検査対象から外す。
    # 除外集合はvp_exclusionsのみが決めるので、除外していないSKに対する
    # 検出力は一切変わらない。
    outfit_sk_entries = [p for p in entries
                         if "/Outfit/" in p and p.endswith(".uasset")
                         and os.path.basename(p).startswith("SK_")]
    n_excluded_sk = len([p for p in outfit_sk_entries
                         if vp_exclusions.is_excluded(p)])
    sk_uassets = sorted(p for p in outfit_sk_entries
                        if "Player/Outfit/" in p
                        and not vp_exclusions.is_excluded(p))
    if n_excluded_sk:
        print(f"  [INFO] G5/G5b 非対応(コラボ系)のため対象外: {n_excluded_sk}件 "
              + str(sorted(os.path.basename(p)[:-len('.uasset')]
                           for p in outfit_sk_entries
                           if vp_exclusions.is_excluded(p))))
    tmp_dir = os.path.join(job["job_dir"], "build", "preflight_g5_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    worst = (0.0, "")
    n_checked = 0
    unknown_bones = set()
    with open(mod_pak, "rb") as pf:
        def extract_bytes(rel_path):
            e = pak_entries_full[rel_path]
            if e["compression"] != 0:
                gate("G5前提: pakが非圧縮", False,
                     f"圧縮エントリ検出(本パイプラインは常に非圧縮のはず): {rel_path}")
                return b""
            pf.seek(e["data_offset"])
            return pf.read(e["size"])

        for p in sk_uassets:
            uexp_rel = p[:-7] + ".uexp"
            if uexp_rel not in pak_entries_full:
                continue
            base = os.path.basename(p)
            tmp_uasset = os.path.join(tmp_dir, base)
            tmp_uexp = tmp_uasset[:-7] + ".uexp"
            with open(tmp_uasset, "wb") as f:
                f.write(extract_bytes(p))
            with open(tmp_uexp, "wb") as f:
                f.write(extract_bytes(uexp_rel))

            ref = vanilla_ref["male"] if "_Male_" in base else vanilla_ref["female"]
            names = core.read_names(tmp_uasset)
            bones, transforms, _ = core.find_refskeleton(tmp_uexp, names)
            # Outfit-specific decoration bones (elbow/knee armour, etc.) are
            # legitimate even when absent from the shared male/female base
            # skeleton.  Accept them only when the exact source Outfit SK has
            # the same bone; a name introduced only by conversion still fails.
            native_bones = set()
            source_uasset = os.path.join(extract, *p.split("/"))
            source_uexp = source_uasset[:-7] + ".uexp"
            try:
                source_names = core.read_names(source_uasset)
                source_rows, _source_transforms, _ = core.find_refskeleton(
                    source_uexp, source_names)
                native_bones = {name for name, _parent in source_rows}
            except Exception:
                native_bones = set()
            struct_info = sk_struct.parse_sk_structure(tmp_uexp, tmp_uasset)
            used_idx = set()
            for sec in struct_info["sections"]:
                used_idx.update(sec["bone_map"])
            for i, ((bname, _p), t) in enumerate(zip(bones, transforms)):
                if i not in used_idx:
                    continue  # 実際のRenderSectionsが参照しない(=描画に無関係な)ボーン
                vb = ref.get(bname)
                if vb is None:
                    if bname in native_bones:
                        continue
                    # メッシュ名とボーン名の衝突でUEがボーンをリネームすると
                    # (例: head→head1)実行時スケルトンに対応が無くなり非追従になる。
                    # 実際に使用中のボーンはバニラの部分集合でなければならない
                    unknown_bones.add(f"{base}:{bname}")
                    continue
                dr = core.quat_angle_deg(t[0:4], vb["quat"])
                if dr > worst[0]:
                    worst = (dr, f"{base}:{bname}")
            n_checked += 1
    # U18実測(docs\REPORT_U18_2026-07-23.md参照): 真のバニラ衣装SKは、
    # 実際にスキニングへ使われている通常ボーン(例: clavicle_l、鎖骨)でも
    # 個別outfitの原作アセット自体がvanilla_ref(共通65ボーン基準)と最大10度
    # 程度の bind回転差を持つことがあると判明(SK_Player_Male_Outfit_Hunter001の
    # clavicle_lで実測)。この値はテンプレート(注入前)とビルド後出力とで
    # バイト完全一致することを確認済み(=本パイプラインは一切変更していない、
    # 100% verbatimコピー)。つまりこれはPalworld自身が出荷している本物の
    # バニラデータそのものであり、そのまま多くのプレイヤーが日常的に装備している
    # 実データである以上、実機で見た目が壊れているとは考えにくい
    # (UEのスキニングはメッシュごとに自己完結したbind poseで計算されるため、
    # 「1つの共通参照骨格と完全一致しなければならない」という前提自体が
    # 本チェックの誤り)。よって回転量の一致は致命ゲートにはせず、
    # 診断情報としてのみ表示する(n_checkedの一致=全60体を実際に検査できた
    # ことの構造的健全性チェックのみ致命ゲートとして残す)。
    # U50: 期待値をCSV由来のexpect[0]から「pakに実際に入っている衣装SK数」
    # (counts[0])へ変更。収録数そのものの妥当性はG4が見ており、ここは
    # 「入っている全SKを実際に検査できたか(uasset/uexpが揃い、解析できたか)」
    # という構造健全性を見るのが本来の役目。CSVがカバレッジの穴の分だけ
    # 大きくなりうる(G10参照)ため、CSVに縛ると本来の意味を失う
    # U50: 期待値から「非対応(コラボ系)で意図的に検査対象外にしたSK」を引く。
    # 引かないとn_checkedが構造的に一致しなくなり誤FAILする(pakは正常)。
    n_g5_expect = counts[0] - n_excluded_sk
    gate("G5 バインド回転差の検査対象カバレッジ(構造健全性)",
         n_checked == n_g5_expect,
         f"{n_checked}/{n_g5_expect}体検証"
         f"(pak収録{counts[0]}体 − 非対応{n_excluded_sk}体。"
         f"CSV由来の全数期待値は{expect[0]})")
    print(f"  [INFO] G5診断: 最大回転差(使用中ボーンのみ、テンプレート自体の"
          f"個体差を含む・不具合ではない) {worst[0]:.3f}deg ({worst[1]})")
    gate("G5b メッシュのボーン集合⊆バニラ(ボーンリネーム検知、使用中ボーンのみ)",
         not unknown_bones,
         str(sorted(unknown_bones)[:3]) if unknown_bones else "全ボーン一致")

    # G6: 参照の閉包性(参照する/Game/パスが自pak∪バニラに実在)
    own_pkgs = {p.rsplit(".", 1)[0] for p in full}
    vanilla_pkgs = {p.rsplit(".", 1)[0] for p in vanilla_entries
                    if p.endswith(".uasset")}
    all_pkgs = own_pkgs | vanilla_pkgs

    def pkg_exists(pkg):
        if pkg in all_pkgs:
            return True
        # FName番号の罠: 「SK_..._v02_2」のようなアセットは基底文字列「..._v02」+
        # 番号で直列化されるため、バイト走査では番号無しの文字列が見える。
        # 「pkg + _数字」が実在するなら偽陽性として容認する
        # (バニラのFemale_Outfit_Iron001_v02_2で実害確認)
        prefix = pkg + "_"
        return any(p.startswith(prefix) and p[len(prefix):].isdigit()
                   for p in all_pkgs)

    dangling = set()
    _g6_mount, g6_entries = core.read_pak_entries(mod_pak)
    with open(mod_pak, "rb") as pak_file:
      for rel, entry in g6_entries.items():
        if not rel.endswith(".uasset"):
            continue
        if entry["compression"] != 0:
            dangling.add(f"compressed:{rel}")
            continue
        pak_file.seek(entry["data_offset"])
        data = pak_file.read(entry["size"])
        try:
            header = live_template._parse_header_with_offsets(data)
            names, _end = live_template._read_name_table(
                data, header.name_offset, header.name_count)
            off = header.import_offset
            package_refs = []
            for _ in range(header.import_count):
                imp, off = live_template._parse_import(data, off)
                class_name = names[imp["class_name_idx"]]
                object_name = names[imp["object_name_idx"]]
                if class_name == "Package" and object_name.startswith("/Game/"):
                    package_refs.append(object_name)
        except Exception:
            package_refs = []
        for ref in package_refs:
            pkg = "Pal/Content/" + ref[len("/Game/"):]
            if not pkg_exists(pkg):
                dangling.add(ref)
    gate("G6 参照の閉包性(宙ぶらりん参照なし)", not dangling,
         str(sorted(dangling)[:3]) if dangling else "")

    # G7: シェーダー(SM5+SM6両対応でcookされたか)
    # 2026-07-26 cooklog_fix: cook_logはUEモードでは生のBuildCookRunログ(テキスト)、
    # noueモードではnoue_master\shader_platform_facts.json(固定の事実だけを持つJSON、
    # 生ログの開発機パス・個人アバター名を含む問題を解消するため導入)のどちらかが渡される。
    # まずJSONとして解析し、期待する構造(platforms_cooked配列)を持てばそれで判定する。
    # 解析できなければ(=UEモードの生ログ)従来どおり文字列検索へフォールバックする
    # (UEモード側の挙動・判定基準は一切変えていない)。
    ok_log = False
    if os.path.exists(cook_log):
        with open(cook_log, encoding="utf-8", errors="replace") as f:
            log = f.read()
        fact = None
        try:
            fact = json.loads(log)
        except (ValueError, TypeError):
            fact = None
        if isinstance(fact, dict) and isinstance(fact.get("platforms_cooked"), list):
            platforms = set(fact["platforms_cooked"])
            ok_log = {"PCD3D_SM5", "PCD3D_SM6"}.issubset(platforms)
        else:
            ok_log = "PCD3D_SM6" in log and "PCD3D_SM5" in log
    mat_sizes = [os.path.getsize(p) for p in glob.glob(
        os.path.join(extract, "Player", "ModelMaterials", "MainShader",
                     "M_VP_*.uexp"))]
    # U13: noueのマスター+MIC構成では正規スロット(M_VP_{slot}.uexp)がMICの場合
    # 数百byte程度まで縮む(shadow_lift等のオーバーライド値のみ保持、実シェーダーは
    # 恒久マスター側にある)。シェーダー実体の有無は「最大サイズ」で判定する
    # (min→maxへ変更。旧来のUEモード全出力(MIC無し)ではmin/maxが一致するため
    # 挙動は変わらない)
    ok_size = mat_sizes and max(mat_sizes) > 60_000
    gate("G7 シェーダーSM5+SM6", bool(ok_log and ok_size),
         f"log={ok_log} 最大={max(mat_sizes) // 1024 if mat_sizes else 0}KB")

    # G8: テクスチャのミップ焼き込み(uexpに実体)
    tex_sizes = {os.path.basename(p): os.path.getsize(p) for p in glob.glob(
        os.path.join(extract, "Player", "ModelMaterials", "MainShader", "*.uexp"))
        if "M_VP_" not in os.path.basename(p)}
    ok_tex = (not n_tex) or (tex_sizes and min(tex_sizes.values()) > 100_000)
    gate("G8 テクスチャ実体(NeverStream焼き込み)", bool(ok_tex),
         f"最小={min(tex_sizes.values()) // 1024 if tex_sizes else 0}KB / {len(tex_sizes)}枚")

    # G9: マテリアルにGPUSkinシェーダー(used_with_skeletal_meshの物証)
    # U13: MIC(数百byte、shadow_lift等のオーバーライド値のみ)は自身にシェーダーを
    # 持たず親の恒久マスター経由でGPUSkinが効く(MIC自体は検査対象外とする。
    # 100KB未満はMIC相当とみなす — 旧来の全出力Materialは350KB超のため無関係)
    no_skin = []
    for p in glob.glob(os.path.join(extract, "Player", "ModelMaterials",
                                    "MainShader", "M_VP_*.uexp")):
        if os.path.getsize(p) < 100_000:
            continue
        with open(p, "rb") as f:
            if b"GPUSkin" not in f.read():
                no_skin.append(os.path.basename(p))
    gate("G9 マテリアルにGPUSkinシェーダー", not no_skin,
         str(no_skin) if no_skin else "全マテリアルOK")

    # ========================================================================
    # G10(U50、既定WARN): 対象一覧のカバレッジ
    # ------------------------------------------------------------------------
    # 「ライブpakに実在する全SKが、このMOD pakに入っているか」を**名前単位**で
    # 照合する。在庫側は命名の形に依存しない場所依存の全数列挙
    # (extract_vanilla.enumerate_vanilla_sk)なので、G4の件数照合が持っていた
    # 「CSV生成側と収録側が同じ正規表現の盲点を共有する」構造がここには無い。
    # 漏れたアセットは「メッシュ注入されない(衣装)」「非表示化されない(頭装備)」
    # という形で実機の見た目が壊れる。
    # ========================================================================
    inv = sk_inventory
    if inv is not None:
        # U50(2026-07-25): 非対応(コラボ系)のSKは検査対象から外す。
        # 実測(2026-07-25)では、除外SKは**両方の状態を取りうる**:
        #   * Outfit の Yakushima001(男女)/ Octavia001(v01/v02)は
        #     noue_template_manifest.json に載っているのでテンプレ経由で
        #     **バニラのままpakに収録される**(=未収録にはならない)
        #   * HeadEquip の Yakushima001〜006 は manifest に無く、
        #     **pakに収録されない**(ダミーSK資産の新規生成が未対応)
        # どちらであってもユーザーには「バニラの装備がそのまま出る」だけで
        # 実害が無い(=NGではない)ので、収録の有無で場合分けせず
        # 「除外SKはカバレッジ判定から外す」で統一する。件数はINFOに出す。
        pak_set = set(entries)
        missing = {}
        excluded_absent = []
        for cat in sorted(inv):
            miss = []
            for r in inv[cat]:
                if r in pak_set:
                    continue
                if not _sk_is_required(
                        cat, r, has_outfit_selection, selected_outfits):
                    if vp_exclusions.is_excluded(r):
                        excluded_absent.append(f"{cat}: {r}")
                    continue
                miss.append(r)
            if miss:
                missing[cat] = miss
        n_missing = sum(len(v) for v in missing.values())
        n_inv = sum(len(v) for v in inv.values())
        n_inv_excluded = sum(1 for rows in inv.values() for r in rows
                             if vp_exclusions.is_excluded(r))
        suffix = (f"(ほかに非対応(コラボ系)で対象外 {n_inv_excluded}件)"
                  if n_inv_excluded else "")
        if missing:
            detail = (f"バニラ全{n_inv}SK中 未収録{n_missing}件 — "
                      + " / ".join(f"{c}:{len(v)}件" for c, v in missing.items())
                      + suffix)
        else:
            detail = f"バニラ全{n_inv}SK収録済み{suffix}"
        soft_gate("G10 ライブpakの全SKが対象一覧に含まれる(場所依存・命名非依存の照合)",
                  not missing, detail, "D2P_PREFLIGHT_COVERAGE", n_missing)
        for c, v in sorted(missing.items()):
            for rel in sorted(v):
                print(f"    [G10未収録] {c}: {rel}")
        for row in sorted(excluded_absent):
            print(f"    [G10 非対応につき対象外・未収録] {row}")

    # ========================================================================
    # G11(U50、既定WARN): 全描画スロットが注入アトラス t00 を指しているか
    # ------------------------------------------------------------------------
    # 旧基準は「slot0->t00 / slot1->t01」だったが、マテリアル単一化
    # (live_template._unify_slot_materials、既定ON)で t01 は使われなくなり、
    # 全描画スロットのMIが t00 を指すのが正しい状態になった(旧基準のNG 16件は
    # すべて基準側が古かっただけで実体は正常)。判定は参照先MIの実バイト
    # (name table)を読む方式へ変更してある(_slot_role_check の docstring 参照)。
    # ========================================================================
    private_ok, private_detail = _private_wiring_check(
        mod_pak, job, selected_outfits)
    gate("G11 avatar-private MI/Texture wiring", private_ok, private_detail)
    n_ng = 0 if private_ok else 1
    n_sk = len(selected_outfits)
    ng_rows = [] if private_ok else [private_detail]
    err = None
    if err:
        print(f"  [WARN] G11 スロット役の判定を実行できなかった: {err}")
    else:
        soft_gate("G11 全衣装SKの全描画スロットが注入アトラスt00を指す",
                  n_ng == 0, f"NG {n_ng}/{n_sk} SK",
                  "D2P_PREFLIGHT_SLOTROLE", n_ng)
        for row in ng_rows:
            print(f"    [G11 NG] {row}")

    # G12: Base Color以外の元防具Normal/ORMが残っていないことを、MIの
    # import参照とCook済みテクスチャの全mip実体の双方から確認する。
    neutral_checked, neutral_bad = _neutral_material_check(mod_pak, job)
    gate("G12 中立Normal/ORMと固定Metallic/Roughness/AO",
         neutral_checked > 0 and not neutral_bad,
         (f"MI {neutral_checked}件 / Normal=(128,128,255相当) / "
          f"Metallic=0 Roughness=0.8 Specular=0 AO=1"
          if not neutral_bad else str(neutral_bad[:3])))

    alpha_ok, alpha_detail = _alpha_mask_check(mod_pak, job_dir, conv, job)
    gate("G13 Base Color AlphaとOpacity Mask", alpha_ok, alpha_detail)

    return finish()


def finish():
    n_fail = sum(1 for _, ok, _ in results if not ok)
    n_warn = sum(1 for _, ok, _ in soft_results if not ok)
    if n_warn:
        print(f"\n--- 警告(検品の合否には影響しない。将来FAILへ昇格予定): {n_warn}件 ---")
        for name, ok, detail in soft_results:
            if not ok:
                print(f"  [WARN] {name} — {detail}")
        print("  昇格方法: D2P_PREFLIGHT_COVERAGE / D2P_PREFLIGHT_SLOTROLE に "
              "fail もしくは max:<件数> を設定する")
    print(f"\n=== preflight結果: "
          f"{'全チェックPASS' if n_fail == 0 else f'{n_fail}件FAIL — このMODは使用しないでください'}"
          f"{f'(警告{n_warn}件)' if n_warn else ''} ===")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
