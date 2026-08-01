# -*- coding: utf-8 -*-
"""U16受入ゲート: vp_atlas.py(マテリアルアトラス化コア)の自動テスト。

G1(アトラス組み立て): 3マテリアル以上の合成/実データで、アトラス組み立て後の
画像サイズ・UV変換後の座標が期待通りであることを検証する。
G2(タイリング検出): 意図的にタイリングUV(0〜4の範囲)を持つ合成マテリアルで、
正しく検出されることを検証する。
G4(無退行の前提条件): distinctテクスチャが1枚以下のラベルはアトラス化を
スキップする(=texture_transformが空)ことを検証する(convert_noue.py側で
このシグナルにより既存の単一テクスチャ注入へフォールバックする)。

実行: python test_vp_atlas.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_atlas  # noqa: E402
import vp_tex    # noqa: E402

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALICIA_META = os.path.join(REPO_DIR, "work", "alicia", "converted", "avatar_meta.json")
ALICIA_TEX_DIR = os.path.join(REPO_DIR, "work", "alicia", "textures")

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"[PASS] {label}")
    else:
        print(f"[FAIL] {label} {detail}")
        failures.append(label)


# ---------------------------------------------------------------- classify_material

def test_classify_material_single():
    """U50-single(2026-07-25、責任者裁定「入力アバターが何マテリアルでも
    1枚のアトラス・1マテリアルに畳む」): classify_material() は**常に0**を返す。

    旧テスト(body/parka のキーワード判定 3件)は仕様ごと廃止した。
    キーワード判定は SK 側のスロット役(t00/t01)と一致して初めて正しく、
    実測で注入対象60SK中16SKが不一致だった
    (work\\u50_equip\\out\\FINDINGS2.txt 5節)。単一化でこの不整合は
    構造的に起こりえなくなる。

    `research\\ue_exit\\dump_avatar_mesh.py` の classify_material() も
    同時に単一化してあり、**両者が同じ値を返すこと**が同期要件
    (モジュールdocstring参照)。あちらは bpy 依存で直接importできないため、
    ここでは vp_atlas 側の単一化のみを固定する。"""
    check("SINGLE_MATERIAL が有効", vp_atlas.SINGLE_MATERIAL is True)
    for name in ("body", "Parka", "Alicia_body_wear", "Alicia_hair_wear",
                 "Shata_overalls", "Heon_mohu", "0mofu", "", None):
        check(f"classify_material({name!r}) -> 0 (単一マテリアル)",
              vp_atlas.classify_material(name) == 0,
              f"got {vp_atlas.classify_material(name)}")


def test_to_blender_transform():
    """U50-single 実機NG(2026-07-25)の回帰テスト。

    `cell_transform()` はアトラス画像の座標系(v下向き=UEのUV)で作られるが、
    UV焼き込みは Blender の UV 座標系(v上向き)で行われ、
    `vp_meshrestore.encode_uv0()` が V_ue = 1 - V_blender と反転して書き出す。
    この差を吸収しないと**行(v)方向だけ違うセル**を引き、実機で顔が
    無地グレーになる(実測: 相関 NCC 0.7182)。

    rows=1 のとき恒等写像になる(=これまで露見しなかった理由)ことと、
    rows>1 で正しいセルに落ちることの両方を固定する。"""
    # rows=1: 恒等(従来の全アバターがこれ。無退行の根拠)
    for i in range(2):
        xf = vp_atlas.cell_transform(i, 1, 2)
        check(f"to_blender_transform: rows=1 cell{i} は恒等",
              vp_atlas.to_blender_transform(xf) == xf, str(xf))
    # rows=2: Blender空間で適用した結果を UE空間へ戻すと期待セルに入る
    for i in range(4):
        xf = vp_atlas.cell_transform(i, 2, 2)
        su, sv, ou, ov = xf
        bxf = vp_atlas.to_blender_transform(xf)
        ends = []
        for v_b_src in (0.0, 1.0):
            _u, v_b = vp_atlas.apply_transform(0.0, v_b_src, bxf)
            ends.append(1.0 - v_b)          # encode_uv0 と同じ変換
        lo, hi = min(ends), max(ends)
        check(f"to_blender_transform: rows=2 cell{i} が期待セル v[{ov},{ov + sv}] に入る",
              abs(lo - ov) < 1e-9 and abs(hi - (ov + sv)) < 1e-9,
              f"got v[{lo},{hi}]")


def test_to_blender_transform_rows3_plus():
    """2026-07-25の回帰テスト: **rows>=3 でも変換が正しい**ことを固定する。

    alicia の FATAL(セル包含チェックで停止)を調べたとき、当初「rows=2 まで
    しか検証していないので3行以上に別の破綻があるのでは」という見立てが
    立てられた。**その見立ては誤りである**ことを機械で固定しておく。

    代数(rows によらず成立する):
      bxf = (su, sv, ou, 1-sv-ov)
      Blender空間で焼く:  v_b' = v_b*sv + (1-sv-ov)
      encode_uv0 が反転: v_ue' = 1 - v_b' = sv*(1-v_b) + ov = sv*v_ue + ov   ∎
    sv, ov に一切の条件が付いていないので rows は何行でもよい。
    (真因は行数ではなく、UVアイランドが隣のタイルへ置かれていたこと。
     `test_face_wrap_shift` を参照)

    ここでは rows=1..5 / cols=1..5 の**全セル**について、
    「Blender空間で焼いた結果をUE空間へ戻すと、ちょうどそのセルになる」
    ことを確認する。
    """
    bad = []
    for rows in range(1, 6):
        for cols in range(1, 6):
            for i in range(rows * cols):
                xf = vp_atlas.cell_transform(i, rows, cols)
                su, sv, ou, ov = xf
                bxf = vp_atlas.to_blender_transform(xf)
                # u軸は反転しないのでそのまま
                u_lo, _ = vp_atlas.apply_transform(0.0, 0.0, bxf)
                u_hi, _ = vp_atlas.apply_transform(1.0, 0.0, bxf)
                ends = []
                for v_b_src in (0.0, 1.0):
                    _u, v_b = vp_atlas.apply_transform(0.0, v_b_src, bxf)
                    ends.append(1.0 - v_b)     # encode_uv0 と同じ変換
                v_lo, v_hi = min(ends), max(ends)
                ok = (abs(u_lo - ou) < 1e-9 and abs(u_hi - (ou + su)) < 1e-9
                      and abs(v_lo - ov) < 1e-9 and abs(v_hi - (ov + sv)) < 1e-9)
                if not ok:
                    bad.append(f"rows={rows} cols={cols} i={i} "
                               f"got u[{u_lo},{u_hi}] v[{v_lo},{v_hi}] "
                               f"want u[{ou},{ou + su}] v[{ov},{ov + sv}]")
    check("to_blender_transform: rows/cols=1..5 の全セルがUE空間で期待セルに一致",
          not bad, f"NG {len(bad)}件: {bad[:5]}")

    # 3行以上のグリッドが実際に使われる枚数であることも固定する
    for n, want in ((7, (3, 3)), (8, (3, 3)), (9, (3, 3)),
                    (10, (3, 4)), (13, (4, 4)), (17, (4, 5))):
        check(f"compute_grid({n}) == {want} (rows>=3 が実際に出る)",
              vp_atlas.compute_grid(n) == want, str(vp_atlas.compute_grid(n)))

    # rows=3 のグリッドで全セルがUE空間を隙間なく・重なり無く覆う
    cells = []
    for i in range(9):
        su, sv, ou, ov = vp_atlas.cell_transform(i, 3, 3)
        cells.append((ou, ov, ou + su, ov + sv))
    area = sum((c[2] - c[0]) * (c[3] - c[1]) for c in cells)
    check("cell_transform(rows=3): 9セルの面積合計が 1.0", abs(area - 1.0) < 1e-9,
          str(area))

    def overlap(a, b):
        return not (a[2] <= b[0] + 1e-12 or b[2] <= a[0] + 1e-12
                    or a[3] <= b[1] + 1e-12 or b[3] <= a[1] + 1e-12)
    check("cell_transform(rows=3): 全セルが重なり無し",
          not any(overlap(cells[i], cells[j])
                  for i in range(9) for j in range(i + 1, 9)))


def test_face_wrap_shift():
    """2026-07-25 alicia FATAL の**真因**の回帰テスト。

    真因は行数ではなく、**UVアイランドが隣のタイル(v∈[-1,0])へ置かれた
    メッシュ**だった。単体テクスチャならWRAPアドレッシングで正しく描けるが、
    アトラスへ詰めると隣のセル(別テクスチャ)を舐めてしまう。
    実測: m00 Alicia_body は 2808面中わずか **4面**、
          m03 Alicia_eye は 1タイルではなく -0.004824 の縁のはみ出し。
    """
    # 既に [0,1] に収まっている面は**絶対に**動かさない(既存アバター無退行)
    for lo, hi in ((0.0, 1.0), (0.2, 0.8), (0.0, 0.0), (1.0, 1.0),
                   (-1e-5, 1.0 + 1e-5)):
        check(f"face_wrap_shift({lo},{hi}) == 0 (範囲内は不動)",
              vp_atlas.face_wrap_shift(lo, hi) == 0,
              str(vp_atlas.face_wrap_shift(lo, hi)))

    # 隣のタイルへ置かれた面 -> 整数シフトで [0,1] へ戻る
    cases = [(-0.9, -0.1, 1), (-1.9, -1.1, 2), (1.2, 1.8, -1), (2.1, 2.9, -2)]
    for lo, hi, want in cases:
        got = vp_atlas.face_wrap_shift(lo, hi)
        check(f"face_wrap_shift({lo},{hi}) == {want}", got == want, str(got))
        check(f"face_wrap_shift({lo},{hi}): シフト後が [0,1] に収まる",
              -1e-9 <= lo + got and hi + got <= 1.0 + 1e-9,
              f"[{lo + got},{hi + got}]")

    # シフト量は必ず整数(WRAP等価であるための必要条件)
    for lo, hi in ((-0.443, 0.02), (-3.7, -3.2), (5.1, 5.4)):
        k = vp_atlas.face_wrap_shift(lo, hi)
        check(f"face_wrap_shift({lo},{hi}) は整数", isinstance(k, int) and k == int(k),
              repr(k))

    # 面自体が1タイルより広い(本物のタイリング)はシフトでは救えない
    # -> シフト後もはみ出したままで、detect_tiling が従来どおり除外する
    lo, hi = 0.0, 4.0
    k = vp_atlas.face_wrap_shift(lo, hi)
    check("face_wrap_shift: 面幅4.0はシフトしても [0,1] に収まらない",
          not (-1e-9 <= lo + k and hi + k <= 1.0 + 1e-9), f"k={k}")
    check("detect_tiling: シフト後bboxでも本物のタイリングは検出される",
          vp_atlas.detect_tiling(lo + k, hi + k, 0.0, 1.0) is True)


def test_bbox_overshoot_and_clamp():
    """整数シフトで吸収しきれない縁のはみ出し(実測 alicia m03 = 0.004824)の
    扱い。**切り詰めてよい上限は `UV_CELL_CLAMP_TOL`**で、それを超えるものは
    切り詰めず vp_atlas_uvbake.py の Pass 3 でビルドを止める(ゲートは緩めない)。"""
    check("bbox_overshoot: 完全に範囲内 -> 0.0",
          vp_atlas.bbox_overshoot([0.0, 1.0, 0.0, 1.0]) == 0.0)
    over = vp_atlas.bbox_overshoot([0.164348, 0.973056, -0.004824, 0.942763])
    check("bbox_overshoot: alicia m03 実測値 -> 0.004824",
          abs(over - 0.004824) < 1e-9, str(over))
    check("bbox_overshoot: alicia m03 は切り詰め上限の内側",
          vp_atlas.UV_IN_RANGE_TOL < over <= vp_atlas.UV_CELL_CLAMP_TOL)
    check("bbox_overshoot: 1タイル分のズレは切り詰め上限を超える(=ゲートで止まる)",
          vp_atlas.bbox_overshoot([0.0, 1.0, -0.442973, 0.990797])
          > vp_atlas.UV_CELL_CLAMP_TOL)
    check("UV_CELL_CLAMP_TOL は 1タイルよりはるかに小さい",
          vp_atlas.UV_CELL_CLAMP_TOL < 0.1)
    check("clamp01: 範囲内はそのまま(ビット同一)", vp_atlas.clamp01(0.3) == 0.3)
    check("clamp01(-0.004824) == 0.0", vp_atlas.clamp01(-0.004824) == 0.0)
    check("clamp01(1.004824) == 1.0", vp_atlas.clamp01(1.004824) == 1.0)


def test_wrap_shift_is_visually_equivalent():
    """整数シフトが WRAP アドレッシングと厳密に等価であること
    (=見た目が変わらないことの根拠)を固定する。

    WRAP では u と u+k(kは整数)は同じテクセルを指す。面を丸ごと整数だけ
    平行移動しても、面内の各頂点が指すテクセルは1つも変わらない。"""
    def frac(x):
        return x - math.floor(x)
    face_v = [-0.42, -0.31, -0.05]          # alicia m00 の該当面に近い値
    k = vp_atlas.face_wrap_shift(min(face_v), max(face_v))
    same = all(abs(frac(v) - frac(v + k)) < 1e-12 for v in face_v)
    check("面の整数シフトは WRAP と等価(全頂点の小数部が不変)", same,
          str([(frac(v), frac(v + k)) for v in face_v]))
    check("整数シフト後の面は [0,1] に収まる",
          all(0.0 <= v + k <= 1.0 for v in face_v), str([v + k for v in face_v]))


def test_compute_grid():
    check("compute_grid(1) == (1,1)", vp_atlas.compute_grid(1) == (1, 1))
    check("compute_grid(3) == (2,2)", vp_atlas.compute_grid(3) == (2, 2),
          str(vp_atlas.compute_grid(3)))
    check("compute_grid(4) == (2,2)", vp_atlas.compute_grid(4) == (2, 2))
    check("compute_grid(5) == (2,3)", vp_atlas.compute_grid(5) == (2, 3),
          str(vp_atlas.compute_grid(5)))
    check("compute_grid(9) == (3,3)", vp_atlas.compute_grid(9) == (3, 3))
    for n in (1, 2, 3, 5, 7, 8, 12):
        rows, cols = vp_atlas.compute_grid(n)
        check(f"compute_grid({n}): rows*cols >= n", rows * cols >= n,
              f"rows={rows} cols={cols}")


# ---------------------------------------------------------------- cell_transform / apply_transform

def test_cell_transform():
    rows, cols = 2, 3
    su, sv, ou, ov = vp_atlas.cell_transform(4, rows, cols)  # r=1,c=1
    check("cell_transform(4,2,3): su==1/3", abs(su - 1 / 3) < 1e-9)
    check("cell_transform(4,2,3): sv==1/2", abs(sv - 1 / 2) < 1e-9)
    check("cell_transform(4,2,3): ou==1/3", abs(ou - 1 / 3) < 1e-9)
    check("cell_transform(4,2,3): ov==1/2", abs(ov - 1 / 2) < 1e-9)

    # index=4のセルは u in [1/3,2/3], v in [1/2,1] のはず。
    # マテリアル内uv(0.5,0.5)(中央)を変換すると、そのセルの中央に来る
    u2, v2 = vp_atlas.apply_transform(0.5, 0.5, (su, sv, ou, ov))
    check("apply_transform: セル境界内(u)", 1 / 3 <= u2 <= 2 / 3, f"u2={u2}")
    check("apply_transform: セル境界内(v)", 1 / 2 <= v2 <= 1.0, f"v2={v2}")
    check("apply_transform: u,v=(0,0) -> セル左上隅",
          vp_atlas.apply_transform(0.0, 0.0, (su, sv, ou, ov)) == (ou, ov))
    check("apply_transform: u,v=(1,1) -> セル右下隅",
          vp_atlas.apply_transform(1.0, 1.0, (su, sv, ou, ov)) == (ou + su, ov + sv))

    # 全セルが重なり無くタイル張りされていることを確認(index 0..5)
    covered = []
    for i in range(rows * cols):
        s = vp_atlas.cell_transform(i, rows, cols)
        covered.append((s[2], s[3], s[2] + s[0], s[3] + s[1]))  # (u0,v0,u1,v1)
    def overlap(a, b):
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
    any_overlap = any(overlap(covered[i], covered[j])
                       for i in range(len(covered)) for j in range(i + 1, len(covered)))
    check("cell_transform: 全セルが重なり無し", not any_overlap)


# ---------------------------------------------------------------- detect_tiling (G2)

def test_detect_tiling():
    check("detect_tiling: 通常UV[0,1] -> False",
          vp_atlas.detect_tiling(0.0, 1.0, 0.0, 1.0) is False)
    check("detect_tiling: 軽微なはみ出し(-0.02,1.02) -> False",
          vp_atlas.detect_tiling(-0.02, 1.02, -0.01, 1.01) is False)
    check("detect_tiling: uが0〜4のタイリング -> True",
          vp_atlas.detect_tiling(0.0, 4.0, 0.0, 1.0) is True)
    check("detect_tiling: u,vとも0〜3のタイリング -> True",
          vp_atlas.detect_tiling(0.0, 3.0, 0.0, 3.0) is True)
    check("detect_tiling: レンジは小さいが大きくオフセット(-0.6,0.5) -> True",
          vp_atlas.detect_tiling(-0.6, 0.5, 0.0, 1.0) is True)


# ---------------------------------------------------------------- build_atlas_image (G1)

def test_build_atlas_image():
    import numpy as np
    red = np.zeros((64, 64, 4), np.uint8)
    red[:, :, 0] = 255
    red[:, :, 3] = 255
    green = np.zeros((32, 32, 4), np.uint8)
    green[:, :, 1] = 255
    green[:, :, 3] = 255
    blue = np.zeros((100, 100, 4), np.uint8)
    blue[:, :, 2] = 255
    blue[:, :, 3] = 255

    canvas, rows, cols, cs = vp_atlas.build_atlas_image([red, green, blue], cell_size=32)
    check("build_atlas_image(3枚): grid==(2,2)", (rows, cols) == (2, 2))
    check("build_atlas_image(3枚): cell_size==32", cs == 32)
    check("build_atlas_image(3枚): canvas.shape==(64,64,4)",
          canvas.shape == (64, 64, 4), str(canvas.shape))

    def cell(r, c):
        return canvas[r * cs:(r + 1) * cs, c * cs:(c + 1) * cs]

    check("build_atlas_image: cell(0,0)は赤", (cell(0, 0)[:, :, 0] == 255).all()
          and (cell(0, 0)[:, :, 1] == 0).all())
    check("build_atlas_image: cell(0,1)は緑", (cell(0, 1)[:, :, 1] == 255).all()
          and (cell(0, 1)[:, :, 0] == 0).all())
    check("build_atlas_image: cell(1,0)は青", (cell(1, 0)[:, :, 2] == 255).all()
          and (cell(1, 0)[:, :, 0] == 0).all())
    check("build_atlas_image: cell(1,1)は未使用(黒)", (cell(1, 1)[:, :, :3] == 0).all())

    # max_canvas制約: セルサイズが自動縮小されること
    imgs9 = [red] * 9
    canvas9, rows9, cols9, cs9 = vp_atlas.build_atlas_image(imgs9, cell_size=2048, max_canvas=1024)
    check("build_atlas_image(9枚,max_canvas=1024): cell_sizeが自動縮小",
          cs9 * max(rows9, cols9) <= 1024, f"cs9={cs9} rows9={rows9} cols9={cols9}")


# ---------------------------------------------------------------- plan_label / plan_avatar

def test_plan_label_no_atlas_when_single_texture():
    transforms, rows, cols = vp_atlas.plan_label(["t00.png"])
    check("plan_label(1枚): transformsは空(アトラス不要)", transforms == {})
    check("plan_label(1枚): rows,cols==(1,1)", (rows, cols) == (1, 1))


def make_synthetic_meta(pairs):
    """pairs: [(slot_id, orig_name, texture_filename), ...] からavatar_meta.json風dictを作る"""
    slots = {}
    for slot_id, orig_name, tex in pairs:
        slots[slot_id] = {"orig_name": orig_name, "texture": tex}
    return {"slots": slots}


def test_plan_avatar_two_material_single_atlas():
    """U50-single: toto相当(m00=body/t00.png, m01=parka/t01.png)は、
    単一マテリアル化により**1枚のアトラス(2セル)**に畳まれる。
    旧仕様では2ラベルへ分かれ、各1枚なのでアトラス化されなかった。"""
    meta = make_synthetic_meta([
        ("m00", "body", "t00.png"),
        ("m01", "parka", "t01.png"),
    ])
    plan, skipped = vp_atlas.plan_avatar(meta)
    check("plan_avatar(toto相当): 全スロットがbodyラベルへ",
          plan["body"]["texture_order"] == ["t00.png", "t01.png"],
          str(plan["body"]["texture_order"]))
    check("plan_avatar(toto相当): parkaラベルは空", plan["parka"]["texture_order"] == [])
    check("plan_avatar(toto相当): 2枚なのでアトラス化される",
          set(plan["body"]["texture_transform"]) == {"t00.png", "t01.png"})
    check("plan_avatar(toto相当): slot_transformsは2スロット分",
          set(vp_atlas.slot_transforms(plan)) == {"m00", "m01"})
    check("plan_avatar(toto相当): skippedは空", skipped == [])


def test_plan_avatar_multi_material_single():
    """U50-single: 4マテリアルは全部1枚のアトラス(2x2)へ畳まれる。"""
    meta = make_synthetic_meta([
        ("m00", "body", "t00.png"),
        ("m01", "eye", "t01.png"),
        ("m02", "face", "t02.png"),
        ("m03", "wear", "t03.png"),   # 旧仕様ではparka、今は同じアトラスへ
    ])
    plan, skipped = vp_atlas.plan_avatar(meta)
    check("plan_avatar(4材質): skippedは空", skipped == [])
    check("plan_avatar(4材質): texture_order==[t00..t03]",
          plan["body"]["texture_order"] == ["t00.png", "t01.png", "t02.png", "t03.png"],
          str(plan["body"]["texture_order"]))
    check("plan_avatar(4材質): grid==(2,2) (n=4)",
          (plan["body"]["rows"], plan["body"]["cols"]) == (2, 2))

    sx = vp_atlas.slot_transforms(plan)
    check("slot_transforms: 全4スロット分", set(sx) == {"m00", "m01", "m02", "m03"}, str(sx.keys()))
    check("slot_transforms: m00 == cell(0,0)相当", sx["m00"] == (0.5, 0.5, 0.0, 0.0), str(sx["m00"]))
    check("slot_transforms: m01 == cell(0,1)相当", sx["m01"] == (0.5, 0.5, 0.5, 0.0), str(sx["m01"]))
    check("slot_transforms: m02 == cell(1,0)相当", sx["m02"] == (0.5, 0.5, 0.0, 0.5), str(sx["m02"]))
    check("slot_transforms: m03 == cell(1,1)相当", sx["m03"] == (0.5, 0.5, 0.5, 0.5), str(sx["m03"]))


def test_plan_avatar_skips_non_png():
    meta = make_synthetic_meta([
        ("m00", "body", "t00.png"),
        ("m01", "eye", "t01.jpg"),   # PNG以外 -> 除外
        ("m02", "face", "t02.png"),
    ])
    plan, skipped = vp_atlas.plan_avatar(meta)
    check("plan_avatar: 非PNGスロットがskippedに記録される", skipped == [("m01", "t01.jpg")])
    check("plan_avatar: 非PNGスロットはtexture_orderに含まれない",
          "t01.jpg" not in plan["body"]["texture_order"]
          and "t01.jpg" not in plan["parka"]["texture_order"])


# ---------------------------------------------------------------- 実データ(alicia)での検証

def test_plan_avatar_alicia_real_data():
    if not os.path.exists(ALICIA_META):
        print(f"[SKIP] test_plan_avatar_alicia_real_data: {ALICIA_META} が無い")
        return
    with open(ALICIA_META, encoding="utf-8") as f:
        meta = json.load(f)
    plan, skipped = vp_atlas.plan_avatar(meta)
    check("alicia実データ: skippedは空(全12スロットPNG)", skipped == [])
    check("alicia実データ: 全12スロットが1枚のアトラスへ(distinct 6枚)",
          plan["body"]["texture_order"] == ["t00.png", "t01.png", "t02.png",
                                            "t03.png", "t04.png", "t05.png"],
          str(plan["body"]["texture_order"]))
    check("alicia実データ: parkaラベルは空", plan["parka"]["texture_order"] == [])
    check("alicia実データ: スロット数12", len(plan["body"]["slots"]) == 12,
          str(plan["body"]["slots"]))
    check("alicia実データ: grid==(2,3) (n=6)",
          (plan["body"]["rows"], plan["body"]["cols"]) == (2, 3))
    sx = vp_atlas.slot_transforms(plan)
    check("alicia実データ: slot_transformsは全12スロット分(両ラベルともアトラス対象)",
          len(sx) == 12, str(len(sx)))

    if os.path.isdir(ALICIA_TEX_DIR):
        paths = [os.path.join(ALICIA_TEX_DIR, fn) for fn in plan["body"]["texture_order"]]
        if all(os.path.exists(p) for p in paths):
            canvas, rows, cols, cs = vp_atlas.build_atlas_from_paths(paths)
            check("alicia実データ: build_atlas_from_paths(body)がgrid(2,3)どおりの寸法",
                  canvas.shape == (rows * cs, cols * cs, 4), str(canvas.shape))
            check("alicia実データ: build_atlas_from_paths(body) rows,cols==(2,3)",
                  (rows, cols) == (2, 3))
        else:
            print("[SKIP] alicia実テクスチャの一部が無い(build_atlas_from_paths実データ検証)")


def main():
    test_classify_material_single()
    test_to_blender_transform()
    test_to_blender_transform_rows3_plus()
    test_face_wrap_shift()
    test_bbox_overshoot_and_clamp()
    test_wrap_shift_is_visually_equivalent()
    test_compute_grid()
    test_cell_transform()
    test_detect_tiling()
    test_build_atlas_image()
    test_plan_label_no_atlas_when_single_texture()
    test_plan_avatar_two_material_single_atlas()
    test_plan_avatar_multi_material_single()
    test_plan_avatar_skips_non_png()
    test_plan_avatar_alicia_real_data()

    print()
    if failures:
        print(f"=== FAIL: {len(failures)}件 ===")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)
    print("=== ALL PASS ===")


if __name__ == "__main__":
    main()
