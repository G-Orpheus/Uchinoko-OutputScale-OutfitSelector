# -*- coding: utf-8 -*-
r"""高速リパック: 中間成果を再利用して pak だけ作り直す(開発ループ専用)。

出典: work\u50_unify\fast_repack.py(2026-07-25 の影スイープで実際に使われた試作)を
devtools へ昇格し、作業域をハードコードせず任意の job から使えるようにしたもの。
2026-07-26: 本ツールは GUI「影のみ更新(高速)」の実行時に呼ばれる出荷物側の
コンポーネントであり、開発専用ではなくなった(devtools\ は非公開のため、
開発専用ツール以外は置けない)。そのため devtools\ から pipeline\py\ へ移設した。
pipeline\ 配下のソースは一切変更しない(import して使うだけ)という制約自体は
変わっていない — 本ファイル自身が pipeline\py\ の一員になっただけ。

■ 何をするか
フル変換(pipeline\cli\convert.ps1)のうち、pak 書き出し(Phase 3)だけを再実行する。
Blender 工程(Phase 1)と衣装SK 60体への実アバター注入(Phase 2)は結果が
    <job_dir>\build\noue_work\variant\
に残っており、マテリアル(MI)のパラメータだけを振るスイープでは一切変わらない。
実測の内訳(work\u50_fastloop\REPORT.md): Phase2 が 109 秒で最大、Phase3 の pak 書き出しは
約 3 秒。pak 735MB の 98.5% は毎回まったく同じバイトを書き直しているだけだった。
    1反復 3分45秒 → 約55秒(約4.1倍)の見積り。

■ 使い方
    python pipeline\py\fast_repack.py --job work\<name>\job.json --out work\<name>\build\try1_P.pak
    python pipeline\py\fast_repack.py --job ... --out ... --tex-gain 1.8556   # テクスチャも作り直す
    python pipeline\py\fast_repack.py --job ... --out k07_P.pak --shadow-lift 0.7  # 影の濃さを振る
    python pipeline\py\fast_repack.py --job ... --out ... --preflight              # 検品まで通す(+約17秒)

■ 呼び出し元(U51、2026-07-25)
GUI「影のみ更新(高速)」→ `pipeline\cli\convert.ps1 -MaterialsOnly`(noue) → 本ツール `--preflight`。
したがって本ツールは**開発専用ではなくなった**。CLI引数と `##REPACK_ERROR##` マーカーは
convert.ps1 の materials-only(noue)分岐と対になっている。片方だけ変えないこと。

■ 影の濃さ(shadow_lift)について — 本ツールの主目的
影の濃さはエンドユーザーがほぼ唯一いじる項目なので、パイプライン中もっとも重い
テンプレート再構築に載せない設計になっている(U50-fast)。
    live_template  … k 非依存(統一MIは BaseColor/Emissive を焼いていない)
    統一MI 79件    … k 依存。`live_template.build_shadow_mi_overrides()` が
                     build\noue_mi_override\ へ数KB書き出す(1秒未満)
本ツールは **毎回この 79件を job.json の shadow_lift(または --shadow-lift)から
作り直してから** pak を書く。したがって shadow_lift を変えても停止せず、
そのまま正しく反映される(k=0 なら1件も作らない = テンプレートのMIがそのまま出る)。
job.json の差分が shadow_lift / unlit **だけ**なら鮮度ゲートも通す
(判定材料は build\job_snapshot.json = 最後のフル変換時点の job.json)。

■ ★★ 使う前に必ず読むこと(危険性) ★★
1. **キャッシュの鮮度がすべて。**再利用する live_template / noue_work\variant / atlas は
   アバターとテクスチャに依存する。VRM/FBX・アトラス・--tex-gain を変えたのに使い回すと
   **古い成果で判断してしまう**。2026-07-25 にこの取り違え事故が実際に2件起きている。
   → 本ツールは毎回「何を再利用したか」を必ずログへ出す。加えて job.json や
     アバターファイルがキャッシュより新しい場合は **既定で停止する**(--allow-stale で続行可)。
     ログの再利用一覧に目を通さずに結果を判断しないこと。
2. **既定では preflight(約17秒)を飛ばす。**禁止物混入(Skeleton/Body/ubulk)や壊れた pak を
   そのまま実機へ送ることになる。クラッシュすれば気づくが、**通ってしまうと気づかない**。
   → 反復中に使うのはよい。ただし**責任者に見せる前・DEV_NOTES へ記録する前には
     必ずフル変換 + `pipeline\py\preflight_pak.py` を通し直すこと。**
     本ツールの出力だけを根拠に合否を報告してはならない。
   → **`--preflight` を付ければこのツール自身が検品まで通す**(U51)。
     GUIの「影のみ更新」は convert.ps1 経由で必ずこれを付けて呼ぶ。
     エンドユーザーに壊れた pak を渡さないため、この経路で外してはならない。
3. **同一アバターの反復にしか効かない。**アバターを変えたらフル変換からやり直す。
4. 実験ごとに作業域を分けること(devtools\new_experiment.ps1)。build\ を共有すると壊れる。

pipeline\ 配下のソースは一切変更しない(import して使うだけ)。
"""
import argparse
import datetime
import io
import json
import os
import subprocess
import sys

# 2026-07-26: devtools\ から pipeline\py\ へ移設(このファイル自身が既に
# pipeline\py\ にいるので、REPO_DIR はここから2段上)。同居する vp_pakwrite 等は
# 「python <このファイル>」実行時にPythonが自動でスクリプトの場所をsys.path[0]へ
# 入れるため追加のsys.path操作なしでimportできるが、明示しておく(頑健性のため)。
HERE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(HERE_DIR))
sys.path.insert(0, HERE_DIR)
_ue_exit = os.path.join(REPO_DIR, "research", "ue_exit")
if os.path.isdir(_ue_exit):
    sys.path.insert(0, _ue_exit)

import vp_pakwrite  # noqa: E402
import vp_texinject  # noqa: E402
import vp_core  # noqa: E402
import live_template  # noqa: E402 (U50-fast: 影の濃さMIの生成)
import convert_noue  # noqa: E402 (U50-fast: M_VPバリアント選択をフル変換と共有する)
import outfit_selection  # noqa: E402
import avatar_assets  # noqa: E402

# U50-fast: 影の濃さはテンプレートから切り離されたので、この2キーだけは
# job.json が変わっていても中間成果(Blender成果/衣装SK注入/アトラス)を
# 再利用してよい。ここを増やすときは「その設定がテンプレートや variant を
# 変えないこと」をコードで確認してからにすること。
SHADOW_ONLY_KEYS = ("shadow_lift", "unlit")

# live_template 内でのテクスチャの位置(live_template.MVP_PACKAGE_PREFIX と対応)。
# slot0=素体(t00) / slot1=衣装(t01)。
TEX_SLOT_REL = {"body": "Player/ModelMaterials/MainShader/t00.uexp",
                "parka": "Player/ModelMaterials/MainShader/t01.uexp"}
ATLAS_PNG = {"body": "atlas_body.png", "parka": "atlas_parka.png"}

# U51: GUI(app\DiveToPalworld.cs の「影のみ更新」)から convert.ps1 -MaterialsOnly
# 経由で呼ばれるようになったので、失敗の**種類**を機械可読にする。
# convert.ps1 はこのマーカーを見てエンドユーザー向けの一文を出す。
# ここを増やす/改名するときは pipeline\cli\convert.ps1 の materials-only(noue)
# 分岐にある同名の文字列も必ず一緒に直すこと。
ERR_NO_FULL_BUILD = "##REPACK_ERROR## NO_FULL_BUILD"   # 一度もフル変換していない/中間成果が壊れている
ERR_STALE = "##REPACK_ERROR## STALE"                   # 影の濃さ以外の設定が変わっている
ERR_PREFLIGHT = "##REPACK_ERROR## PREFLIGHT_FAIL"      # 出来たpakが検品に落ちた

# 鮮度ゲートに引っかかったとき「何が変わったのか」をエンドユーザーの言葉で出す。
# GUI の表記に合わせる(app\DiveToPalworld.cs のラベル/ツールチップが正)。
JP_KEY_LABEL = {
    "shadow_lift": "影の濃さ", "unlit": "影なし", "force_two_sided": "両面表示",
    "shoulder_offset_deg": "肩の開き", "merge_fingers": "指を固定",
    "drop_bones": "削除ボーン", "vrm_path": "アバターファイル",
    "avatar_name": "アバター名", "genders": "性別", "engine_mode": "変換モード",
    "hair_sway": "揺れ髪", "hair_bones": "揺れ髪ボーン",
    "sway_cloth_bones": "揺れ布ボーン", "merge_eyes": "目の統合",
    "humanoid_json": "ボーン対応表", "paths": "ツールの場所",
    "license_confirmed": "規約の確認",
}


def _jp_keys(keys):
    return "、".join(JP_KEY_LABEL.get(k, k) for k in keys)


def _fmt_mtime(path):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "??"


# dev#7: 診断ログへ入力アバター/job.json等の生フルパスを無加工出力していた穴の修正。
# convert.ps1 の Mask-Path / Get-PathFacts(パスの事実のみ出力・生パスを出さない方針)を
# Python側でも踏襲する。以下2関数は**表示専用**(実際のファイル操作には一切使わない)。

def _drive_type(path):
    """Windowsのドライブ種別(固定/リムーバブル/ネットワーク等)。取得できなければ '?'。"""
    try:
        import ctypes
        drive = os.path.splitdrive(os.path.abspath(path))[0]
        if not drive:
            return "?"
        names = {0: "不明", 1: "無し", 2: "リムーバブル", 3: "固定",
                 4: "ネットワーク", 5: "CD-ROM", 6: "RAMディスク"}
        t = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
        return names.get(t, str(t))
    except Exception:
        return "?"


def _path_facts(p):
    """生フルパスの代わりに診断に要る事実だけを返す(convert.ps1のGet-PathFacts相当)。
    ファイル名(利用者のフォルダ名は含まない)+存在有無+ドライブ種別+パスの特徴のみで、
    ユーザー名等が乗る中間ディレクトリ名は一切出さない。"""
    if not p:
        return "(パス無し)"
    name = os.path.basename(p.rstrip("\\/")) or p
    exists = os.path.exists(p)
    non_ascii = any(ord(c) > 127 for c in p)
    has_space = " " in p
    is_unc = p.startswith("\\\\")
    onedrive = os.environ.get("OneDrive", "")
    under_onedrive = bool(onedrive) and os.path.normcase(p).startswith(os.path.normcase(onedrive))
    return (f"名前={name} 存在={exists} ドライブ種別={_drive_type(p)} "
            f"長さ={len(p)} 非ASCII文字={non_ascii} 空白={has_space} "
            f"UNC={is_unc} OneDrive配下={under_onedrive}")


def _display_path(p, bases=()):
    """生フルパスをログへ出さないための表示用ヘルパー(dev#7)。
    bases に列挙したディレクトリのいずれか配下なら相対パスにして返す
    (work配下の中間成果パスはこちらで足りる)。どれにも当てはまらなければ
    ファイル名のみを返す。実際のファイル操作には一切使わない(表示専用)。"""
    if not p:
        return p
    ap = os.path.abspath(p)
    for b in bases:
        if not b:
            continue
        try:
            b_abs = os.path.abspath(b)
            rp = os.path.relpath(ap, b_abs)
            if rp != "." and not rp.startswith(".."):
                return rp
        except Exception:
            continue
    return os.path.basename(ap.rstrip("\\/")) or ap


def _stat_tree(path):
    """(ファイル数, 合計バイト, 最も新しいmtime)。パスが無ければ (0, 0, None)。"""
    if os.path.isfile(path):
        st = os.stat(path)
        return 1, st.st_size, st.st_mtime
    n = size = 0
    newest = None
    for dirpath, _d, filenames in os.walk(path):
        for fn in filenames:
            st = os.stat(os.path.join(dirpath, fn))
            n += 1
            size += st.st_size
            newest = st.st_mtime if newest is None else max(newest, st.st_mtime)
    return n, size, newest


def _log_reuse(label, path, bases=()):
    """再利用するキャッシュの素性をログへ出す(危険性1への対策。省略禁止)。
    dev#7: 生フルパスではなく bases 相対(work配下ならそれ)で表示する。"""
    n, size, newest = _stat_tree(path)
    disp = _display_path(path, bases)
    if n == 0:
        print(f"[repack] 再利用 {label:16s}: **存在しない** {disp}")
        return None
    stamp = datetime.datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[repack] 再利用 {label:16s}: {n}件 / {size:,}B / 最終更新 {stamp}  {disp}")
    return newest


def main():
    ap = argparse.ArgumentParser(
        description="中間成果を再利用してpakだけ作り直す。"
                    "既定ではpreflightを飛ばすので、責任者に見せる前・記録前には必ず"
                    "フル変換+preflight_pak.pyを通すこと(--preflightを付ければ本ツールが検品まで通す)。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--job", help="job.json。作業域(build\\ の親)を決める。--job-dir と排他")
    ap.add_argument("--job-dir", help="作業域を直接指定する(job.json が無い実験用)")
    ap.add_argument("--out", required=True, help="出力する pak のパス")
    ap.add_argument("--tex-gain", type=float, default=None,
                    help="指定するとテクスチャを作り直す(既定: noue_work\\tex の既存物を流用)")
    ap.add_argument("--tex-dir", default=None,
                    help="テクスチャ出力先(既定 build\\noue_work\\tex)。gain違いを併存させたいとき用")
    ap.add_argument("--allow-stale", action="store_true",
                    help="job.json/アバターがキャッシュより新しくても続行する(既定は停止)")
    ap.add_argument("--shadow-lift", type=float, default=None,
                    help="影の濃さ k(0.0-1.0)。省略時は job.json の値を使う。"
                         "job.json を書き換えずに k だけ振りたいとき用")
    ap.add_argument("--unlit", dest="unlit", action="store_true", default=None,
                    help="unlit として扱う(=k を 0 扱いにする既存の意味論)")
    ap.add_argument("--preflight", action="store_true",
                    help="pak生成後に pipeline\\py\\preflight_pak.py を通す(約17秒)。"
                         "エンドユーザー向け(GUIの「影のみ更新」)は必ずこれを付ける。"
                         "開発の反復では既定(付けない)のままでよい")
    a = ap.parse_args()

    if bool(a.job) == bool(a.job_dir):
        raise SystemExit("--job か --job-dir のどちらか一方を指定すること")
    if a.job:
        job_path = os.path.abspath(a.job)
        job_dir = os.path.dirname(job_path)
    else:
        job_path, job_dir = None, os.path.abspath(a.job_dir)

    build = os.path.join(job_dir, "build")
    work = os.path.join(build, "noue_work")
    atlas = os.path.join(build, "atlas")
    mat_override = os.path.join(build, "noue_mat_override")

    _bases = (job_dir, REPO_DIR)  # dev#7: 診断ログの表示専用。実パスはそのまま各変数で使う
    print(f"[repack] 作業域: {_display_path(job_dir, (REPO_DIR,))}")
    # dev#42 item7(2026-07-29): live_template はU54 WP-Bでアバター非依存の共有キャッシュ
    # (work\_shared_cache\live_template\<fp12>\)へ移った。このアバター固有のbuild\配下に
    # あるとは限らない(初回はここに無く、この後 live_template.build_live_template() が
    # 組み立てる)ので、「フル変換が完走したか」の必須リストからは外す。このアバター固有の
    # 3ディレクトリだけを見る(app\DiveToPalworld.cs の HasNoueFullBuild() と厳密に一致させること)。
    for label, p in (("noue_work/variant", os.path.join(work, "variant")),
                     ("atlas", atlas), ("noue_mat_override", mat_override)):
        if not os.path.exists(p):
            raise SystemExit(
                f"{ERR_NO_FULL_BUILD}\n"
                f"再利用すべき中間成果が無い: {_display_path(p, _bases)}\n"
                "先に一度フル変換(pipeline\\cli\\convert.ps1)を通すこと。")

    # --- live_templateの解決: 自前でパスを組まず build_live_template() に委ねる ---
    # --job(job.json)がある通常経路では、共有キャッシュのフィンガープリント判定に
    # 従って既存を再利用するか(既に温めてあれば一瞬)、無ければこの場で組み立てる。
    # --job-dir単独(job.jsonが無い実験用途)では共有キャッシュを解決する材料
    # (job["paths"]["palworld_pak"])が無いため、従来どおり作業域直下を前提にする。
    job = None
    if job_path and os.path.exists(job_path):
        try:
            job = vp_core.load_job(job_path)
        except Exception as e:
            print(f"[repack] job.json を vp_core.load_job() で読めなかった"
                  f"(live_template解決不可。--job-dir相当の従来パスへ縮退): {e}")

    if job is not None:
        template = live_template.build_live_template(job)
    else:
        template = os.path.join(build, "live_template")
        if not os.path.exists(template):
            raise SystemExit(
                f"{ERR_NO_FULL_BUILD}\n"
                f"再利用すべき中間成果が無い: {_display_path(template, _bases)}\n"
                "先に一度フル変換(pipeline\\cli\\convert.ps1)を通すこと。")

    # --- 危険性1: キャッシュの鮮度を必ず表示し、明らかに古ければ止める ---
    print("[repack] --- 再利用するキャッシュ(結果を判断する前に必ず確認すること) ---")
    newest = {}
    for label, p in (("live_template", template), ("variant", os.path.join(work, "variant")),
                     ("atlas", atlas), ("mat_override", mat_override)):
        newest[label] = _log_reuse(label, p, _bases)
    fp = template.rstrip("\\/") + ".fingerprint.json"
    if os.path.exists(fp):
        with io.open(fp, encoding="utf-8") as f:
            print(f"[repack] live_template.fingerprint = {json.dumps(json.load(f), ensure_ascii=False)}")

    # 「最後にフル変換が完走したのはいつか」を基準にする。
    # live_template は fingerprint で世代管理される長寿命キャッシュなので、
    # 単純に全キャッシュの最古を基準にすると毎回誤検出する(実測)。
    # convert_noue.py が最後に書く build_provenance.json が完走の印になる。
    prov = os.path.join(build, "build_provenance.json")
    if os.path.exists(prov):
        cache_floor = os.path.getmtime(prov)
        print(f"[repack] 基準  最後のフル変換完了   : {_fmt_mtime(prov)}  {_display_path(prov, _bases)}")
    else:
        # 完走の印が無い場合は、毎回作り直される variant を代用する
        cache_floor = newest.get("variant") or min(v for v in newest.values() if v is not None)
        print("[repack] 基準  build_provenance.json が無いので variant の更新時刻を代用する")
    stale = []
    inputs = []
    if job_path and os.path.exists(job_path):
        inputs.append(("job.json", job_path))
        try:
            with io.open(job_path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
            if cfg.get("vrm_path") and os.path.exists(cfg["vrm_path"]):
                inputs.append(("アバター", cfg["vrm_path"]))
        except Exception as e:  # job.json が壊れていても鮮度表示だけは出す
            print(f"[repack] job.json を読めなかった(鮮度判定は job.json のみ): {e}")
    # U50-fast: 「job.json が新しい」だけで止めると、影の濃さを1文字変えた
    # だけでも停止してしまう(影の濃さは中間成果を一切変えないのに)。
    # 最後のフル変換時点の控え(job_snapshot.json)と中身を比較し、
    # 差分が SHADOW_ONLY_KEYS だけなら鮮度judgeの対象から外す。
    snap_path = os.path.join(build, "job_snapshot.json")
    job_diff_keys = None
    if job is not None and os.path.exists(snap_path):
        try:
            with io.open(snap_path, encoding="utf-8-sig") as f:
                snap = json.load(f)
            # 既にtemplate解決時にvp_core.load_job()済みのjobをそのまま使う
            # (二重ロード回避。palworld_locateのレジストリ/Steam探索を2回走らせない)
            cur = {k: v for k, v in job.items() if k != "job_dir"}
            job_diff_keys = sorted(set(snap) ^ set(cur)) or []
            job_diff_keys += sorted(k for k in set(snap) & set(cur) if snap[k] != cur[k])
            job_diff_keys = sorted(set(job_diff_keys))
            if not job_diff_keys:
                print("[repack] job.json は最後のフル変換時点と**内容が同一**"
                      f"(控え: {_display_path(snap_path, _bases)})")
            else:
                print(f"[repack] job.json の変更点: {job_diff_keys}  "
                      f"(控え: {_display_path(snap_path, _bases)})")
        except Exception as e:
            job_diff_keys = None
            print(f"[repack] job_snapshot.json と比較できなかった({e})。mtimeで判定する")

    for label, p in inputs:
        mt = os.path.getmtime(p)
        mark = ""
        # dev#7: job.json/アバターの生フルパスは利用者名を含みうる個人情報のため、
        # ログには出さず _path_facts() の事実(ファイル名/存在有無/ドライブ種別等)だけ出す。
        if (label == "job.json" and job_diff_keys is not None
                and set(job_diff_keys) <= set(SHADOW_ONLY_KEYS)):
            # 影の濃さ(と unlit)はテンプレート/variant/アトラスに一切影響しない。
            print(f"[repack] 入力     {label:16s}: 更新 {_fmt_mtime(p)}  {_path_facts(p)}"
                  f"  ← 差分は影の濃さのみ({job_diff_keys})。中間成果は有効")
            continue
        if mt > cache_floor:
            stale.append(label)
            mark = "  ← ★キャッシュより新しい"
        print(f"[repack] 入力     {label:16s}: 更新 {_fmt_mtime(p)}  {_path_facts(p)}{mark}")
    if stale:
        msg = ("[repack] 中間成果より新しい入力がある: " + ", ".join(stale) +
               "\n  このまま進むと**古い成果で判断する**ことになる"
               "(2026-07-25に実際に2件の取り違え事故あり)。\n"
               "  フル変換をやり直すか、意図的なら --allow-stale を付けること。")
        # U51: エンドユーザー(GUIの「影のみ更新」)にも何が起きたか伝わる一文を足す。
        # 「黙って古い成果を出す」も「開発者向けの語彙だけで落ちる」も等しく失格。
        if job_diff_keys:
            msg += ("\n  【影の濃さ以外の設定が変わっています】変わったのは: "
                    + _jp_keys(job_diff_keys) + "\n"
                    "  これらは「影のみ更新」では反映できません。"
                    "「フル変換」を実行してください。")
        elif "アバター" in stale:
            msg += ("\n  【アバターのファイルが更新されています】"
                    "「フル変換」を実行してください。")
        elif job_diff_keys is None:
            # 前回のフル変換が U50-fast より前(job_snapshot.json が無い)。
            # 何が変わったか判定できないので、安全側=フル変換を案内する
            msg += ("\n  【前回のフル変換の記録が無いため、設定が変わったか判定できません】"
                    "「フル変換」を実行してください。")
        if not a.allow_stale:
            raise SystemExit(ERR_STALE + "\n" + msg)
        print(msg + "\n  --allow-stale が指定されたので続行する。")
    print("[repack] " + "-" * 60)

    # --- テクスチャ ---
    tex_dir = os.path.abspath(a.tex_dir) if a.tex_dir else os.path.join(work, "tex")
    tex_replace = {}
    # U50-single 以降、注入されるアトラスは t00 の1枚だけになった(両スロットの
    # 統一MIが同じ Base Texture=t00 を指すため、convert_noue は t01 を作らない)。
    # したがって「スロットが揃っていること」ではなく「**フル変換が実際に作った
    # ぶんと同じものを差し替えていること**」を基準にする。
    #   - --tex-gain 指定時: アトラスPNGがあるスロットだけ作り直す
    #   - 未指定時       : noue_work\tex に実在するスロットだけ流用する
    # 1枚も解決できなければ止める(黙って素のテンプレートを出荷しない)。
    for slot, rel in TEX_SLOT_REL.items():
        out_uexp = os.path.join(tex_dir, *rel.split("/"))
        png = os.path.join(atlas, ATLAS_PNG[slot])
        if a.tex_gain is not None:
            if not os.path.exists(png):
                print(f"[repack] tex {slot}: アトラスPNGが無いので対象外 "
                      f"(フル変換もこのスロットを注入していない): {_display_path(png, _bases)}")
                continue
            template_uexp = os.path.join(template, *rel.split("/"))
            info = vp_texinject.inject_texture_file(
                template_uexp, png, out_uexp, alpha_coverage=True, gain=a.tex_gain)
            print(f"[repack] tex {slot}: gain={info['gain']:.4f} PSNR={info['psnr']:.2f}dB "
                  f"-> {_display_path(out_uexp, _bases)}")
        if not os.path.exists(out_uexp):
            print(f"[repack] tex {slot}: 注入済みテクスチャが無いので対象外 "
                  f"(フル変換もこのスロットを注入していない): {_display_path(out_uexp, _bases)}")
            continue
        tex_replace[rel] = out_uexp
        if a.tex_gain is None:
            print(f"[repack] tex {slot}: 既存を流用(作り直していない) "
                  f"最終更新 {_fmt_mtime(out_uexp)}  {_display_path(out_uexp, _bases)}")
    if not tex_replace:
        raise SystemExit(
            f"{ERR_NO_FULL_BUILD}\n"
            f"注入テクスチャが1枚も見つからない: {_display_path(tex_dir, _bases)}\n"
            "先に一度フル変換(pipeline\\cli\\convert.ps1)を通すこと"
            "(このまま進むとアバターのテクスチャが入らない pak になる)。")

    # --- 影の濃さ(shadow_lift)のMI: 毎回ここで作り直す(1秒未満) ---
    # テンプレートは k 非依存なので、pak を書く直前に統一MI 79件だけ差し替える。
    # これがフル変換(convert_noue.py → build_pak_from_avatar --mi-override-dir)と
    # **同じ関数・同じ出力先**であることが、両者の一致を構造的に保証している。
    mi_override_dir = os.path.join(build, "noue_mi_override")
    mi_replace = {}
    if job is not None:
        # template解決時に読み込み済みのjobをそのまま使う(二重ロード回避)。
        # ここで shadow_lift/unlit を書き換えるが、それより前(job_diff_keys比較)は
        # 既に済んでいるので、この場での変更が過去の判定に影響することはない
        if a.shadow_lift is not None:
            print(f"[repack] --shadow-lift {a.shadow_lift} で job.json の値"
                  f"({job.get('shadow_lift')})を上書きする")
            job["shadow_lift"] = a.shadow_lift
        if a.unlit:
            print("[repack] --unlit 指定(k=1.0 相当として扱う)")
            job["unlit"] = True
        out, n_mi, mi_info = live_template.build_shadow_mi_overrides(
            job, template, mi_override_dir)
        print(f"[repack] 影の濃さ: k={mi_info['k']:.4f} / MI {n_mi}件 / "
              f"uexp sha1={mi_info['uexp_sha1']}")
        # 旧経路(M_VP_{slot})も shadow_lift を焼いている。実機の描画には届いて
        # いない(参照ゼロ。DEV_NOTES 2026-07-25(27) §3)が、**焼き直さないと
        # 本ツールの出力がフル変換の出力とバイト一致しなくなる**ので、フル変換と
        # 同じ関数(convert_noue.prepare_material_overrides)をそのまま呼ぶ。
        meta_path = os.path.join(job_dir, "converted", "avatar_meta.json")
        if os.path.exists(meta_path):
            with io.open(meta_path, encoding="utf-8") as f:
                _meta = json.load(f)
            convert_noue.prepare_material_overrides(
                job, _meta, live_template.VARIANTS_DIR)
        else:
            print(f"[repack][WARN] avatar_meta.json が無いので M_VP は前回のまま: "
                  f"{_display_path(meta_path, _bases)}(描画には届かない経路なので絵は変わらないが、"
                  f"フル変換の出力とはバイト一致しない)")
    else:
        if a.shadow_lift is not None or a.unlit:
            raise SystemExit("--shadow-lift / --unlit は --job(job.json)が要る")
        n_mi = 0
        if os.path.isdir(mi_override_dir):
            print(f"[repack] 影の濃さ: --job-dir 指定のため既存の "
                  f"{_display_path(mi_override_dir, _bases)} を"
                  f"そのまま流用する(作り直していない)")
    for dirpath, _d, filenames in os.walk(mi_override_dir):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            mi_replace[os.path.relpath(p, mi_override_dir).replace("\\", "/")] = p

    # --- 差し替え表の組み立て ---
    replace_map = {}
    n_mat = 0
    for fn in sorted(os.listdir(mat_override)):
        n_mat += 1

    known_outfits = outfit_selection.catalog()
    try:
        selected_outfits = outfit_selection.selected(job or {}, known_outfits)
    except ValueError as e:
        raise SystemExit(str(e))
    variant_dir = os.path.join(work, "variant")
    n_var = 0
    for dirpath, _d, filenames in os.walk(variant_dir):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, variant_dir).replace("\\", "/")
            if (not rel.startswith("Player/Outfit/")
                    or outfit_selection.normalize_id(rel) in selected_outfits):
                replace_map[rel] = p
                n_var += 1
    print(f"[repack] 差し替え: tex {len(tex_replace)} / 影の濃さMI {len(mi_replace)} / "
          f"mat_override {n_mat} / variant {n_var} = 計{len(replace_map)}")

    private_root = os.path.join(build, "noue_work", "avatar_assets")
    try:
        private_files, private_info = avatar_assets.build_private_assets(
            job or {}, template, selected_outfits, variant_dir,
            tex_replace.get(TEX_SLOT_REL["body"]), mi_replace, private_root)
    except avatar_assets.AvatarAssetError as e:
        raise SystemExit(f"{ERR_NO_FULL_BUILD}\navatar-private asset build failed: {e}")
    print(f"[repack] avatar-private assets: namespace={private_info['namespace']} "
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
        raise SystemExit(f"{ERR_NO_FULL_BUILD}\n"
                         f"差し替え対象{len(replace_map)}件のうち{n_replaced}件しか一致しなかった "
                         "(live_template とキャッシュの版が食い違っている可能性がある)")

    out_pak = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out_pak) or ".", exist_ok=True)
    info = vp_pakwrite.build_pak(final_files, out_pak)
    print(f"[repack] pak生成: {_display_path(out_pak, _bases)} (総エントリ{info['n_entries']}件, "
          f"差し替え{n_replaced}件, size={info['size']:,})")

    # --- 検品(U51: エンドユーザー経路では必ず通す) ---
    if a.preflight:
        if not (job_path and os.path.exists(job_path)):
            raise SystemExit("--preflight は --job(job.json)が要る")
        preflight_py = os.path.join(REPO_DIR, "pipeline", "py", "preflight_pak.py")
        print("[repack] === preflight_pak.py(最終チェック / 約17秒) ===")
        r = subprocess.run([sys.executable, preflight_py, job_path, out_pak,
                            template, live_template.COOK_LOG])
        if r.returncode != 0:
            raise SystemExit(
                f"{ERR_PREFLIGHT}\n"
                f"最終チェックに失敗しました(preflight_pak.py exit={r.returncode})。"
                "このMODは使用しないでください。")
        print("[repack] preflight PASS")
    else:
        print("[repack] ※ preflight は実行していない。責任者へ見せる前・記録前には "
              "フル変換 + pipeline\\py\\preflight_pak.py を必ず通すこと。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
