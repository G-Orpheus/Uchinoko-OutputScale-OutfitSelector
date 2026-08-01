# -*- coding: utf-8 -*-
"""Armatureモディファイアの有効フラグ正規化(公開issue #18)。

アバター制作者が編集中にArmatureモディファイアの表示(show_viewport等)を
切ったまま保存したファイルは、step02の bake_pose_into_meshes で
bpy.ops.object.modifier_apply がBlender自身のエラー
(日本語UIで `RuntimeError: モディファイアーはOFFです`)を出して変換が停止する。

設計判断(2026-07-28確定): このフラグは制作者の編集時表示の名残にすぎず、
束縛の実体は「モディファイアの存在」と「頂点グループ」。したがって
エラーにせず**入口で強制ONに正規化して進む**。ユーザーにBlenderで
直させる方向の対応は禁止。

このモジュールは意図的にbpy非依存(ダックタイピング)にしてあり、
Blender外のユニットテスト(tests/coverage/selftest)から直接検証できる。
対象は `type == "ARMATURE"` のモディファイアのみ。モディファイアを
持たないメッシュ(真の非スキンメッシュ等)には一切触れない。
"""

# 正規化対象の有効フラグ。modifier_applyが直接見るのはビューポート評価だが、
# レンダリング側も残すと「見た目検査(render)と変換結果が食い違う」ので両方ONにする。
_ENABLE_FLAGS = ("show_viewport", "show_render")


def normalize_armature_modifiers(mesh_objs, tag="vp_modnorm", log=print):
    """Armatureモディファイアの無効フラグを強制ONへ正規化する。

    mesh_objs: `.name` と `.modifiers`(各要素が `.type` `.name` と
        _ENABLE_FLAGS 属性を持つ)を備えたオブジェクトの列。bpyのObjectで
        そのまま動くが、bpyには依存しない。
    tag: ログ行の先頭タグ([step01] 等)。
    log: ログ出力関数(既定print。テストでは記録用に差し替え可)。

    返り値: 正規化した (mesh名, modifier名, 無効だったフラグ名タプル) のリスト。
    もともと全フラグONのモディファイア・ARMATURE以外のモディファイアは
    触らず、リストにも載せない。
    """
    normalized = []
    for obj in mesh_objs:
        for mod in getattr(obj, "modifiers", ()):
            if mod.type != "ARMATURE":
                continue
            disabled = tuple(f for f in _ENABLE_FLAGS
                             if not getattr(mod, f, True))
            if not disabled:
                continue
            for f in disabled:
                setattr(mod, f, True)
            normalized.append((obj.name, mod.name, disabled))
            # 英語ログ(配布版ログから診断できるよう成功時にも構造を残す)
            log(f"[{tag}] normalized: armature modifier '{mod.name}' on mesh "
                f"'{obj.name}' was disabled ({', '.join(disabled)}=False) "
                f"-> forced ON and continuing (author-time display leftover; "
                f"binding is defined by the modifier + vertex groups)")
    return normalized
