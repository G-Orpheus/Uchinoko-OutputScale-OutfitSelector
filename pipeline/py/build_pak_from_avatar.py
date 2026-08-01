# -*- coding: utf-8 -*-
"""U6-T2: step02.blend → pak 一気通貫CLI(UE非依存パイプラインの本統合)。

1コマンドで以下を実行する(UnrealPak.exe不使用。同梱Blender+numpyのみ):
  1) 同梱Blender headlessで --step02-female/--step02-male を実アバターメッシュへ
     ダンプ(`research\\ue_exit\\dump_avatar_mesh.py`、無改変・そのまま呼び出し)
  2) 衣装SK 60体へ性別別に実アバターを注入
     (`research\\ue_exit\\build_avatar_variant_all.py`の
     `collect_targets`/`gender_of`/`build_and_validate`をimport再利用、無改変)
  3) 残り375件(スタブ153+マテリアル+テクスチャ+アンカー等)は
     --template からそのままコピー
  4) `vp_pakwrite.py`(U6-T1、本ファイルと同じpipeline\\py配下、新規)でpak化
     (UnrealPak不使用)
  5) `preflight_pak.py`を自動実行して結果を表示

既存ファイル(vp_core.py/vp_meshrestore.py/preflight_pak.py/
research\\ue_exit\\build_avatar_variant*.py/dump_avatar_mesh.py)は一切変更しない。
本ファイルはそれらをimport/subprocessで呼び出すだけの新規オーケストレータ
(pipeline\\py\\restore_full.pyと同じ設計方針)。

実行例:
  python build_pak_from_avatar.py \\
      --step02-female work\\toto\\converted\\step02_female.blend \\
      --step02-male   work\\alicia\\converted\\step02_male.blend \\
      --template work\\toto\\build\\pak_extract \\
      --out out\\avatar.pak
  (--job-jsonの既定値はwork\\toto系。他jobで使う場合は明示指定。
   --cook-logの既定値はpipeline\\py\\noue_master\\shader_platform_facts.json
   (noueモード共通の固定事実ファイル、2026-07-26 cooklog_fix)。UEモードの実cookログを
   使いたい場合のみ明示指定する)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))       # pipeline\py
PIPELINE_DIR = os.path.dirname(HERE)                     # pipeline\
REPO_DIR = os.path.dirname(PIPELINE_DIR)                 # リポジトリルート

sys.path.insert(0, HERE)
import vp_exclusions  # noqa: E402
import outfit_selection  # noqa: E402
import vp_pakwrite  # noqa: E402
import vp_texinject  # noqa: E402
import avatar_assets  # noqa: E402
# U51(research\ue_exit→pipeline\py移設): build_avatar_variant*.py/dump_avatar_mesh.py
# は元research\ue_exit\から無改変のままpipeline\py\へコピーされ、以降はHEREから
# 直接import/参照する(research\ue_exit\側は開発参照用に残置、実行時には見ない)
from build_avatar_variant import load_dump  # noqa: E402
from build_avatar_variant_all import (  # noqa: E402
    build_and_validate, collect_targets, gender_of,
)

TAG = "build_pak_from_avatar"

DEFAULT_BLENDER_EXE = (
    r"C:\P\Work\PalMod\tools\blender-4.3.2-windows-x64\blender.exe")
DEFAULT_DUMP_SCRIPT = os.path.join(HERE, "dump_avatar_mesh.py")
DEFAULT_PREFLIGHT = os.path.join(HERE, "preflight_pak.py")
DEFAULT_JOB_JSON = os.path.join(REPO_DIR, "work", "toto", "job.json")
# 2026-07-26 cooklog_fix: 旧既定値 work\toto\build\logs\cook.log は開発機にしか無い上
# 個人アバター名"toto"を含んでいた。noueモードでpreflightが本来参照すべきは
# pipeline\py\noue_master\shader_platform_facts.json(SM5/SM6双方でcook済みという
# 固定の事実、live_template.COOK_LOGと同じ実体)であり、これはリポジトリにも配布物にも
# 常に存在するため、スタンドアロン実行時の既定値として妥当(convert_noue.py経由の
# 通常実行では--cook-logが明示的に上書きされるため、この既定値は直接呼び出し時のみ使う)。
DEFAULT_COOK_LOG = os.path.join(HERE, "noue_master", "shader_platform_facts.json")

# U6-T3(ストレッチ): avatar_meta.json実測(m00=body/t00.png, m01=parka/t01.png、
# docs\REPORT_U5_2026-07-23.md T1b節参照)固定のテクスチャスロット対応
TEX_SLOT_REL = {
    "body": "Player/ModelMaterials/MainShader/t00.uexp",
    "parka": "Player/ModelMaterials/MainShader/t01.uexp",
}


def die(msg):
    print(f"[{TAG}][FATAL] {msg}")
    sys.exit(1)


def run(cmd, log_path):
    """subprocessを実行し、ログをファイルへ保存する。失敗したら末尾を出して停止する。
    (restore_full.py の run() と同じ流儀)"""
    print(f"[{TAG}] $ {' '.join(cmd)}")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        tail = ""
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                tail = f.read()[-3000:]
        except OSError:
            pass
        die(f"コマンド失敗 exit={r.returncode} (ログ: {log_path})\n"
            f"--- ログ末尾 ---\n{tail}")
    print(f"[{TAG}]   -> OK (ログ: {log_path})")


def main():
    ap = argparse.ArgumentParser(
        description="step02_{gender}.blend + テンプレpak_extract から "
                     "ゲームに入れられるpakを1コマンドで生成する(UnrealPak不使用)")
    ap.add_argument("--step02-female", required=True)
    ap.add_argument("--step02-male", required=True)
    ap.add_argument("--template", required=True,
                    help="pak_extractディレクトリ(435ファイル、性別衣装SK込み)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--blender", default=DEFAULT_BLENDER_EXE, help="Blender本体exe")
    ap.add_argument("--work", default=None,
                    help="作業ディレクトリ(ダンプ/中間生成物の置き場所)。"
                         "省略時は一時ディレクトリを新規作成する")
    ap.add_argument("--max-influences", type=int, default=8)
    ap.add_argument("--job-json", default=DEFAULT_JOB_JSON,
                    help="preflight_pak.py用job.json")
    ap.add_argument("--cook-log", default=DEFAULT_COOK_LOG,
                    help="preflight_pak.py用cook_log(UEモード:実cookログ / "
                         "noueモード:noue_master\\shader_platform_facts.json)")
    ap.add_argument("--skip-preflight", action="store_true")
    ap.add_argument("--tex-body", default=None,
                    help="U6-T3(ストレッチ): body(t00)スロットへ注入するPNG。"
                         "テンプレートと異なる解像度は自動リサイズ(ニアレストネイバー)")
    ap.add_argument("--tex-parka", default=None,
                    help="U6-T3(ストレッチ): parka(t01)スロットへ注入するPNG")
    ap.add_argument("--tex-body-alpha-coverage", action="store_true",
                    help="FIX2(2026-07-24): bodyテクスチャのミップ生成で"
                         "アルファカバレッジを保存する(avatar_meta.jsonの"
                         "alpha_mode==MASKスロット向け)")
    ap.add_argument("--tex-parka-alpha-coverage", action="store_true",
                    help="FIX2(2026-07-24): parkaテクスチャのミップ生成で"
                         "アルファカバレッジを保存する")
    ap.add_argument("--tex-gain", type=float, default=1.0,
                    help="U49(2026-07-25): 注入テクスチャ(body/parka共通)へ"
                         "掛ける明度ゲイン(shadow_lift接続、"
                         "vp_texinject.shadow_lift_gain()参照)。既定1.0=無補正"
                         "(従来どおりのピクセル列、convert_noue.pyがjob.jsonの"
                         "shadow_liftから計算して渡す)")
    ap.add_argument("--mat-override-dir", default=None,
                    help="U13: スロット別マテリアル(M_VP_{slot}.uasset/uexp)の"
                         "差し替え元ディレクトリ。convert_noue.pyがバリアント選択+"
                         "shadow_liftバイトパッチ済みのファイルを置く")
    ap.add_argument("--mi-override-dir", default=None,
                    help="U50-fast(2026-07-26): 影の濃さ(shadow_lift)を焼き込んだ"
                         "統一MIの差し替え元ディレクトリ。--mat-override-dirと違い"
                         "**pak内相対パスと同じ木構造**で置かれている"
                         "(Player/Outfit/.../MI_*.uasset 等)。"
                         "live_template.build_shadow_mi_overrides()が生成し、"
                         "convert_noue.pyが渡す。k=0(影の濃さ0)のときは1件も"
                         "生成されず、この引数自体が渡らない")
    args = ap.parse_args()

    step02_female = os.path.abspath(args.step02_female)
    step02_male = os.path.abspath(args.step02_male)
    template = os.path.abspath(args.template)
    out_pak = os.path.abspath(args.out)
    blender_exe = os.path.abspath(args.blender)

    output_scale = 1.0
    job_cfg = {}
    if args.job_json and os.path.exists(args.job_json):
        with open(args.job_json, encoding="utf-8") as f:
            job_cfg = json.load(f)
            output_scale = float(job_cfg.get("output_scale", 1.0))
    if not (0.01 <= output_scale <= 100.0):
        die(f"output_scaleは0.01〜100.0で指定してください: {output_scale}")
    print(f"[{TAG}] 出力倍率: {output_scale}")

    for p, label in ((step02_female, "--step02-female"), (step02_male, "--step02-male"),
                     (template, "--template"), (blender_exe, "--blender")):
        if not os.path.exists(p):
            die(f"{label}が存在しない: {p}")

    work = os.path.abspath(args.work) if args.work else tempfile.mkdtemp(
        prefix="d2p_build_pak_from_avatar_")
    os.makedirs(work, exist_ok=True)
    log_dir = os.path.join(work, "logs")
    dump_dir = os.path.join(work, "dump")
    variant_dir = os.path.join(work, "variant")
    os.makedirs(dump_dir, exist_ok=True)
    print(f"[{TAG}] 作業ディレクトリ: {work}")

    # === Phase 1: Blender headlessで両性別をダンプ ===
    # WP-B3(2026-07-28): dump_avatar_mesh.py内のmesh.calc_tangents()
    # (Blender内蔵mikktspace)がBlenderのタスクスケジューラ(BLI_task)の
    # マルチスレッド評価に起因して実行のたびに1e-6オーダーで結果がブレる
    # ことを実測で確認した(同一.blend・同一スクリプトを単独プロセスで
    # 逐次2回実行しても、特定頂点のtangent成分だけが最終桁で相違。
    # pos/normal/uv/weightsは常に完全一致)。この揺れがbuild_avatar_variant.py
    # のencode_tangent_pair()での8bit量子化の境界をたまたま跨ぐと、
    # Outfit衣装SKのuexpが1バイトだけ変化し、pakのSHA256が実行ごとに
    # non-deterministicになる(release.py v1.1.4試行 run_20260728_054403で
    # 実際に発生、prefab_flatapronのOutfit系uexp 29件が変更ありでFAIL)。
    # `-t 1`(Blender CLIオプション、BLI_taskのスレッド数を1に固定)を
    # 付けた場合のみ、同一検証手順で3回連続バイト完全一致を確認済み。
    # calc_tangents()を呼ぶBlender起動はこのdump_avatar_mesh.py呼び出し
    # 1箇所だけ(pipeline全体をgrep済み、他のBlender工程は呼んでいない)
    # なので、ここにだけ限定して付与する(全Blender工程に付けると遅くなる)。
    dump_blender_args = ["-t", "1"]
    dumps = {}
    for gender, blend in (("Female", step02_female), ("Male", step02_male)):
        out_json = os.path.join(dump_dir, f"avatar_{gender.lower()}.json")
        print(f"[{TAG}] === Phase 1: {gender}ダンプ ===")
        run([blender_exe, "--background", "--factory-startup", *dump_blender_args,
             "--python-exit-code", "1", "--python",
             DEFAULT_DUMP_SCRIPT, "--", blend, gender, out_json, str(args.max_influences),
             os.path.join(os.path.dirname(blend), "avatar_meta.json"), str(output_scale)],
            os.path.join(log_dir, f"dump_{gender}.log"))
        if not os.path.exists(out_json):
            die(f"{gender}ダンプの出力が無い: {out_json}")
        dumps[gender] = load_dump(out_json)
        # U21: RefSkeletonバインドポーズ位置パッチ(build_avatar_variant.py
        # load_chibi_bone_world_head参照)向けに、真のjob_dir/convertedの
        # 場所を明示的に渡す。dump['source_blend']はUVアトラス焼き込み後の
        # blend(work/<job>/build/atlas/step02_{gender}_atlas.blend)を指して
        # おり、pipeline/blender/step02_retarget.pyがchibi_bone_world_head_
        # {gender}.jsonを書き出す本来のconvertedディレクトリ
        # (work/<job>/converted/)とは別の場所になる(U21初回実装で発覚した
        # バグ: source_blendのdirnameから逆算すると見つからず、パッチが
        # 常にサイレントno-opになっていた)。job.jsonの場所から直接
        # job_dir/convertedを解決する方が確実なので、こちらを明示的に渡す。
        dumps[gender]['_job_converted_dir'] = os.path.join(
            os.path.dirname(os.path.abspath(args.job_json)), "converted")

    # === Phase 2: 衣装SK 60体へ性別別に実アバターを注入 ===
    print(f"[{TAG}] === Phase 2: 衣装SKへの実アバター注入 ===")
    outfit_root = os.path.join(template, "Player", "Outfit")
    pairs = collect_targets(outfit_root)
    # U40(T3設計転換): live_template.pyがPlayer/Outfit/配下にMI_*(バニラMI
    # 差し替え、SkeletalMeshではない)を追加で置くようになったため、
    # collect_targets(拡張子のみでの機械的な.uexp/.uassetペア収集、
    # research\ue_exit\build_avatar_variant_all.py、無改変維持)がそれも
    # 「衣装SK」として拾ってしまう。MI_*はメッシュではなくindex bufferを
    # 持たないため実アバター注入は必ず失敗する(意図通り、対象外)。
    # ファイル名がSK_で始まるものだけを注入対象とし、MI_*はここで除外して
    # Phase 3の「残りはテンプレートのままコピー」経路に委ねる
    # (=T3パッチ済みのバイト列がそのまま最終pakへ入る)。
    before_filter = len(pairs)
    pairs = [(u, a) for u, a in pairs if os.path.basename(u).startswith("SK_")]
    n_excluded_mi = before_filter - len(pairs)
    if n_excluded_mi:
        print(f"[{TAG}] T3: MI_*(バニラMI差し替え、非メッシュ){n_excluded_mi}件を"
              f"実アバター注入対象から除外(テンプレートのままpakへ収録)")
    # U50(2026-07-25、責任者裁定「コラボ系アイテムは非対応です」):
    # 除外対象のSKには実アバターを注入しない。注入しなければ Phase 3 の
    # 「残りはテンプレートのままコピー」経路に乗り、**バニラの装備がそのまま
    # 出る**(方針「失敗するにしても優雅に失敗する」)。
    # 正本は pipeline\py\vp_exclusions.py(そこへ足せば全経路に効く)。
    kept = []
    excluded = []
    for u, a in pairs:
        if vp_exclusions.is_excluded(u):
            excluded.append(u)
        else:
            kept.append((u, a))
    pairs = kept
    known_outfits = outfit_selection.catalog()
    try:
        selected_outfits = outfit_selection.selected(job_cfg, known_outfits)
    except ValueError as e:
        die(str(e))
    pairs = [(u, a) for u, a in pairs
             if outfit_selection.normalize_id(
                 os.path.relpath(a, template).replace("\\", "/")) in selected_outfits]
    if excluded:
        print(f"[{TAG}] 非対応(コラボ系)のため注入しないSK {len(excluded)}件 "
              f"= バニラの装備がそのまま出る:")
        for u in excluded:
            print(f"[{TAG}]   - {os.path.basename(u)} "
                  f"({vp_exclusions.excluded_reason(u)})")
    print(f"[{TAG}] 対象SK: {len(pairs)}件")
    targets_rel = []
    n_fail = 0
    gender_counts = {"Male": 0, "Female": 0}
    for uexp_path, uasset_path in pairs:
        rel_uexp = os.path.relpath(uexp_path, template).replace("\\", "/")
        fn = os.path.basename(uexp_path)
        gender = gender_of(fn)
        gender_counts[gender] += 1
        dump = dumps[gender]
        out_uexp = os.path.join(variant_dir, rel_uexp)
        out_uasset = out_uexp[:-5] + ".uasset"
        try:
            ok, errs, info = build_and_validate(uexp_path, uasset_path, dump, out_uexp, out_uasset)
        except Exception as e:
            ok, errs, info = False, [str(e)], {}
        status = "OK" if ok else "FAIL"
        print(f"[{TAG}] [{status}] {rel_uexp} gender={gender} "
              f"numv={info.get('num_vertices')} tri={info.get('num_triangles')}" +
              (f" errs={errs}" if errs else ""))
        if not ok:
            n_fail += 1
        else:
            targets_rel.append(rel_uexp)
    if n_fail:
        die(f"衣装SK注入が{n_fail}件失敗した(詳細は上のログ参照)")
    print(f"[{TAG}] 衣装SK注入: {len(targets_rel)}/{len(pairs)}件成功 "
          f"(gender_counts={gender_counts})")

    # === Phase 2b(U6-T3ストレッチ): テクスチャ注入 ===
    tex_dir = os.path.join(work, "tex")
    tex_args = {"body": args.tex_body, "parka": args.tex_parka}
    tex_alpha_coverage = {"body": args.tex_body_alpha_coverage,
                           "parka": args.tex_parka_alpha_coverage}
    tex_replace = {}
    for slot, png_path in tex_args.items():
        if not png_path:
            continue
        png_path = os.path.abspath(png_path)
        if not os.path.exists(png_path):
            die(f"--tex-{slot}が存在しない: {png_path}")
        rel = TEX_SLOT_REL[slot]
        template_uexp = os.path.join(template, *rel.split("/"))
        out_uexp = os.path.join(tex_dir, rel)
        print(f"[{TAG}] === Phase 2b: テクスチャ注入({slot}: {png_path}) ===")
        info = vp_texinject.inject_texture_file(
            template_uexp, png_path, out_uexp,
            alpha_coverage=tex_alpha_coverage[slot], gain=args.tex_gain)
        print(f"[{TAG}]   {rel}: {info['pixel_format']} {info['size_x']}x{info['size_y']} "
              f"PSNR={info['psnr']:.2f}dB gain={info['gain']:.4f}"
              f"(version={info['gain_version']})")
        print(f"[{TAG}]   Alpha: input min={info['input_alpha']['min']} "
              f"max={info['input_alpha']['max']} "
              f"transparent={info['input_alpha']['transparent']} -> "
              f"final {info['pixel_format']} transparent="
              f"{info['output_alpha']['transparent']} / "
              f"MI BlendMode={info['blend_mode']} "
              f"OpacityMask={info['opacity_mask']} "
              f"Clip={info['opacity_mask_clip_value']}")
        tex_replace[rel] = out_uexp

    # === Phase 2c(U13): マテリアル差し替え(バリアント選択+shadow_liftパッチ済み) ===
    mat_override = {}
    if args.mat_override_dir:
        mo_dir = os.path.abspath(args.mat_override_dir)
        for fn in sorted(os.listdir(mo_dir)):
            rel = f"Player/ModelMaterials/MainShader/{fn}"
            mat_override[rel] = os.path.join(mo_dir, fn)
        print(f"[{TAG}] マテリアル差し替え: {len(mat_override)}件 ({mo_dir})")

    # === Phase 2d(U50-fast): 影の濃さ(shadow_lift)を焼き込んだ統一MIの差し替え ===
    # Phase 2c と同じ「後段でMIファイルを差し替える」形。違いは木構造で置かれて
    # いる点だけ(相対パスがそのままpak内パスになる)。これにより shadow_lift は
    # ライブテンプレート(879ファイル/約700MB)の再構築を必要としない。
    mi_override = {}
    if args.mi_override_dir:
        mi_dir = os.path.abspath(args.mi_override_dir)
        for dirpath, _d, filenames in os.walk(mi_dir):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, mi_dir).replace("\\", "/")
                mi_override[rel] = p
        print(f"[{TAG}] 影の濃さMI差し替え: {len(mi_override)}件 ({mi_dir})")

    # === Phase 3: pak化(残り375件はテンプレートのまま、vp_pakwriteでpak化) ===
    print(f"[{TAG}] === Phase 3: pak化(mount={vp_pakwrite.DEFAULT_MOUNT}) ===")
    private_root = os.path.join(work, "avatar_assets")
    try:
        private_files, private_info = avatar_assets.build_private_assets(
            job_cfg, template, selected_outfits, variant_dir,
            tex_replace.get(TEX_SLOT_REL["body"]), mi_override, private_root)
    except avatar_assets.AvatarAssetError as e:
        die(f"avatar-private Material/Texture build failed: {e}")
    print(f"[{TAG}] avatar-private assets: namespace={private_info['namespace']} "
          f"SK={private_info['selected_sk']} slots={private_info['material_slots']} "
          f"MI={private_info['paths']['mi']}")

    all_files = outfit_selection.filter_pak_files(
        vp_pakwrite.collect_files(template), template, selected_outfits,
        known_outfits, private_materials=True)
    all_files = [
        (src, rel) for src, rel in all_files
        if not rel.replace("\\", "/").startswith(
            "Player/ModelMaterials/MainShader/")
        and rel.replace("\\", "/") not in {
            "Player/Body/Male/MI_Player_Male_Body.uasset",
            "Player/Body/Male/MI_Player_Male_Body.uexp",
            "Player/Body/Female/MI_Player_Female_Body.uasset",
            "Player/Body/Female/MI_Player_Female_Body.uexp",
        }
    ]
    replace_map = {}
    for rel_uexp in targets_rel:
        rel_uasset = rel_uexp[:-5] + ".uasset"
        replace_map[rel_uexp] = os.path.join(variant_dir, rel_uexp)
        replace_map[rel_uasset] = os.path.join(variant_dir, rel_uasset)
    allowed_replacements = {rel for _src, rel in all_files}
    replace_map = {rel: src for rel, src in replace_map.items()
                   if rel in allowed_replacements}

    final_files = []
    n_replaced = 0
    for src, rel in all_files:
        if rel in replace_map:
            final_files.append((replace_map[rel], rel))
            n_replaced += 1
        else:
            final_files.append((src, rel))
    final_files.extend(private_files)
    if n_replaced != len(replace_map):
        die(f"差し替え対象{len(replace_map)}件のうち{n_replaced}件しか一致しなかった")

    os.makedirs(os.path.dirname(out_pak) or ".", exist_ok=True)
    info = vp_pakwrite.build_pak(final_files, out_pak)
    print(f"[{TAG}] pak生成: {out_pak} "
          f"(総エントリ{info['n_entries']}件, 差し替え{n_replaced}件, size={info['size']})")

    # === Phase 4: preflight_pak.py 自動実行 ===
    if args.skip_preflight:
        print(f"[{TAG}] --skip-preflight指定のためpreflightをスキップ")
    else:
        job_json = os.path.abspath(args.job_json)
        cook_log = os.path.abspath(args.cook_log)
        if not (os.path.exists(job_json) and os.path.exists(cook_log)):
            print(f"[{TAG}] job.json/cook.logが見つからないためpreflightをスキップ"
                  f"(job_json={job_json} cook_log={cook_log}。"
                  "--job-json/--cook-logで明示指定してください)")
        else:
            print(f"[{TAG}] === Phase 4: preflight_pak.py ===")
            r = subprocess.run([sys.executable, DEFAULT_PREFLIGHT, job_json,
                                out_pak, template, cook_log])
            if r.returncode != 0:
                die(f"preflight_pak.pyが{r.returncode}で終了(上の出力参照)")

    print(f"[{TAG}] done: {out_pak}")
    print(f"[{TAG}] 作業ディレクトリ(ダンプ/中間生成物/ログ): {work}")


if __name__ == "__main__":
    main()
