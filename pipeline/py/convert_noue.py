# -*- coding: utf-8 -*-
"""U12: convert.ps1のnoueモード(既定、UE不要)から呼ばれるグルー。

step01/02(convert.ps1が共用のBlender工程として既に実行済み)の成果である
converted\\step02_{female,male}.blend から、build_pak_from_avatar.py 1本で
ゲーム投入可能なpakまで仕上げる(UnrealPak.exe/UEエディタ不使用)。

既存コア(build_pak_from_avatar.py/vp_pakwrite.py/vp_texinject.py/
extract_vanilla.py/step01_import_vrm.py/step02_retarget.py)は無改変。
本ファイルはbuild_pak_from_avatar.pyをimportしてmain()をsys.argv経由で
呼び出す(U11の_u11_quarantine_run.pyと同じ再利用パターン)だけの新規
オーケストレータ。プロセスを跨がないため、vp_core.DEFAULT_UE_ROOTの
quarantine(UnrealPak不在の動的証明)がbuild_pak_from_avatar.py内部まで
一貫して効く。

テンプレート/参照バニラ/参照cook.log/マテリアルバリアントの解決順(U18改訂、
旧U14の①同梱テンプレは廃止 — Palworld著作物を含むため配布不可と判明したため):
  ①環境変数override(`D2P_NOUE_TEMPLATE_ROOT`、開発/検証専用フック、従来どおり)
  ②ライブ抽出(新規・既定。`live_template.py`経由でユーザー自身のPalworld
    インストールからその場組み立てる。事前cook済みテンプレフォルダ不要)
  ③開発機フォールバック(リポジトリ内`work\\toto\\build`等、ライブ抽出が
    使えない場合の開発時フォールバック)
いずれも使えなければエラー。`D2P_NOUE_LIVE_ONLY=1`でライブ抽出のみを強制できる
(③へのフォールバックを禁止するテストモード、docs\\REPORT_U18_2026-07-23.md参照)。

使い方: python convert_noue.py <job.json>
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))       # pipeline\py
PIPELINE_DIR = os.path.dirname(HERE)                     # pipeline\
REPO_DIR = os.path.dirname(PIPELINE_DIR)                 # リポジトリルート(=配布物ではアプリルート)

sys.path.insert(0, HERE)
import vp_core as core  # noqa: E402
import build_pak_from_avatar  # noqa: E402
import extract_vanilla  # noqa: E402 (U54: 抽出のキャッシュ判定を共有する)
import live_template  # noqa: E402 (U18: ライブテンプレ組み立て)
import vp_atlas  # noqa: E402 (U16: マテリアルアトラス化コア)
import vp_tex  # noqa: E402 (U16: アトラス合成PNGの書き出しに使用)
import vp_provenance  # noqa: E402 (U34: ビルド来歴スタンプ)
import vp_texinject  # noqa: E402 (U49: shadow_lift接続の明度ゲイン計算)

TAG = "convert_noue"

# U14-T2検証専用フック: 環境変数D2P_QUARANTINE_UE_ROOTが設定されていれば
# vp_core.DEFAULT_UE_ROOTをそれで上書きする(U11/U12方式のUE不在動的証明を
# convert.ps1経由の実行でも行えるようにするため。未設定時は何もしない=
# 通常経路に影響なし)
_quarantine_ue_root = os.environ.get("D2P_QUARANTINE_UE_ROOT")
if _quarantine_ue_root:
    core.DEFAULT_UE_ROOT = _quarantine_ue_root
    print(f"[{TAG}] UE quarantine有効: vp_core.DEFAULT_UE_ROOT -> {_quarantine_ue_root}")

# U18: extract_vanilla.py(U17でUnrealPak不使用・ライブ抽出化済み)をサブプロセスで
# 呼び、ライブ抽出モードのバニラ参照データ(refskel/複製リスト/pak全エントリ)を
# job配下へ直接生成する
EXTRACT_VANILLA_PY = os.path.join(HERE, "extract_vanilla.py")
# 開発機フォールバック(リポジトリ内、従来どおり。U6〜U13で実証済みの
# 開発側cook済み資産をそのまま参照する。ライブ抽出(pakが無い等)が使えない
# 場合のみ使う)
DEV_BUILD_DIR = os.path.join(REPO_DIR, "work", "toto", "build")
DEV_VANILLA_DIR = os.path.join(REPO_DIR, "work", "toto", "vanilla")
# U16: マテリアルアトラス化(3枚以上マテリアルを持つアバターの見た目崩れ対策)の
# UV焼き込みをBlender headlessで行うスクリプト(vp_atlas.py/vp_atlas_uvbake.py
# 参照。詳細設計はvp_atlas.pyのモジュールdocstring)
VP_ATLAS_UVBAKE_PY = os.path.join(HERE, "vp_atlas_uvbake.py")
# U50-single: 焼き込み後のUVで実際にレンダリングして絵を突き合わせる受入ゲート
RENDER_ATLAS_CHECK_PY = os.path.join(
    os.path.dirname(HERE), "blender", "render_atlas_check.py")


def resolve_vanilla_source(job):
    """**参照バニラデータの供給元だけ**を決める軽量版(U54)。

    resolve_noue_assets() は②ライブ抽出のときテンプレート本体
    (447ファイル/約700MB)をその場で組み立てる。ところが `--ensure-vanilla`
    (convert.ps1のPhase 0)が要るのは「live か copy か」「copyならどこから」
    だけで、テンプレートは1つも要らない。-PreviewOnly では最後まで要らない。
    そこで判定だけをこちらへ切り出し、resolve_noue_assets() からも呼ぶ
    (順序・条件の二重実装を作らないため)。

    戻り値: {"kind": "override"|"live"|"dev", "vanilla_mode": "live"|"copy",
             "vanilla_ref"(copyのみ), "root"(overrideのみ), "source"}
    """
    override_root = os.environ.get("D2P_NOUE_TEMPLATE_ROOT")
    if override_root:
        return {
            "kind": "override",
            "vanilla_mode": "copy",
            "vanilla_ref": os.path.join(override_root, "vanilla"),
            "root": override_root,
            "source": f"override({override_root})",
        }

    live_only = os.environ.get("D2P_NOUE_LIVE_ONLY") == "1"
    pak = job["paths"].get("palworld_pak")
    if pak and os.path.exists(pak):
        return {"kind": "live", "vanilla_mode": "live", "source": "live_extract"}
    if live_only:
        die(f"D2P_NOUE_LIVE_ONLY=1だがPalworldのpakが見つからない: {pak}"
            "(③開発機フォールバックへの逃げを禁止するテストモードのため停止)")

    # WP16(公開issue #8 追加報告): ③開発機フォールバックは、開発機に実際に
    # dev vanillaが用意されているとき(=このリポジトリで開発中)だけ許可する。
    # 配布版にはwork\toto\vanillaが同梱されないため、このディレクトリが
    # 実在しない=一般ユーザー環境だと判断できる。その場合は③へ静かに落ちず、
    # 真因(Palworldのpakが見つからない)をそのまま停止理由にする
    # (従来は③へ落ちた後、ensure_vanilla()が開発専用パスの「参照バニラデータが
    # 無い」という、真因と無関係に見える内部パスのエラーで止まっていた)。
    dev_ref_version = os.path.join(DEV_VANILLA_DIR, "version.txt")
    if os.path.exists(dev_ref_version):
        return {
            "kind": "dev",
            "vanilla_mode": "copy",
            "vanilla_ref": DEV_VANILLA_DIR,
            "source": "dev_fallback",
        }

    detail = job.get("_palworld_pak_search_error") or (
        f"Palworldのpakが見つからない: {pak}\n"
        "job.jsonのpaths.palworld_pakを設定してください")
    die(detail)


def resolve_noue_assets(job):
    """テンプレ資産一式のパスを解決する。①環境変数override → ②ライブ抽出(新規・既定)
    → ③開発機フォールバックの順。
    戻り値: {"template","cook_log","variants","source",
             "vanilla_mode":"live"|"copy", "vanilla_ref"(copyモードのみ)}

    ①はU15-T2検証専用フック: 環境変数D2P_NOUE_TEMPLATE_ROOTが設定されていれば
    そのディレクトリ(work\\<avatar>\\相当、直下にbuild\\pak_extract等がある構成)を
    テンプレとして使う。特定avatarの変換1回だけ別テンプレ(例: Shapell由来)を
    試すための一時フック(未設定時は何もしない=通常経路に影響なし)。

    ②はU18: `live_template.build_live_template()`(U17産pak_live_extract.py
    ベース)でユーザー自身のPalworldインストールのpakからその場組み立てる。
    事前cook済みテンプレフォルダが一切無くても成立する(既定経路)。
    環境変数D2P_NOUE_LIVE_ONLY=1が設定されていれば、pakが無い等でライブ抽出が
    使えない場合に③開発機フォールバックへ逃げず即エラーにする(3節の安全制約:
    work\\のリネームの代わりにこのフラグでテストする)。

    U54: ①②③の判定そのものは resolve_vanilla_source() へ切り出した
    (テンプレート組み立てを伴わない軽量版が --ensure-vanilla で要るため)。
    ここは判定結果にテンプレ資産のパスを足すだけで、順序も条件も従来どおり。"""
    src = resolve_vanilla_source(job)

    if src["kind"] == "override":
        override_build = os.path.join(src["root"], "build")
        return {
            "template": os.path.join(override_build, "pak_extract"),
            "cook_log": os.path.join(override_build, "logs", "cook.log"),
            "vanilla_mode": "copy",
            "vanilla_ref": src["vanilla_ref"],
            "variants": os.path.join(override_build, "noue_variants"),
            "source": src["source"],
        }

    if src["kind"] == "live":
        template_dir = live_template.build_live_template(job)
        return {
            "template": template_dir,
            "cook_log": live_template.COOK_LOG,
            "vanilla_mode": "live",
            "variants": live_template.VARIANTS_DIR,
            "source": src["source"],
        }

    return {
        "template": os.path.join(DEV_BUILD_DIR, "pak_extract"),
        "cook_log": os.path.join(DEV_BUILD_DIR, "logs", "cook.log"),
        "vanilla_mode": "copy",
        "vanilla_ref": src["vanilla_ref"],
        "variants": os.path.join(DEV_BUILD_DIR, "noue_variants"),
        "source": src["source"],
    }


def die(msg):
    print(f"[{TAG}][FATAL] {msg}")
    sys.exit(1)


def ensure_vanilla(job, assets, job_json, stage=extract_vanilla.STAGE_FULL):
    """バニラ参照データ(refskel/複製リスト/pak全エントリ)をjob配下へ用意する。

    U18: assets["vanilla_mode"]=="live"(既定)なら`extract_vanilla.py`
    (U17でUnrealPak.exe不使用・ライブ抽出化済み)をサブプロセスで実行し、
    ユーザー自身のPalworldインストールのpakから直接生成する(事前cook済み
    参照データ不要)。"copy"(開発機フォールバック/override時)なら従来どおり
    同梱済み参照バニラデータをjob配下へコピーする。

    U54: 引数stageは必要な段(extract_vanilla.STAGE_BLENDER=Blender工程が
    読む分だけ / STAGE_FULL=pak組み立て・preflightが読む分まで)。既定は従来
    どおりfull。既に足りているときはサブプロセスすら起動しない
    (キャッシュ判定の実装はextract_vanilla側の1本だけ。ここでは呼ぶだけ)。
    """
    if assets.get("vanilla_mode") == "live":
        if extract_vanilla.is_cache_fresh(job, stage):
            print(f"[{TAG}] 参照バニラデータ: 既存の抽出物(共有キャッシュ)を再利用"
                  f"(Palworldのpakも抽出器も変化なし、stage={stage}要求)"
                  f" — extract_vanilla.pyは起動しない")
            # U54 WP-B: 共有キャッシュは既に新鮮でも、このjob_dirがまだ
            # 一度もvanilla\へ複製されていない(新規job等)可能性があるため、
            # サブプロセスを起動しないこの経路では明示的に複製を確認する
            # (extract_vanilla.py本体が走る経路は内部で必ずやるので不要)。
            extract_vanilla.ensure_job_local_copy(job)
            return
        print(f"[{TAG}] 参照バニラデータをライブ生成: extract_vanilla.py "
              f"{job_json} --stage {stage}")
        r = subprocess.run([sys.executable, EXTRACT_VANILLA_PY, job_json,
                            "--stage", stage])
        if r.returncode != 0:
            die(f"extract_vanilla.pyが{r.returncode}で終了(バニラ参照データの"
                "ライブ生成に失敗)")
        return

    vanilla_ref = assets["vanilla_ref"]
    vanilla_dir = core.job_subdir(job, "vanilla")
    ref_version_file = os.path.join(vanilla_ref, "version.txt")
    if not os.path.exists(ref_version_file):
        die(f"参照バニラデータが無い: {vanilla_ref}")
    with open(ref_version_file, encoding="utf-8") as f:
        want = f.read().strip()
    version_file = os.path.join(vanilla_dir, "version.txt")
    have = ""
    if os.path.exists(version_file):
        with open(version_file, encoding="utf-8") as f:
            have = f.read().strip()
    if have == want:
        print(f"[{TAG}] 参照バニラデータ: 既存(version={have})を再利用")
        return
    print(f"[{TAG}] 参照バニラデータをコピー: {vanilla_ref} -> {vanilla_dir}")
    for fn in os.listdir(vanilla_ref):
        src = os.path.join(vanilla_ref, fn)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(vanilla_dir, fn))


def resolve_textures(job, meta):
    """avatar_meta.jsonのslots(m00, m01, ...)から body/parka 用PNGを解決する。

    U16改訂: 以前は各ラベル(body/parka)につき「代表スロット1枚」だけを
    キーワードヒント(body/skin, parka/cloth/outfit/wear/top/shirt/dress)で
    選んで注入していたが、3枚以上マテリアルを持つアバター(alicia等)では
    対応しない部位が誤ったテクスチャで描画され見た目が崩れていた
    (アーキテクチャ上の制約。docs\\TODO.md「マテリアル数の多いアバターの
    見た目崩れ対策」参照)。

    今回から `vp_atlas.classify_material()`
    (`research\\ue_exit\\dump_avatar_mesh.py`のSKメッシュ三角形分類ロジックと
    完全同期。同モジュールdocstring参照)で**全スロット**をbody(0)/parka(1)へ
    分類し、ラベル内のdistinctテクスチャファイルが:
      - 1枚以下 → 従来どおりそのままPNGを直接注入(アトラス化スキップ、
        既存挙動を完全維持。G4無退行の根拠)
      - 2枚以上 → `vp_atlas.build_atlas_from_paths()`でグリッドアトラスへ
        合成し、そのPNGを注入する(実際のUV座標変換はBlender側
        `apply_atlas_uv_bake()`が別途行う。ここでは画像合成のみ)
    PNG以外(FBX入力で外部jpg/tga等を参照した場合)は従来どおり自動注入を
    スキップする(vp_atlas.plan_avatar内でPNG判定・除外)。

    戻り値: (tex: {"body":path, "parka":path}(存在するラベルのみ),
             slot_transform: {slot_id: (su,sv,ou,ov)}
             アトラス化によりUV変換が必要なスロットのみを含む。
             空dictなら全ラベルともアトラス不要=Blender UV焼き込み工程を
             スキップしてよい合図,
             tex_alpha_mask: {"body":bool, "parka":bool}
             そのラベルにMASK/BLENDスロットがある、または生成PNGにAlpha<255
             がある場合True。`vp_tex.make_mips`のAlphaカバレッジ保存と、
             PF_DXT1の3色+1bit透明モードを有効にする合図。PF_DXT1/Maskedの
             ため半透明は閾値で二値化されるが、Alpha=0の切り抜きは保持する。
    """
    tex_dir = os.path.join(job["job_dir"], "textures")
    atlas_dir = core.job_subdir(job, "build", "atlas")

    plan, skipped_non_png = vp_atlas.plan_avatar(meta)
    for slot_id, fn in skipped_non_png:
        if fn.startswith("<no-texture-no-basecolor:"):
            # 2026-07-26追加: texture=nullかつbase_colorも取得できない
            # (現行step01_import_vrm.pyでは通常発生しない、旧形式meta等の
            # フォールバック)。以前はここが完全に無言で握り潰されていた
            # (=seed胸ロゴ不具合の根)。もう黙らせず、ログ+GUI両方へ警告する。
            orig_name = fn[len("<no-texture-no-basecolor:"):-1]
            print(f"[{TAG}][WARN] slot={slot_id}(材質={orig_name}) は"
                  "テクスチャもベースカラーも解決できないため自動注入から除外"
                  "(見た目が欠落する可能性)")
            print("##AVATAR_WARNING## 一部のマテリアルの色情報を取得できな"
                  f"かったため、正しく表示されない可能性があります(材質={orig_name})")
        else:
            print(f"[{TAG}][WARN] slot={slot_id} texture={fn} がPNGでないため"
                  "自動注入をスキップ(テンプレート既定のまま)")

    result = {}
    tex_alpha_mask = {}

    def log_alpha(label, path, phase):
        _w, _h, rgba = vp_tex.decode_png(path)
        st = vp_tex.alpha_stats(rgba)
        print(f"[{TAG}] Alpha {phase} {label}: {os.path.basename(path)} "
              f"min={st['min']} max={st['max']} 透明={st['transparent']} "
              f"半透明={st['partial']} pixels={st['pixels']}")
        return st

    for label, info in plan.items():
        order = info["texture_order"]
        if not order:
            continue
        tex_alpha_mask[label] = info.get("alpha_mask", False)
        if len(order) == 1:
            only = order[0]
            if vp_atlas.is_solid_color_key(only):
                # 2026-07-26追加: このラベルの唯一のマテリアルがtexture=null
                # (単色)だった場合。従来の「1枚ならそのままPNGを直接注入」
                # 経路は実ファイルパスを前提にしているため使えない。単色PNGを
                # その場で1枚焼いて注入する(アトラス化と同じ塗りつぶしロジック
                # を1x1グリッドで使うだけ)。
                rgba = vp_atlas.parse_solid_color_key(only)
                img = vp_atlas.solid_color_image(rgba)
                out_png = os.path.join(atlas_dir, f"solidcolor_{label}.png")
                vp_tex.encode_png(out_png, img)
                result[label] = out_png
                print(f"[{TAG}] {label}: テクスチャ無し(単色{rgba[:3]})の"
                      f"マテリアルのみのため単色PNGを生成 -> {out_png}")
            else:
                result[label] = os.path.join(tex_dir, only)
            continue
        # solid_color_key は実ファイルではないので tex_dir と結合しない
        # (結合すると build_atlas_from_paths の is_solid_color_key 判定が
        # 効かなくなり、存在しないパスとして decode_png に渡って壊れる)。
        paths = [fn if vp_atlas.is_solid_color_key(fn) else os.path.join(tex_dir, fn)
                 for fn in order]
        for p in paths:
            if not vp_atlas.is_solid_color_key(p):
                log_alpha(label, p, "step01出力")
        canvas, rows, cols, cs = vp_atlas.build_atlas_from_paths(paths)
        out_png = os.path.join(atlas_dir, f"atlas_{label}.png")
        vp_tex.encode_png(out_png, canvas)
        atlas_alpha = log_alpha(label, out_png, "atlas生成後")
        tex_alpha_mask[label] = (tex_alpha_mask[label]
                                 or atlas_alpha["min"] < 255)
        result[label] = out_png
        # ログ表示だけ solid_color_key を読みやすい表記へ変換する(実際の
        # キー文字列はNUL区切りで生ログに出すとエディタ・端末で崩れるため)。
        order_display = [
            f"<単色{vp_atlas.parse_solid_color_key(fn)[:3]}>"
            if vp_atlas.is_solid_color_key(fn) else fn
            for fn in order]
        print(f"[{TAG}] {label}: {len(order)}枚のテクスチャをアトラス化 "
              f"({rows}x{cols}グリッド, cell={cs}px, canvas={canvas.shape[1]}x"
              f"{canvas.shape[0]}, 元={order_display}) -> {out_png}")

    # アトラス不要(1テクスチャ)経路も実ファイルのAlphaを検査する。
    for label, path in result.items():
        if os.path.exists(path) and not os.path.basename(path).startswith("atlas_"):
            st = log_alpha(label, path, "step01出力/直接注入")
            tex_alpha_mask[label] = (tex_alpha_mask.get(label, False)
                                     or st["min"] < 255)

    slot_xf = vp_atlas.slot_transforms(plan)
    return result, slot_xf, tex_alpha_mask


def apply_atlas_uv_bake(job, slot_xf, blender_exe, step02_female, step02_male):
    """U16: slot_xfが空ならBlenderを起動せず元のstep02_{female,male}.blendの
    パスをそのまま返す(=アトラス不使用アバターは一切余計な処理をしない。
    G4無退行の根拠)。

    非空なら`vp_atlas_uvbake.py`をBlender headlessでfemale/male各1回実行し、
    アトラス変換後のUVを焼き込んだ**新しい**blend(元ファイルは無改変)を
    job配下build\\atlas\\へ書き出し、そのパスを返す。呼び出し元はこの戻り値を
    step02_female/step02_maleとして以後使う(build_pak_from_avatar.pyには
    無改変のまま渡すだけなので、build_pak_from_avatar.py自体の変更は不要)。

    戻り値: (step02_female_path, step02_male_path, reports)
      reports = {"female": {slot: {...}}, "male": {...}} (vp_atlas_uvbake.pyの
      report.json。タイリング除外スロットの警告ログにも使う)"""
    if not slot_xf:
        # 検証官F3(公開issue #5の4経路目、2026-07-28): アトラス不要
        # (distinctテクスチャ≦1)の検体は _render_atlas_visual_check まで
        # 到達せず、マーカーが1行も出なかった。「該当なし」と「そこまで
        # 到達しなかった」をログだけで区別できるよう、NOT_APPLICABLE を
        # 明示する(構造的にアトラス化しない=検査対象が存在しないだけ
        # なので、strictモードでもdieしない。バグではない: G4無退行の根拠)
        for _gender in ("female", "male"):
            print(f"##ATLAS_VISUAL_CHECK## NOT_APPLICABLE gender={_gender} "
                  "reason=no_atlas")
        print(f"[{TAG}] アトラス見た目チェック: この検体はアトラス化が構造的に"
              "不要(distinctテクスチャ≦1)のため検査対象が存在しない"
              "(NOT_APPLICABLE。無言スキップではない)")
        return step02_female, step02_male, {}

    atlas_dir = core.job_subdir(job, "build", "atlas")
    xf_json = os.path.join(atlas_dir, "slot_transform.json")
    with open(xf_json, "w", encoding="utf-8") as f:
        json.dump(slot_xf, f)

    # research\ue_exit\dump_avatar_mesh.py(無改変・書き込み許可対象外)は
    # avatar_meta_pathの既定値を「blend_pathと同じディレクトリのavatar_meta.json」
    # としてハードコードしている。焼き込み後のblendはconverted\ではなく
    # build\atlas\に置くため、同ディレクトリへavatar_meta.jsonを複製して
    # そのデフォルト解決を満たす(dump_avatar_mesh.py自体は無改変のまま)。
    src_meta = os.path.join(job["job_dir"], "converted", "avatar_meta.json")
    shutil.copy(src_meta, os.path.join(atlas_dir, "avatar_meta.json"))

    out_blend = {}
    reports = {}
    for gender, blend_in in (("female", step02_female), ("male", step02_male)):
        blend_out = os.path.join(atlas_dir, f"step02_{gender}_atlas.blend")
        report_json = os.path.join(atlas_dir, f"uvbake_report_{gender}.json")
        log_path = os.path.join(atlas_dir, f"uvbake_{gender}.log")
        # --factory-startup(2026-07-28、公開issue #14): ユーザー設定(新規データ名の
        # 翻訳等)を読み込ませない。全Blender起動共通の方針(dev issue #24)
        cmd = [blender_exe, "--background", "--factory-startup",
               "--python-exit-code", "1", "--python",
               VP_ATLAS_UVBAKE_PY, "--", blend_in, blend_out, xf_json, report_json]
        print(f"[{TAG}] UVアトラス焼き込み({gender}): $ {' '.join(cmd)}")
        with open(log_path, "w", encoding="utf-8") as lf:
            r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0:
            tail = ""
            try:
                with open(log_path, encoding="utf-8", errors="replace") as lf:
                    tail = lf.read()[-3000:]
            except OSError:
                pass
            die(f"UVアトラス焼き込み({gender})が{r.returncode}で終了 "
                f"(ログ: {log_path})\n--- ログ末尾 ---\n{tail}")
        with open(report_json, encoding="utf-8") as rf:
            report = json.load(rf)
        tiling_slots = [k for k, v in report.items() if v.get("tiling")]
        if tiling_slots:
            print(f"[{TAG}][WARN] {gender}: タイリングUV検出によりアトラス対象から"
                  f"除外(見た目崩れを許容): {tiling_slots}")
        # 2026-07-26追加(オーナー裁定): 面がUVタイル境界をまたいでいて整数
        # シフトでは[0,1]に収めきれなかったスロット(vp_atlas_uvbake.py Pass2、
        # excluded_reason=="overshoot")。閾値を緩めて通すのではなく、タイリング
        # 除外と同じ思想でアトラス対象から除外して完走させ、エンドユーザーへ
        # 警告する。ログだけでなくGUI(app\DiveToPalworld.cs)が拾える
        # ##AVATAR_WARNING## マーカーも出す(ログ欄に流れるだけでは見落とされる
        # ため、完了ダイアログで明示提示する)。
        overshoot_excluded = {k: v for k, v in report.items()
                               if v.get("excluded_reason") == "overshoot"}
        if overshoot_excluded:
            detail = ", ".join(
                f"{k}(overshoot={v.get('overshoot_after_shift', 0):.3f})"
                for k, v in overshoot_excluded.items())
            print(f"[{TAG}][WARN] {gender}: UVタイル境界をまたぐ面によりアトラス"
                  f"対象から除外(見た目崩れを許容): {detail}")
            print("##AVATAR_WARNING## このアバターは特殊なUV構造をしているので"
                  "正しく表示されない可能性があります"
                  f"(該当マテリアル: {gender} {detail})")
        # U50-single(受入ゲート): 焼き込み後のUVが意図したセルの外へ出ていたら
        # ビルドを止める。2026-07-25の実機NG(行方向のセル取り違え、
        # vp_atlas.to_blender_transform のdocstring参照)はこれで捕まる。
        out_of_cell = {k: v for k, v in report.items() if v.get("out_of_cell")}
        if out_of_cell:
            detail = "\n".join(
                f"    {k}: UE空間bbox={v.get('bbox_after_ue')} "
                f"期待セル={v.get('cell_ue')}" for k, v in out_of_cell.items())
            die(f"UVアトラス焼き込み({gender}): 焼き込み後のUVが意図したセルの外に"
                f"出ている {len(out_of_cell)}スロット。\n"
                f"アトラスのセル割り当てとUV変換が食い違っている(見た目が壊れる)。\n"
                f"{detail}\n  レポート: {report_json}")
        out_blend[gender] = blend_out
        reports[gender] = report
        _render_atlas_visual_check(job, gender, blend_out, blender_exe, atlas_dir)
    return out_blend["female"], out_blend["male"], reports


# U50-single(2026-07-25、実機NGを受けた受入ゲート追加):
# 「MIが1種類」「NG 0件」という**構造の一致**はすべてPASSだったのに実機は
# 顔が無地グレーだった(UVが別のセルを指していた)。構造だけでは足りないので
# **焼き込み後のUVで実際にレンダリングして、アトラス化前のプレビューと
# 同じ絵になるか**を機械判定する。
# 閾値: 相関(NCC) >= 0.95。セル数が多いアバターはアトラス縮小の分だけ
# 正当に絵が変わる(n=9で元の2/3)ため完全一致は求めない。実測では
# バグ時 0.7182 / 正常時 1.0000 と明確に分かれる。
ATLAS_VISUAL_MIN_NCC = 0.95


def _visual_check_not_run(gender, reason_code, human_reason):
    """公開issue #5(fail-open封じ、2026-07-28): アトラス見た目チェックが
    「実行できなかった」ときの唯一の出口。以前は3経路(①比較材料欠如
    ②レンダリング失敗 ③NCC判定不能(寸法不一致/例外))がそれぞれ軽い
    printだけで黙ってreturnしており、検査が無効化されたまま変換が「成功」
    していた(=「数値ゲートは通ったのに実物が壊れていた」を捕まえるための
    検査自身が、条件次第で静かに消えるfail-open構造)。ここで必ず:
      - 理由コード付きの[WARN](開発者向けログ)
      - ##AVATAR_WARNING##(GUIの完了ダイアログに出るエンドユーザー向け警告)
      - ##ATLAS_VISUAL_CHECK## SKIPPED(機械可読マーカー。実行成功時のRANと
        対になり、「実行された」と「合格した」をログ上で区別できる)
    を出す。さらに D2P_STRICT_VISUAL_CHECK=1(devtools\\relgate.py=リリース
    関所が常時設定)のときは die する(リリース判定では検査の自己無効化を
    許さない=fail-closed)。エンドユーザー経路がWARN継続なのは、GPUの無い
    環境ではプレビュー画像自体が作れず(convert.ps1のrender_preview NonFatal
    裁定、2026-07-26)、ここでdieすると「MODは作れるのに変換が止まる」退行に
    なるため。"""
    print(f"[{TAG}][WARN] アトラス見た目チェック({gender})を実行できなかった: "
          f"{human_reason}(理由コード: {reason_code})")
    print("##AVATAR_WARNING## アトラス化後の見た目検査を実行できませんでした"
          f"({gender}: {human_reason})。変換は続行しますが、見た目が壊れていても"
          "自動検出されていません")
    print(f"##ATLAS_VISUAL_CHECK## SKIPPED gender={gender} reason={reason_code}")
    if os.environ.get("D2P_STRICT_VISUAL_CHECK") == "1":
        die(f"アトラス見た目チェック({gender})が実行できない状態での完走を、"
            f"D2P_STRICT_VISUAL_CHECK=1(リリース関所)では許可しない: "
            f"{human_reason}(理由コード: {reason_code})")


def _render_atlas_visual_check(job, gender, blend_out, blender_exe, atlas_dir):
    ref = os.path.join(job["job_dir"], "converted", f"preview_{gender}_stand.png")
    atlas_png = os.path.join(atlas_dir, "atlas_body.png")
    if not (os.path.exists(ref) and os.path.exists(atlas_png)):
        # 経路① 比較材料の欠如(公開issue #5)。典型はGPU無し環境で
        # render_preview.pyが失敗しrefが無いケース
        _visual_check_not_run(
            gender, "missing_inputs",
            f"比較材料が無い(アトラス化前プレビュー={os.path.exists(ref)}, "
            f"アトラス画像={os.path.exists(atlas_png)})")
        return
    out_png = os.path.join(atlas_dir, f"atlascheck_{gender}.png")
    log_path = os.path.join(atlas_dir, f"atlascheck_{gender}.log")
    cmd = [blender_exe, "--background", "--factory-startup",
           "--python-exit-code", "1", "--python",
           RENDER_ATLAS_CHECK_PY, "--", blend_out, atlas_png, out_png]
    with open(log_path, "w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0 or not os.path.exists(out_png):
        # 経路② 検査用レンダリングの失敗(公開issue #5)
        _visual_check_not_run(
            gender, "render_failed",
            f"検査用レンダリングが失敗した(exit={r.returncode}, ログ: {log_path})")
        return
    try:
        import numpy as np
        import vp_tex
        _w, _h, a = vp_tex.decode_png(ref)
        _w2, _h2, b = vp_tex.decode_png(out_png)
        if a.shape != b.shape:
            # 経路③a 寸法不一致でNCC計算不能(公開issue #5)
            _visual_check_not_run(
                gender, "size_mismatch",
                f"画像寸法が一致しない(基準={a.shape} 検体={b.shape})")
            return
        af = a[:, :, :3].astype(np.float64).ravel()
        bf = b[:, :, :3].astype(np.float64).ravel()
        af -= af.mean()
        bf -= bf.mean()
        denom = float((af ** 2).sum() ** 0.5 * (bf ** 2).sum() ** 0.5)
        ncc = float((af * bf).sum() / denom) if denom else 0.0
    except Exception as e:
        # 経路③b NCC判定処理自体の失敗(公開issue #5)
        _visual_check_not_run(gender, "ncc_error", f"判定処理が失敗した({e})")
        return
    print(f"[{TAG}] アトラス見た目チェック({gender}): アトラス化前のプレビューとの"
          f"相関 NCC={ncc:.4f} (>= {ATLAS_VISUAL_MIN_NCC} が合格) -> {out_png}")
    # 公開issue #5: 「検査が実行された」ことを機械可読に残す(SKIPPEDと対になる
    # マーカー。合否はresult=。FAIL時はこの直後のdieで変換ごと停止する)
    print(f"##ATLAS_VISUAL_CHECK## RAN gender={gender} ncc={ncc:.4f} "
          f"result={'PASS' if ncc >= ATLAS_VISUAL_MIN_NCC else 'FAIL'}")
    if ncc < ATLAS_VISUAL_MIN_NCC:
        die(f"アトラス化後のUVで描いた絵が、アトラス化前のプレビューと一致しない"
            f"({gender}: NCC={ncc:.4f} < {ATLAS_VISUAL_MIN_NCC})。\n"
            f"セル割り当てとUV変換が食い違っている疑いが強い(見た目が壊れる)。\n"
            f"  アトラス化前(正解): {ref}\n"
            f"  アトラス化後(検体): {out_png}\n"
            f"  アトラス画像      : {atlas_png}")


def find_shadow_lift_offset(data):
    """cook済みMICのuexpからShadowLift ScalarParameterValueのfloatオフセットを
    一意に特定する(U13-T0.2実証: FMaterialParameterInfoのIndex(-1、4byteの
    0xFF)直後の4byteがパラメータ値、さらにその後16byteがExpressionGUID。
    プレースホルダは親の既定値(0.0)と異なる値でcookされている前提
    ——一致しているとUEがオーバーライドを一切書き出さないため、
    09_build_noue_variants.pyはSHADOW_LIFT_PLACEHOLDER=0.5を使う)。"""
    candidates = [i + 4 for i in range(len(data) - 4)
                  if data[i:i + 4] == b"\xff\xff\xff\xff"
                  and i + 4 + 4 + 16 <= len(data)]
    if len(candidates) != 1:
        raise RuntimeError(
            f"ShadowLiftのオフセットが一意でない: {len(candidates)}件 {candidates}")
    return candidates[0]


def patch_shadow_lift(uexp_bytes, value):
    data = bytearray(uexp_bytes)
    off = find_shadow_lift_offset(bytes(data))
    struct.pack_into("<f", data, off, float(value))
    return bytes(data)


def combo_for(unlit, two_sided):
    return f"{'Unlit' if unlit else 'Lit'}{'2S' if two_sided else '1S'}"


def prepare_material_overrides(job, meta, variants_dir):
    """job設定(unlit/shadow_lift/force_two_sided)+avatar_meta(スロット別
    double_sided)から、スロットごとに正しい静的バリアント
    (影なし×両面表示の組み合わせ)を選び、Litバリアントなら影の濃さを
    バイトパッチしてjob配下へ書き出す。戻り値: 差し替えファイルを置いた
    ディレクトリ(1件も無ければNone)。"""
    unlit = bool(job.get("unlit", False))
    shadow_lift = max(0.0, min(1.0, float(job.get("shadow_lift", 0.0))))
    force_two_sided = bool(job.get("force_two_sided", True))

    out_dir = core.job_subdir(job, "build", "noue_mat_override")
    n = 0
    for slot, info in meta["slots"].items():
        two_sided = bool(info.get("double_sided")) or force_two_sided
        combo = combo_for(unlit, two_sided)
        src_dir = os.path.join(variants_dir, combo)
        src_asset = os.path.join(src_dir, f"M_VP_{slot}.uasset")
        src_uexp = os.path.join(src_dir, f"M_VP_{slot}.uexp")
        if not (os.path.exists(src_asset) and os.path.exists(src_uexp)):
            print(f"[{TAG}][WARN] noueマテリアルバリアント無し"
                  f"(slot={slot} combo={combo}) — テンプレート既定のまま")
            continue
        shutil.copy(src_asset, os.path.join(out_dir, f"M_VP_{slot}.uasset"))
        with open(src_uexp, "rb") as f:
            uexp = f.read()
        if not combo.startswith("Unlit"):
            uexp = patch_shadow_lift(uexp, shadow_lift)
        with open(os.path.join(out_dir, f"M_VP_{slot}.uexp"), "wb") as f:
            f.write(uexp)
        n += 1
        detail = f"shadow_lift={shadow_lift}" if not combo.startswith("Unlit") else "unlit"
        print(f"[{TAG}] マテリアル設定: slot={slot} combo={combo} {detail} "
              f"two_sided={two_sided}")
    return out_dir if n else None


# ============================================================================
# U54 WP-B(2026-07-27): --warm-cache(事前計算)
# ----------------------------------------------------------------------------
# バニラ両ステージ+live_templateを、job.json無しでマシン共有キャッシュへ
# 事前構築するスタンドアロンモード。GUI起動時(app\DiveToPalworld.cs)が
# バックグラウンドで静かに呼ぶほか、CLIから明示実行してもよい。
# ============================================================================

def _warm_job(pak, work_root):
    """--warm-cache専用の最小限job dict。job_dir自体は実在しないプレース
    ホルダ(core.job_work_root()がdirname(job_dir)==work_rootを返すためだけに
    使う。ファイルは一切書かない)。shadow_lift/unlitは既定値のままでよい
    (live_templateのfingerprintに乗るのはD2P_U50_*系の切り分け環境変数が
    立っているときだけ。既定OFF)。"""
    return {
        "paths": {"palworld_pak": os.path.abspath(pak)},
        "job_dir": os.path.join(os.path.abspath(work_root), "_warm_dummy"),
    }


def warm_cache(pak, work_root):
    """バニラ両ステージ+live_templateを共有キャッシュへ事前構築する。
    戻り値: {"vanilla_blender_sec","vanilla_full_sec","live_template_sec",
             "total_sec","template_dir"}(すべて秒、round(…, 2))。
    2回目以降(既に新鮮)の呼び出しはキャッシュ判定だけで即returnするため、
    各secはほぼ0になる(GUI起動のたびに叩いても実害が無いことの根拠)。"""
    job = _warm_job(pak, work_root)
    t0 = time.time()
    print(f"[{TAG}] --warm-cache開始: pak={job['paths']['palworld_pak']} "
          f"work_root={os.path.abspath(work_root)}")

    t = time.time()
    extract_vanilla.run(job, extract_vanilla.STAGE_BLENDER)
    t_vb = time.time() - t

    t = time.time()
    extract_vanilla.run(job, extract_vanilla.STAGE_FULL)
    t_vf = time.time() - t

    t = time.time()
    template_dir = live_template.build_live_template(job)
    t_lt = time.time() - t

    info = {
        "vanilla_blender_sec": round(t_vb, 2),
        "vanilla_full_sec": round(t_vf, 2),
        "live_template_sec": round(t_lt, 2),
        "total_sec": round(time.time() - t0, 2),
        "template_dir": template_dir,
    }
    print(f"[{TAG}] --warm-cache完了: {info}")
    return info


def main():
    if len(sys.argv) < 2:
        die("使い方: python convert_noue.py <job.json>  /  "
            "python convert_noue.py --ensure-vanilla [--stage blender|full] "
            "<job.json>  /  "
            "python convert_noue.py --warm-cache --pak <Pal-Windows.pak> "
            "--work-root <workRoot>")

    if sys.argv[1] == "--warm-cache":
        args = sys.argv[2:]
        opts = {}
        i = 0
        while i < len(args):
            if args[i] in ("--pak", "--work-root") and i + 1 < len(args):
                opts[args[i][2:].replace("-", "_")] = args[i + 1]
                i += 2
                continue
            i += 1
        if "pak" not in opts or "work_root" not in opts:
            die("使い方: python convert_noue.py --warm-cache --pak "
                "<Pal-Windows.pak> --work-root <workRoot>")
        if not os.path.exists(opts["pak"]):
            die(f"--pakが存在しない: {opts['pak']}")
        warm_cache(opts["pak"], opts["work_root"])
        return

    # U14: convert.ps1のPhase 0(Blender工程より前)から呼ばれる軽量モード。
    # noueのBlender工程(step02_retarget.py)がvanilla\common_bones.json等を
    # Blender工程内で直接参照するため、フル変換の最後ではなくBlender工程の
    # 前にバニラ参照データを用意しておく必要がある(クリーンルーム検証で発覚)
    if sys.argv[1] == "--ensure-vanilla":
        # U54: --stage blender なら「Blender工程が読む分」だけ用意する
        # (プレビューに要らないpakインデックス走査を後回しにする)。
        # 省略時はfull=従来どおり(devtools\u33_render_gallery.py等の
        # 既存の呼び出しは何も変わらない)
        args = sys.argv[2:]
        stage = extract_vanilla.STAGE_FULL
        if "--stage" in args:
            i = args.index("--stage")
            if i + 1 >= len(args):
                die("--stage の値がない (blender|full)")
            stage = args[i + 1]
            del args[i:i + 2]
        if len(args) != 1 or stage not in extract_vanilla.STAGES:
            die("使い方: python convert_noue.py --ensure-vanilla "
                "[--stage blender|full] <job.json>")
        job_json = os.path.abspath(args[0])
        job = core.load_job(job_json)
        # テンプレート(447ファイル/約700MB)はここでは要らないので組み立てない。
        # 必要になるのはpak組み立て工程(main本体のresolve_noue_assets)から
        assets = resolve_vanilla_source(job)
        ensure_vanilla(job, assets, job_json, stage=stage)
        return

    job_json = os.path.abspath(sys.argv[1])
    job = core.load_job(job_json)
    job_dir = job["job_dir"]
    avatar = job.get("avatar_name", "Avatar")

    conv = os.path.join(job_dir, "converted")
    step02_female = os.path.join(conv, "step02_female.blend")
    step02_male = os.path.join(conv, "step02_male.blend")
    for p, label in ((step02_female, "step02_female.blend"),
                     (step02_male, "step02_male.blend")):
        if not os.path.exists(p):
            die(f"{label}が無い(Blender工程が未完了?): {p}")
    # WP-C(dev issue #27、2026-07-28): relgateの中間ハッシュスキップ用フック。
    # convert.ps1のPhase 0-1(バニラ準備+Blender工程、Mutex保護込み)だけを
    # 本番と完全に同一の経路で走らせ、noue工程(Phase 2-6)へ入る直前で止める。
    # convert.ps1自体は無改変(このプロセスが即0終了すればPhase 2〜6は
    # 実質何もしない)。step02の存在確認(上)まで済ませてから止まるので、
    # 「Phase 0-1が本当に成果を出したか」はこの経路でも保証される。
    # テンプレート組み立て(resolve_noue_assets、ライブ抽出~700MB)には入らない。
    if os.environ.get("D2P_STOP_BEFORE_NOUE") == "1":
        print(f"[{TAG}] D2P_STOP_BEFORE_NOUE=1: Phase 0-1の成果物を確認して終了"
              "(noue工程は実行しない。relgate中間ハッシュスキップ判定用フック)")
        print("##D2P_STOP_BEFORE_NOUE## OK")
        return
    assets = resolve_noue_assets(job)
    if not os.path.exists(assets["template"]):
        die(f"noueテンプレートが無い(ライブ抽出/開発機フォールバック: "
            f"{DEV_BUILD_DIR}): {assets['template']}")
    print(f"[{TAG}] テンプレ資産: {assets['source']} ({assets['template']})")

    # U54: convert.ps1のPhase 0はblender段(Blender工程が読む分)までしか
    # 用意しない。pak組み立てとpreflightが読む分(複製リスト/pak全エントリ)は
    # ここで初めて要るので、ここで揃える。同じ抽出が1ビルドで2回走っていた
    # 二重呼び出しは、この「段の分担」で解消している(Phase 0が済ませた分は
    # extract_vanilla側のキャッシュ判定が見て再実行しない)
    ensure_vanilla(job, assets, job_json)

    meta_path = os.path.join(conv, "avatar_meta.json")
    if not os.path.exists(meta_path):
        die(f"avatar_meta.jsonが無い(step01が未実行?): {meta_path}")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    blender_exe = job["paths"]["blender_exe"]
    if not os.path.exists(blender_exe):
        die(f"Blenderが無い: {blender_exe}")

    # U16: マテリアルアトラス化。tex解決(画像合成)→アトラス使用時のみ
    # Blender headlessでUV焼き込み(step02_{female,male}.blendの新版を作る。
    # 元ファイルは無改変)。slot_xfが空(distinctテクスチャ<=1のラベルのみ)
    # ならapply_atlas_uv_bakeはBlenderを起動せず元のパスをそのまま返す
    # (G4無退行)
    tex, slot_xf, tex_alpha_mask = resolve_textures(job, meta)
    step02_female, step02_male, _atlas_reports = apply_atlas_uv_bake(
        job, slot_xf, blender_exe, step02_female, step02_male)

    mat_override_dir = prepare_material_overrides(job, meta, assets["variants"])

    # U50-fast(2026-07-26): 影の濃さ(shadow_lift)をライブテンプレートの外へ出す。
    #
    # 影の濃さはエンドユーザーがほぼ唯一いじる項目なので、パイプライン中もっとも
    # 重い工程(テンプレート再構築 879ファイル/約700MB)に載せてはいけない。
    # live_template._unify_slot_materials は k 非依存の統一MIだけを焼き、
    # k 依存のMI(79件・数KB)はここで作って pak 化直前に差し替える
    # (build_pak_from_avatar の --mi-override-dir。Phase 2c の mat_override と同じ形)。
    #
    # ライブ抽出モードでのみ有効。開発機フォールバック/D2P_NOUE_TEMPLATE_ROOT
    # では統一MI自体が無い(テンプレートは事前cook済みのpak_extract)ので、
    # 旧経路(M_VPバリアント)のままにする。
    mi_override_dir = None
    if assets["vanilla_mode"] == "live":
        mi_override_dir, _n_mi, _mi_info = live_template.build_shadow_mi_overrides(
            job, assets["template"],
            core.job_subdir(job, "build", "noue_mi_override"))
    else:
        print(f"[{TAG}] U50-fast: テンプレがライブ抽出でない({assets['source']})ため"
              f"影の濃さのMI差し替えは行わない(旧経路のまま)")

    # U49: shadow_lift(job.json)から注入テクスチャの明度ゲインを計算する。
    # 根拠/式はvp_texinject.shadow_lift_gain()のdocstring+モジュール
    # docstring参照(UE版M_VPのBaseColor×(1-k)+Emissive×k split相当を
    # テクスチャ空間の乗算ゲインで近似)。shadow_lift=0またはunlit=Trueなら
    # gain=1.0(既存アバターへの回帰なし)。
    # 校正専用フック(U49引き継ぎセッション新設): 環境変数D2P_U49_L0が
    # 設定されていれば、vp_texinject.SHADOW_LIFT_GAIN_L0の代わりに一時的に
    # その値でgainを計算する(job.json自体は書き換えない=通常経路に影響なし。
    # 実機校正で複数のL0候補を1本のjob.jsonから連続ビルドするための開発時
    # フックであり、D2P_NOUE_TEMPLATE_ROOT等の既存パターンと同じ位置づけ)。
    #
    # U50-unify(2026-07-25): このテクスチャ明度ゲイン経路は**既定で無効**に
    # した(tex_gain=1.0固定)。理由:
    #   shadow_lift は live_template._unify_slot_materials によって
    #   「BaseColor=A×(1-k) / Emissive Texture Intensity=A×k」という
    #   **UEのM_VPが持つ式そのもの**でMIへ実装された。U49のゲインは
    #   その式を持てなかった時代の代用(テクスチャ空間の乗算近似)であり、
    #   両方を有効にすると影の持ち上げが二重に掛かる。
    #   shadow_lift=0 のときは U49 のゲインも 1.0 だったため、
    #   **shadow_lift=0 のビルドはこの変更前後でピクセル完全一致する**。
    # D2P_U50_LEGACY_TEX_GAIN=1 で旧経路(U49のゲイン)へ戻せる(A/B切り分け用)。
    _legacy_gain = os.environ.get("D2P_U50_LEGACY_TEX_GAIN") == "1"
    _l0_override = os.environ.get("D2P_U49_L0")
    _l0 = float(_l0_override) if _l0_override else None
    if _legacy_gain:
        tex_gain = vp_texinject.shadow_lift_gain(
            job.get("shadow_lift", 0.0), unlit=bool(job.get("unlit", False)), l0=_l0)
        print(f"[{TAG}] U49(LEGACY): shadow_lift={job.get('shadow_lift', 0.0)} "
              f"unlit={job.get('unlit', False)} -> tex_gain={tex_gain:.4f} "
              f"(L0={_l0 if _l0 is not None else vp_texinject.SHADOW_LIFT_GAIN_L0}"
              f"{'(override)' if _l0 is not None else ''}, "
              f"version={vp_texinject.TEXINJECT_GAIN_VERSION}) "
              f"※D2P_U50_LEGACY_TEX_GAIN=1。U50のEmissive実装と二重計上になる")
    else:
        tex_gain = 1.0
        print(f"[{TAG}] U50: shadow_lift={job.get('shadow_lift', 0.0)} は"
              f"MIのBaseColor/Emissive分割で実装(live_template)。"
              f"U49のテクスチャ明度ゲインは二重計上を避けるため無効"
              f"(tex_gain=1.0固定)")

    out_dir = os.path.join(job_dir, "build")
    os.makedirs(out_dir, exist_ok=True)
    out_pak = os.path.join(out_dir, f"{avatar}_PlayerSwap_P.pak")
    work_dir = os.path.join(out_dir, "noue_work")

    argv = ["build_pak_from_avatar.py",
            "--step02-female", step02_female,
            "--step02-male", step02_male,
            "--template", assets["template"],
            "--out", out_pak,
            "--blender", blender_exe,
            "--work", work_dir,
            "--job-json", job_json,
            "--cook-log", assets["cook_log"],
            "--tex-gain", str(tex_gain)]
    if "body" in tex:
        argv += ["--tex-body", tex["body"]]
        if tex_alpha_mask.get("body"):
            argv += ["--tex-body-alpha-coverage"]
    if "parka" in tex:
        argv += ["--tex-parka", tex["parka"]]
        if tex_alpha_mask.get("parka"):
            argv += ["--tex-parka-alpha-coverage"]
    if mat_override_dir:
        argv += ["--mat-override-dir", mat_override_dir]
    if mi_override_dir:
        argv += ["--mi-override-dir", mi_override_dir]

    print(f"[{TAG}] build_pak_from_avatar.main() argv={argv[1:]}")
    old_argv = sys.argv
    sys.argv = argv
    try:
        build_pak_from_avatar.main()
    finally:
        sys.argv = old_argv

    vp_provenance.write_build_provenance(out_dir, out_pak, avatar, assets["source"], REPO_DIR)

    # U50-fast(2026-07-26): フル変換が完走した時点の job.json を控えておく。
    # pipeline\py\fast_repack.py(2026-07-26: devtools\から移設)はこれと現在の job.json を比較して
    # 「差分が shadow_lift / unlit だけなら中間成果は再利用してよい」と判定する
    # (mtime だけで見ると影の濃さを1文字変えただけで停止してしまうため)。
    try:
        with open(os.path.join(out_dir, "job_snapshot.json"), "w",
                  encoding="utf-8") as f:
            json.dump({k: v for k, v in job.items() if k != "job_dir"},
                      f, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    except Exception as e:  # 控えの失敗でビルドを落とさない(fast_repackはmtimeへ退避する)
        print(f"[{TAG}][WARN] job_snapshot.json を書けなかった: {e}")

    print(f"[{TAG}] done: {out_pak}")


if __name__ == "__main__":
    main()
