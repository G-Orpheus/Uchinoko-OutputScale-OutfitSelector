"""U4 T1: 実アバターメッシュ(パルワールド骨格にウェイト済み)のレンダー頂点分割ダンプ。

パイプライン調査結果(work\\toto配下の実成果物とpipeline\\blender\\step0*.pyの
ソースを読んで特定):
  - `pipeline\\blender\\step02_retarget.py` の出力 `converted\\step02_{gender}.blend`
    が「パル骨格へウェイト移植+バインド済み」の最終形(docstring:
    「ウェイトをパル名へ移植...バインド」)。
  - `step03_export_fbx.py` はこれをFBX化するだけの後工程(ジオメトリ・
    ウェイトの追加変更なし。HairSwayオブジェクトと`hair_*`ボーンを本体
    出力から除外するのみ)。
  - よって本スクリプトは`step02_{gender}.blend`を直接開き、step03と同じ
    「HairSwayを除く全MESHオブジェクト」を対象にする(FBXへの往復エクスポート/
    インポートによる再量子化を避けるため、devtools\\dump_restore_geometry.py
    (FBXベース)より.blend直読みを選んだ)。
  - toto(女性)実測: step02_female.blend は ARMATURE(65ボーン、Bronze001と
    同数=同一パル骨格) + MESH geo_00(21402頂点)/geo_01(1399)/geo_02(4320)/
    geo_03(2524)の4オブジェクト。HairSwayオブジェクトは非存在(hair_sway
    機能未使用のtoto build)。

## レンダー頂点分割(UEのcookと同じ考え方)

Blenderの頂点は複数ポリゴンで共有され、UV/法線はループ(頂点×隣接面)属性
なので、(位置, UV, 法線, タンジェント, 従法線符号)の組が異なるループは
別頂点として複製する。同じ組のループは同一頂点として共有する(重複排除)。
スキンウェイトは元のBlender頂点(vi)に紐づくため、分割後の複数頂点が
同じviを指していれば同じウェイトを持つ。

## 出力形式(次の人が別メッシュで再現できる粒度)

JSON、トップレベル:
  {"gender": "Female", "source_blend": "...", "max_influences": 8,
   "num_vertices": N, "num_triangles": T,
   "vertices": [{"pos":[x,y,z](m,ワールド座標), "normal":[x,y,z],
                 "tangent":[x,y,z], "bitangent_sign": +-1.0,
                 "uv":[u,v], "weights": [[bone_name, weight], ...] (和=1)}, ...],
   "triangles": [[i0,i1,i2], ...] }

pos/normal/tangentはワールド座標変換済み(devtools\\dump_restore_geometry.py
と同じ流儀: mw@position、(mw.to_3x3().normalized())@法線/タンジェント)。
weightsは頂点ごとに重み降順ソート済み、上位max_influences個に切り捨てた上で
和=1へ再正規化済み(cooked skin_weightのu8エンコード時の再正規化と二重に
なるが、G1ゲート(和=1±1e-3)をダンプ単体で検証可能にするため、この段階で
正規化しておく)。

## 重要な単位系の罠(本セッションで発見、次の人向けに明記)

`pipeline\\blender\\step02_retarget.py`の`global_scale_and_place()`は
アバターをパルワールドの実寸(RefSkeletonがcm単位)に直接一致させるよう
スケール・配置する。**その結果、step02_{gender}.blendのオブジェクト座標の
生の数値は「Blenderが1ユニット=1mだと仮定して扱う値」がそのまま
センチメートル相当になる**(scale_lengthは変更されておらずBlender既定の
ままだが、メッシュの実寸自体をパルワールドのcm数値に合わせて拡大している
ため)。実測: toto(Female)のz座標範囲が[0.0, 126.0](=U3が20角両錐の
Z_TOP=126cmとして独立に定めた「頭の高さ」と完全一致)。実際に1m=1mの
メッシュなら数値は[0, 1.26]になるはずで、そうなっていない。

`pipeline\\py\\vp_meshrestore.py`の`encode_position()`/
`blender_pos_to_ue_cm()`は「Blender側位置はm単位」という前提で内部で
×100している(P2セッションがFBX経由(=step03のglobal_scale=0.01適用後、
実寸mに変換された後)のジオメトリで検証した式のため)。本ダンプは
step03のFBXエクスポートを経由せず.blendを直接読むため、その×100は
二重適用になり10000倍の位置ズレを起こす(実際に発生し、build_avatar_variant.py
の最初の実行でvp_core.parse_skeletalmesh_buffersの範囲外チェック
(position頂点0=(0.0, 1585.97, 9296.11)cm)で検出した)。

対策: 本スクリプトは`pos`をワールド座標の生値を**100で割ってから**
記録する(=`encode_position()`が想定する「m単位」に変換してから渡す。
ちょうどstep03_export_fbx.pyの`global_scale=0.01`と同じ意味の補正)。
normal/tangentは単位方向ベクトルなのでスケールの影響を受けず補正不要。

実行: <blender.exe> --background --factory-startup --python-exit-code 1 --python dump_avatar_mesh.py -- \\
    <step02_blend_path> <gender:Male|Female> <out.json> [max_influences=8] [avatar_meta.jsonパス] [output_scale=1.0]

## U7 T1で追加: マテリアル別三角形分類(format=2)

各三角形に`material`(0=body/1=parka)を追加した。判定は`avatar_meta.json`
(既定: step02_blend_pathと同じ`converted`フォルダの`avatar_meta.json`)の
`slots[m??]['orig_name']`を読み、`classify_material()`で0/1へ分類する
(オブジェクト単位ではなく、面のマテリアルスロット単位。1オブジェクトに
複数マテリアルが混在する場合(alicia実測: geo_07/geo_08)にも対応する)。

判定規則(`classify_material`のdocstring参照): orig_nameが完全一致
'body'→0、'parka'→1。それ以外は'wear'/'cloth'/'parka'/'outfit'/'costume'の
いずれかを含むかで判定(含む→1=parka、含まない→0=body)。toto(Female)は
'body'/'parka'の完全一致のみで100%決着(オラクル実測: m00=49435/m01=8446、
テンプレートSK Section0/1と厳密一致)。alicia(Male)は12マテリアル
(m00〜m11)を持ち、'body_wear'/'wear'/'hair_wear'の3件が'wear'を含むため
1(parka)、残り9件(body/eye/face/eye_white/face_mastuge/hair/
hair_trans_zwrite/hair_trans/other_zwrite)は0(body)に分類される
(m11 'Alicia_other_zwrite'は装飾品/アクセサリの可能性があり判別が難しい
ため既定の0側へ倒した。次の人向けの判断根拠は
docs\\REPORT_U7_*.md参照。オラクル未確認、後述)。

出力トップレベルに以下を追加: `"format": 2`,
`"material_slot_map": {slot_name: 0|1, ...}`,
`"material_triangle_counts": {"0": N0, "1": N1}`。
`triangles`の各要素は`[i0, i1, i2, material]`(4要素、末尾がmaterial)に変更
(旧format=1の3要素`[i0,i1,i2]`とは非互換。旧形式ダンプ・旧build_avatar_variant.py
はそのままでは読めなくなる。次工程(T2)のビルダーは新format=2前提で書き直す)。
"""
import json
import math
import os
import sys

import bmesh
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
blend_path, gender, out_path = argv[0], argv[1], argv[2]
max_influences = int(argv[3]) if len(argv) > 3 else 8
avatar_meta_path = argv[4] if len(argv) > 4 else os.path.join(
    os.path.dirname(blend_path), "avatar_meta.json")
output_scale = float(argv[5]) if len(argv) > 5 else 1.0
if not (0.01 <= output_scale <= 100.0):
    raise ValueError(f"output_scaleは0.01〜100.0で指定してください: {output_scale}")

ROUND = 6


# U50-single: 単一マテリアル化(pipeline\py\vp_atlas.py の同名定数と同期必須)
SINGLE_MATERIAL = True


def classify_material(orig_name):
    """avatar_meta.jsonのslots[m??]['orig_name']から0(body)/1(parka)を判定する。

    完全一致'body'->0、'parka'->1。それ以外は'wear'/'cloth'/'parka'/'outfit'/
    'costume'/'overalls'/'mohu'/'mofu'のいずれかを含むかどうかで判定する
    (着脱可能な衣装・装飾を示す語を含めば1=parka、含まなければ0=body)。
    toto実測ではbody/parkaの完全一致のみで全マテリアルが決着する(単純な
    1オブジェクト=1マテリアル構成)。alicia実測(12マテリアル)は'wear'を
    含む3件(body_wear/wear/hair_wear)が1、残り9件が0になる。'overalls'は
    U16 Shata実測で追加(既存キーワードに一致する語が皆無だと全三角形が
    material=0に倒れ、2セクションSKへの注入が「material=1の三角形が0件」で
    全滅する事故を確認したため)。'mohu'/'mofu'はFIX3a(2026-07-24)で追加:
    毛皮襟パーツ(heon/zizi/flatif等の"mohu"、pgftestの"0mofu")が従来
    material=0(body)へ強制併合され素肌メッシュと同一セクションで重なる
    (z-fighting/裂けの疑い、docs\\DIAG_TEARING_2026-07-24.md)ため、
    衣装側(material=1)へ回す試行。

    U50-single(2026-07-25、責任者裁定): **常に0を返す**(単一マテリアル化)。
    キーワード判定はSK側のスロット役(t00/t01)と一致して初めて正しく、
    実測で注入対象60SK中16SKが不一致だった(work\\u50_equip\\out\\FINDINGS2.txt
    5節)。1マテリアルへ畳めばこの不整合は起こりようがない(実測NG 0件)。
    `pipeline\\py\\vp_atlas.py`の`classify_material()`(同期必須)も同時に
    単一化してある。"""
    if SINGLE_MATERIAL:
        return 0
    name = orig_name.lower()
    if name == "body":
        return 0
    if name == "parka":
        return 1
    for kw in ("wear", "cloth", "parka", "outfit", "costume", "overalls",
               "mohu", "mofu"):
        if kw in name:
            return 1
    return 0


with open(avatar_meta_path, encoding="utf-8") as f:
    _avatar_meta = json.load(f)
slot_material_class = {
    slot: classify_material(info.get("orig_name", ""))
    for slot, info in _avatar_meta.get("slots", {}).items()
}
# U16: preflight G4の収録数整合のためavatar_meta.jsonの"slots"を2枠へ
# 絞り込んだ場合(trim_avatar_meta.py)でも、絞り落とされたスロットの
# orig_nameは"_all_slots_orig_name"に退避されているので、そちらを使って
# classify_material()し直す(絞り込み前と同じ分類結果を保つ。絞り込み後の
# "slots"だけを見ると情報が失われ、全三角形がmaterial=0に潰れる事故になる)
for slot, orig_name in _avatar_meta.get("_all_slots_orig_name", {}).items():
    if slot not in slot_material_class:
        slot_material_class[slot] = classify_material(orig_name or "")
print(f"[dump_avatar_mesh] slot_material_class={slot_material_class}")

bpy.ops.wm.open_mainfile(filepath=blend_path)

if "HairSway" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["HairSway"], do_unlink=True)

deps = bpy.context.evaluated_depsgraph_get()

mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
if not mesh_objs:
    raise RuntimeError(f"MESHオブジェクトが見つからない: {blend_path}")

vert_key_to_index = {}
vertices = []  # 分割後の頂点(dict)
triangles = []  # [i0,i1,i2] グローバル索引

total_src_verts = 0
total_src_tris = 0

total_material_tri_counts = {0: 0, 1: 0}

for obj in sorted(mesh_objs, key=lambda o: o.name):
    obj_slot_names = [ms.material.name if ms.material else None for ms in obj.material_slots]
    unknown_slots = {s for s in obj_slot_names if s is not None and s not in slot_material_class}
    if unknown_slots:
        # U16実測(Heon等、body/parka以外の3件目以降のマテリアルスロットを持つ
        # kemono系アバター): pak側は解剖学的にbody/parka2スロットしか持たないため
        # (resolve_textures()と同じ理由)、G4整合のためavatar_meta.jsonのslots
        # から2スロットへ絞り込んでいる場合がある。絞り込まれたスロットの
        # 三角形はclassify_material()の既定(0=body)へ倒して警告するに留める
        # (幾何欠落より軽微、ライセンス非関連の技術判断のため0節聖域条項の対象外)
        print(f"[dump_avatar_mesh][WARN] {obj.name}: avatar_meta.jsonに無いマテリアル"
              f"スロット(既定でmaterial=0扱い): {unknown_slots}")
        for s in unknown_slots:
            slot_material_class[s] = 0
    vg_names = {vg.index: vg.name for vg in obj.vertex_groups}
    weights_by_vertex = []
    for v in obj.data.vertices:
        pairs = sorted(
            ((vg_names.get(g.group, "?"), g.weight) for g in v.groups if g.weight > 0),
            key=lambda p: -p[1])[:max_influences]
        total = sum(w for _, w in pairs)
        if total <= 0:
            weights_by_vertex.append(None)
            continue
        norm = [[n, w / total] for n, w in pairs]
        diff = 1.0 - sum(w for _, w in norm)
        norm[0][1] += diff
        weights_by_vertex.append(norm)
    total_src_verts += len(obj.data.vertices)

    eo = obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    if not mesh.uv_layers:
        eo.to_mesh_clear()
        raise RuntimeError(f"{obj.name}: UVレイヤーが無い")
    # calc_tangents()はn-gon(5角形以上)を含むメッシュでは動作しない
    # (Blender API制約: tris/quadsのみ)。Heon実測(jacketメッシュ)で発覚。
    # 既存メッシュ(toto等、既にtris/quadsのみ)への影響を避けるため、
    # n-gonのみを対象にin-place三角形分割する(tris/quadsはそのまま)
    ngon_faces = [f for f in mesh.polygons if len(f.vertices) > 4]
    if ngon_faces:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        ngon_bm_faces = [f for f in bm.faces if len(f.verts) > 4]
        bmesh.ops.triangulate(bm, faces=ngon_bm_faces,
                               quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        print(f"[dump_avatar_mesh] {obj.name}: n-gon {len(ngon_faces)}面を三角形分割")
    uvmap_name = mesh.uv_layers[0].name
    try:
        mesh.calc_tangents(uvmap=uvmap_name)
    except Exception as e:
        eo.to_mesh_clear()
        raise RuntimeError(f"{obj.name}: calc_tangents失敗: {e}")

    mesh.calc_loop_triangles()
    uv_layer = mesh.uv_layers[0].data
    mw = eo.matrix_world
    rot = mw.to_3x3().normalized()

    obj_tri_count = 0
    for lt in mesh.loop_triangles:
        tri_idx = []
        skip = False
        for li in lt.loops:
            loop = mesh.loops[li]
            vi = loop.vertex_index
            w = weights_by_vertex[vi]
            if w is None:
                skip = True
                break
            pos = (mw @ mesh.vertices[vi].co) * (0.01 * output_scale)  # cm相当の生値 -> m単位へ補正し、最終倍率を適用
            # v2.2.13 diagnostic backport only: reject corrupt coordinates at
            # their source. Do not clamp, delete, reorder, or otherwise mutate
            # vertices, indices, weights, tangents, or bone assignments.
            if not (math.isfinite(pos.x) and math.isfinite(pos.y)
                    and math.isfinite(pos.z)):
                top_bone = w[0][0] if w else "(no weights)"
                raise RuntimeError(
                    f"non-finite vertex position detected in {obj.name!r} "
                    f"vertex_index={vi}: pos=({pos.x}, {pos.y}, {pos.z}) "
                    f"top_weight_bone={top_bone!r}. Aborting before SK injection."
                )
            uv = uv_layer[li].uv
            n = (rot @ loop.normal).normalized()
            t = (rot @ loop.tangent).normalized()
            bsign = loop.bitangent_sign
            key = (obj.name, vi,
                   round(pos.x, ROUND), round(pos.y, ROUND), round(pos.z, ROUND),
                   round(uv.x, ROUND), round(uv.y, ROUND),
                   round(n.x, ROUND), round(n.y, ROUND), round(n.z, ROUND),
                   round(t.x, ROUND), round(t.y, ROUND), round(t.z, ROUND),
                   round(bsign, 2))
            gi = vert_key_to_index.get(key)
            if gi is None:
                gi = len(vertices)
                vert_key_to_index[key] = gi
                vertices.append({
                    "pos": [round(pos.x, ROUND), round(pos.y, ROUND), round(pos.z, ROUND)],
                    "normal": [round(n.x, ROUND), round(n.y, ROUND), round(n.z, ROUND)],
                    "tangent": [round(t.x, ROUND), round(t.y, ROUND), round(t.z, ROUND)],
                    "bitangent_sign": round(bsign, 2),
                    "uv": [round(uv.x, ROUND), round(uv.y, ROUND)],
                    "weights": w,
                })
            tri_idx.append(gi)
        eo_break = False
        if skip:
            continue
        if tri_idx[0] == tri_idx[1] or tri_idx[1] == tri_idx[2] or tri_idx[0] == tri_idx[2]:
            continue  # 縮退三角形は捨てる(位置・法線・UV全一致の完全重複ループのみ発生しうる)
        poly = mesh.polygons[lt.polygon_index]
        slot_name = obj_slot_names[poly.material_index] if poly.material_index < len(obj_slot_names) else None
        material = slot_material_class[slot_name] if slot_name is not None else 0
        tri_idx.append(material)
        triangles.append(tri_idx)
        total_material_tri_counts[material] += 1
        obj_tri_count += 1

    total_src_tris += obj_tri_count
    eo.to_mesh_clear()
    print(f"[dump_avatar_mesh] {obj.name}: src_verts={len(obj.data.vertices)} "
          f"tris={obj_tri_count} (running total split_verts={len(vertices)})")

out = {
    "format": 2,
    "gender": gender,
    "source_blend": blend_path,
    "output_scale": output_scale,
    "max_influences": max_influences,
    "num_vertices": len(vertices),
    "num_triangles": len(triangles),
    "material_slot_map": slot_material_class,
    "material_triangle_counts": {str(k): v for k, v in total_material_tri_counts.items()},
    "vertices": vertices,
    "triangles": triangles,
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f)

print(f"[dump_avatar_mesh] DONE src_objects={len(mesh_objs)} src_total_verts={total_src_verts} "
      f"split_vertices={len(vertices)} triangles={len(triangles)} "
      f"material_triangle_counts={total_material_tri_counts} -> {out_path}")
