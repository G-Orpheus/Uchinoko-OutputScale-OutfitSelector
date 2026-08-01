# -*- coding: utf-8 -*-
"""U16: Blender headless — マテリアルアトラスUV焼き込み。

指定した step02_{gender}.blend を開き、avatar_meta.jsonのスロットID
(=Blenderマテリアル名。convert_noue.py/resolve_textures()のdocstring、
および research\\ue_exit\\dump_avatar_mesh.py の運用実態のとおり、
Blender側マテリアル名は"m00","m01",...のスロットIDそのもの)ごとに
与えられたアフィン変換 (su,sv,ou,ov: u'=u*su+ou, v'=v*sv+ov) を
そのマテリアルが使う面のUVループへ適用し、新しいblendとして保存する。

対象スロットは適用前に、まず**面(ポリゴン)単位のタイル正規化**を行う
(2026-07-25追加。UVアイランドを隣のタイル v∈[-1,0] 等へ置いたままの
メッシュを、面ごとの整数シフトで [0,1] のタイルへ戻す。WRAPアドレッシングと
厳密に等価なので見た目は変わらない。詳細は `vp_atlas.py` の
「UVのタイル正規化」節)。その上で正規化後のUVバウンディングボックスを
`vp_atlas.detect_tiling()`にかけ、タイリング(UVが[0,1]を大きく超える。
レース・網目模様等でよくある)と判定されたら**変換をスキップする**
(2026-07-23深夜ぱん裁定: タイリング検出のみ行い、修復(焼き込み)は
しない。検出したスロットはアトラス化対象から外し、見た目崩れを許容する)。

2026-07-26追加: 整数シフトを掛けてもなお `vp_atlas.UV_CELL_CLAMP_TOL` を超えて
[0,1]をはみ出すスロット(=1個の面がタイル境界をまたいでいて、面単位の整数
シフトでは原理的に解消できないケース。diag_E_uv.md実測)も、同じ思想で
アトラス対象から除外する(閾値は変更しない。ビルドは止めずに見た目崩れを
許容し、呼び出し元がユーザー向け警告を出す)。

元のblend(呼び出し元の step02_female.blend / step02_male.blend)は
一切変更しない(=新しいファイルパスへ`bpy.ops.wm.save_as_mainfile`で
別名保存する。convert.ps1が共用するBlender工程の成果物を汚染しない
ための設計)。

実行:
  <blender.exe> --background --factory-startup --python-exit-code 1 --python \\
      vp_atlas_uvbake.py -- <blend_in> <blend_out> <transform.json> <report.json>

transform.json (入力): {"m00": [su,sv,ou,ov], ...} (アトラス対象スロットのみ。
  convert_noue.py が vp_atlas.slot_transforms(plan) の出力をそのままdumpする)

report.json (出力): {"m00": {"bbox":[umin,umax,vmin,vmax]|null,
  "bbox_normalized":[...], "wrap_shifted_faces":int,
  "overshoot_after_shift":float, "cell_clamped":bool,
  "tiling":bool, "applied":bool, "note":str(省略可)}, ...}
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import vp_atlas  # noqa: E402

TAG = "vp_atlas_uvbake"

argv = sys.argv[sys.argv.index("--") + 1:]
if len(argv) < 4:
    raise RuntimeError(
        "使い方: blender --background --factory-startup --python-exit-code 1 --python "
        "vp_atlas_uvbake.py -- <blend_in> <blend_out> <transform.json> <report.json>")
blend_in, blend_out, transform_json, report_json = argv[0], argv[1], argv[2], argv[3]

with open(transform_json, encoding="utf-8") as f:
    transform_map = json.load(f)  # {slot: [su,sv,ou,ov]}

bpy.ops.wm.open_mainfile(filepath=blend_in)

mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
if not mesh_objs:
    raise RuntimeError(f"MESHオブジェクトが見つからない: {blend_in}")

# --- Pass 1: スロットごとに**面(ポリゴン)単位で**UVループを収集し、
#     生のバウンディングボックスを取る ---
# (面単位にするのは Pass 1.5 のタイル正規化のため。ループ単位では
#  「この頂点はどの面のものか」が分からず、面を丸ごと平行移動できない)
slot_faces = {}   # slot_name -> [(obj_name, [loop_index, ...]), ...]
slot_loops = {}   # slot_name -> [(obj_name, loop_index), ...] (Pass 3 用)
slot_bbox = {}     # slot_name -> [umin,umax,vmin,vmax] (シフト前)
uv_by_obj = {}      # obj_name -> uv_layers[0].data (書き戻し用)
n_no_uv = 0

for obj in mesh_objs:
    if not obj.data.uv_layers:
        n_no_uv += 1
        continue
    uv_data = obj.data.uv_layers[0].data
    uv_by_obj[obj.name] = uv_data
    obj_slot_names = [ms.material.name if ms.material else None
                       for ms in obj.material_slots]
    for poly in obj.data.polygons:
        idx = poly.material_index
        slot_name = obj_slot_names[idx] if idx < len(obj_slot_names) else None
        if slot_name is None or slot_name not in transform_map:
            continue
        lis = list(poly.loop_indices)
        slot_faces.setdefault(slot_name, []).append((obj.name, lis))
        loops = slot_loops.setdefault(slot_name, [])
        for li in lis:
            uv = uv_data[li].uv
            u, v = float(uv[0]), float(uv[1])
            loops.append((obj.name, li))
            bbox = slot_bbox.get(slot_name)
            if bbox is None:
                slot_bbox[slot_name] = [u, u, v, v]
            else:
                if u < bbox[0]:
                    bbox[0] = u
                if u > bbox[1]:
                    bbox[1] = u
                if v < bbox[2]:
                    bbox[2] = v
                if v > bbox[3]:
                    bbox[3] = v

# --- Pass 1.5(2026-07-25、alicia が FATAL で止まっていた真因の修正):
#     **面単位のタイル正規化**。UVアイランドを隣のタイル(v∈[-1,0] 等)へ
#     置いたままのメッシュを、面ごとの整数シフトで [0,1] のタイルへ戻す。
#     WRAP アドレッシングと厳密に等価なので見た目は変わらない。
#     詳しい理由は vp_atlas.py の「UVのタイル正規化」節を読むこと。
#     ここではまだUVを書き換えない(タイリング除外と判定されたスロットは
#     一切触らない従来どおりの挙動を保つため、書き換えは Pass 2 で行う)。
slot_shift = {}       # slot_name -> [(obj_name, [li,...], ku, kv), ...]
slot_norm_bbox = {}   # slot_name -> [umin,umax,vmin,vmax] (シフト後)
slot_n_shifted = {}   # slot_name -> シフトした面数
for slot_name, faces in slot_faces.items():
    shifted = []
    n_shifted = 0
    nb = None
    for obj_name, lis in faces:
        uv_data = uv_by_obj[obj_name]
        ulo = vlo = 1e9
        uhi = vhi = -1e9
        for li in lis:
            uv = uv_data[li].uv
            u, v = float(uv[0]), float(uv[1])
            if u < ulo:
                ulo = u
            if u > uhi:
                uhi = u
            if v < vlo:
                vlo = v
            if v > vhi:
                vhi = v
        ku = vp_atlas.face_wrap_shift(ulo, uhi)
        kv = vp_atlas.face_wrap_shift(vlo, vhi)
        if ku or kv:
            n_shifted += 1
        shifted.append((obj_name, lis, ku, kv))
        lo_u, hi_u, lo_v, hi_v = ulo + ku, uhi + ku, vlo + kv, vhi + kv
        if nb is None:
            nb = [lo_u, hi_u, lo_v, hi_v]
        else:
            if lo_u < nb[0]:
                nb[0] = lo_u
            if hi_u > nb[1]:
                nb[1] = hi_u
            if lo_v < nb[2]:
                nb[2] = lo_v
            if hi_v > nb[3]:
                nb[3] = hi_v
    slot_shift[slot_name] = shifted
    slot_norm_bbox[slot_name] = nb
    slot_n_shifted[slot_name] = n_shifted

# --- Pass 2: タイリング判定+非タイリングのみ変換を適用 ---
# タイリング判定は**正規化後の**バウンディングボックスで行う。生のbboxで
# 判定すると、隣のタイルへ置かれただけのアイランド(実測 alicia m01/m02)を
# 「本物のタイリング」と誤認してアトラス対象から丸ごと外してしまう。
# 面自体が1タイルより広い本物のタイリングは、シフトしても収まらないので
# 正規化後のbboxでも従来どおり検出される。
report = {}
n_applied = 0
n_tiling = 0
n_wrap_normalized = 0
n_clamped = 0
n_overshoot_excluded = 0
for slot_name, xf in transform_map.items():
    bbox = slot_bbox.get(slot_name)
    if bbox is None:
        report[slot_name] = {"bbox": None, "tiling": False, "applied": False,
                              "note": "このblendに対応する面が見つからなかった"}
        continue
    nbox = slot_norm_bbox[slot_name]
    n_shifted = slot_n_shifted[slot_name]
    tiling = vp_atlas.detect_tiling(nbox[0], nbox[1], nbox[2], nbox[3])
    if tiling:
        n_tiling += 1
        report[slot_name] = {"bbox": bbox, "bbox_normalized": nbox,
                              "wrap_shifted_faces": n_shifted,
                              "tiling": True, "applied": False}
        continue
    # 整数シフトで吸収しきれなかったごく僅かなはみ出し(パディング・座標精度
    # 由来。実測 alicia m03=Alicia_eye が -0.004824)は、セル境界へ切り詰める。
    # 上限は vp_atlas.UV_CELL_CLAMP_TOL。
    #
    # 2026-07-26追加(diag_E_uv.md/オーナー裁定): それを超えるはみ出しは
    # **UV_CELL_CLAMP_TOL を緩めて通す(切り詰める)のではなく**、上のタイリング
    # 除外と同じ思想でこのスロットを丸ごとアトラス対象から外す(=元のUVのまま
    # 触らず、applied=False にする)。原因は1個の面がタイル境界をまたいでいて
    # 面単位の整数シフトでは原理的に[0,1]へ収まらないケース(境界またぎ面。
    # diag_E_uv.md実測: vrm_sample_b m13/m14/m17)。ビルドは止めず、見た目崩れを
    # 許容した上で警告する(呼び出し元 convert_noue.apply_atlas_uv_bake が
    # ユーザー向け警告を出す)。閾値そのものは一切変更していない。
    overshoot = vp_atlas.bbox_overshoot(nbox)
    if overshoot > vp_atlas.UV_CELL_CLAMP_TOL:
        n_overshoot_excluded += 1
        report[slot_name] = {"bbox": bbox, "bbox_normalized": nbox,
                              "wrap_shifted_faces": n_shifted,
                              "overshoot_after_shift": overshoot,
                              "tiling": False, "applied": False,
                              "excluded_reason": "overshoot",
                              "note": (
                                  f"面がUVタイル境界をまたぐため整数シフトでは"
                                  f"[0,1]に収めきれなかった(overshoot={overshoot:.6f}"
                                  f" > 上限{vp_atlas.UV_CELL_CLAMP_TOL})。アトラス"
                                  "対象から除外し元のUVのまま残した"
                                  "(見た目崩れの可能性あり)")}
        print(f"[{TAG}][WARN] {slot_name}: overshoot={overshoot:.6f} が上限"
              f"{vp_atlas.UV_CELL_CLAMP_TOL}を超えるためアトラス対象から除外"
              "(面がタイル境界をまたぐUV。見た目崩れを許容) "
              f"bbox_normalized={[round(x, 6) for x in nbox]}")
        continue
    do_clamp = vp_atlas.UV_IN_RANGE_TOL < overshoot <= vp_atlas.UV_CELL_CLAMP_TOL
    # U50-single修正(2026-07-25): xf は「アトラス画像の座標系(v下向き=UEのUV)」
    # で作られている。BlenderのUVは v上向きなので、そのまま適用すると行(v)方向
    # だけ上下逆のセルを指す(rows=1のときだけ恒等写像になるため今まで露見
    # しなかった)。詳細は vp_atlas.to_blender_transform() のdocstring。
    bxf = vp_atlas.to_blender_transform(xf)
    for obj_name, lis, ku, kv in slot_shift[slot_name]:
        uv_data = uv_by_obj[obj_name]
        for li in lis:
            u, v = uv_data[li].uv
            u = float(u) + ku
            v = float(v) + kv
            if do_clamp:
                u = vp_atlas.clamp01(u)
                v = vp_atlas.clamp01(v)
            nu, nv = vp_atlas.apply_transform(u, v, bxf)
            uv_data[li].uv = (nu, nv)
    n_applied += 1
    if n_shifted:
        n_wrap_normalized += 1
        print(f"[{TAG}] {slot_name}: {n_shifted}面のUVを隣のタイルから [0,1] へ"
              f"戻した(WRAP等価の整数シフト) 生bbox={[round(x, 6) for x in bbox]}"
              f" -> 正規化後={[round(x, 6) for x in nbox]}")
    if do_clamp:
        n_clamped += 1
        print(f"[{TAG}] {slot_name}: 残ったはみ出し {overshoot:.6f} を"
              f"セル境界へ切り詰めた(上限 {vp_atlas.UV_CELL_CLAMP_TOL})")
    report[slot_name] = {"bbox": bbox, "bbox_normalized": nbox,
                          "wrap_shifted_faces": n_shifted,
                          "overshoot_after_shift": overshoot,
                          "cell_clamped": do_clamp,
                          "tiling": False, "applied": True,
                          "blender_transform": list(bxf)}

# --- Pass 3(U50-single、受入ゲート): 焼き込み後のUVが「意図したセルの中」に
# 収まっているかを**UE座標系(v下向き)に直して**機械確認する。
# 実機NG(2026-07-25、行方向のセル取り違え)は、この検査があれば
# Blender工程だけで捕まえられた。ズレていたら report に out_of_cell=True を
# 立て、呼び出し元(convert_noue.apply_atlas_uv_bake)がビルドを止める。
EPS = 1e-3
for slot_name, xf in transform_map.items():
    r = report.get(slot_name)
    if not r or not r.get("applied"):
        continue
    su, sv, ou, ov = xf
    umin = vmin = 1e9
    umax = vmax = -1e9
    for obj_name, li in slot_loops[slot_name]:
        u, v_b = uv_by_obj[obj_name][li].uv
        v_ue = 1.0 - float(v_b)          # encode_uv0 と同じ変換
        u = float(u)
        umin = min(umin, u); umax = max(umax, u)
        vmin = min(vmin, v_ue); vmax = max(vmax, v_ue)
    inside = (umin >= ou - EPS and umax <= ou + su + EPS
              and vmin >= ov - EPS and vmax <= ov + sv + EPS)
    r["bbox_after_ue"] = [umin, umax, vmin, vmax]
    r["cell_ue"] = [ou, ou + su, ov, ov + sv]
    r["out_of_cell"] = not inside
    if not inside:
        print(f"[{TAG}][ERROR] {slot_name}: 焼き込み後のUVが意図したセルの外 "
              f"UE空間bbox=u[{umin:.4f},{umax:.4f}] v[{vmin:.4f},{vmax:.4f}] "
              f"期待セル=u[{ou:.4f},{ou + su:.4f}] v[{ov:.4f},{ov + sv:.4f}]")

os.makedirs(os.path.dirname(os.path.abspath(blend_out)) or ".", exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=blend_out)

with open(report_json, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)

print(f"[{TAG}] applied={n_applied} tiling_excluded={n_tiling} "
      f"overshoot_excluded={n_overshoot_excluded} "
      f"wrap_normalized={n_wrap_normalized} cell_clamped={n_clamped} "
      f"total_transform_slots={len(transform_map)} objects_without_uv={n_no_uv} "
      f"-> {blend_out}")
