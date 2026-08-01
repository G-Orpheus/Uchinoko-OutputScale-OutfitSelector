# -*- coding: utf-8 -*-
r"""公開issue #18: Armatureモディファイア無効フラグの入口正規化のユニット確認。

背景: 制作者が編集中に表示を切ったまま保存したファイルで、step02の
bake_pose_into_meshes の modifier_apply がBlender自身の
`RuntimeError: モディファイアーはOFFです` で変換停止していた。
修正は「エラーにせず入口(step01)+適用直前(step02)で強制ONに正規化して進む」。

vp_modnorm はbpy非依存(ダックタイピング)なので、Blender外のこのテストで
直接検証できる。実変換は伴わない(モックのみ)。

    python -m pytest tests\coverage\selftest\test_armature_modifier_normalize.py -q
"""
import os
import sys

BLENDER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "pipeline", "blender")
if BLENDER_DIR not in sys.path:
    sys.path.insert(0, BLENDER_DIR)

import vp_modnorm  # noqa: E402


# ---------------------------------------------------------------------------
# bpyの代役: 属性だけ合わせた素のオブジェクト
# ---------------------------------------------------------------------------

class FakeModifier:
    def __init__(self, name, mtype, show_viewport=True, show_render=True):
        self.name = name
        self.type = mtype
        self.show_viewport = show_viewport
        self.show_render = show_render


class FakeMesh:
    def __init__(self, name, modifiers=(), parent_type="OBJECT"):
        self.name = name
        self.modifiers = list(modifiers)
        self.parent_type = parent_type  # 真の非スキンメッシュ=ボーン親も無い


def fake_modifier_apply(mod):
    """Blenderの modifier_apply の停止条件を再現するモック。
    show_viewport=False のモディファイアを適用しようとすると、実際の
    Blender(日本語UI)と同じ RuntimeError で停止する。"""
    if not mod.show_viewport:
        raise RuntimeError("モディファイアーはOFFです")
    return True


# ---------------------------------------------------------------------------
# 正: 無効フラグのArmatureモディファイアが強制ONへ正規化される
# ---------------------------------------------------------------------------

def test_disabled_armature_modifier_is_forced_on():
    mesh = FakeMesh("geo_00", [FakeModifier("Armature", "ARMATURE",
                                            show_viewport=False,
                                            show_render=False)])
    logs = []
    result = vp_modnorm.normalize_armature_modifiers(
        [mesh], tag="test", log=logs.append)
    mod = mesh.modifiers[0]
    assert mod.show_viewport is True
    assert mod.show_render is True
    assert result == [("geo_00", "Armature", ("show_viewport", "show_render"))]
    # 英語の正規化ログが出ること(停止ではなくログで通過する仕様)
    assert len(logs) == 1
    assert "forced ON" in logs[0]
    assert "geo_00" in logs[0] and "Armature" in logs[0]


def test_viewport_only_disabled_is_forced_on():
    mesh = FakeMesh("geo_01", [FakeModifier("Armature", "ARMATURE",
                                            show_viewport=False,
                                            show_render=True)])
    result = vp_modnorm.normalize_armature_modifiers([mesh], log=lambda s: None)
    assert mesh.modifiers[0].show_viewport is True
    assert mesh.modifiers[0].show_render is True
    assert result == [("geo_01", "Armature", ("show_viewport",))]


# ---------------------------------------------------------------------------
# 負の対照: 触ってはいけないものに触らない
# ---------------------------------------------------------------------------

def test_negative_true_unskinned_mesh_untouched():
    """真の非スキンメッシュ(モディファイア無し・ボーン親無し)は対象外。"""
    mesh = FakeMesh("geo_02", modifiers=[], parent_type="OBJECT")
    logs = []
    result = vp_modnorm.normalize_armature_modifiers(
        [mesh], log=logs.append)
    assert result == []
    assert logs == []
    assert mesh.modifiers == []  # 追加も削除もされない


def test_negative_non_armature_modifier_untouched():
    """ARMATURE以外のモディファイアは無効のまま維持(勝手にONにしない)。"""
    sub = FakeModifier("Subdivision", "SUBSURF", show_viewport=False)
    mesh = FakeMesh("geo_03", [sub])
    result = vp_modnorm.normalize_armature_modifiers([mesh], log=lambda s: None)
    assert result == []
    assert sub.show_viewport is False


def test_negative_already_enabled_not_reported():
    """全フラグONのモディファイアはログにも結果にも出ない(ノイズを増やさない)。"""
    mesh = FakeMesh("geo_04", [FakeModifier("Armature", "ARMATURE")])
    logs = []
    result = vp_modnorm.normalize_armature_modifiers([mesh], log=logs.append)
    assert result == []
    assert logs == []


# ---------------------------------------------------------------------------
# 修正前は停止 → 修正後は通過(チェック関数単体での赤→緑)
# ---------------------------------------------------------------------------

def test_apply_stops_without_fix_and_passes_with_fix():
    import pytest
    mesh = FakeMesh("geo_05", [FakeModifier("Armature", "ARMATURE",
                                            show_viewport=False)])
    # 修正前の挙動: 無効フラグのままapplyするとBlender相当のエラーで停止
    with pytest.raises(RuntimeError, match="OFF"):
        fake_modifier_apply(mesh.modifiers[0])
    # 修正後: 正規化してからapplyすれば通過し、正規化ログが残る
    logs = []
    vp_modnorm.normalize_armature_modifiers([mesh], log=logs.append)
    assert fake_modifier_apply(mesh.modifiers[0]) is True
    assert len(logs) == 1 and "forced ON" in logs[0]


def test_mixed_scene_only_armature_targets_normalized():
    """混在シーン: スキン済み(無効Armature)+真の非スキン+無効SUBSURF。
    正規化されるのはArmatureモディファイアだけ。"""
    skinned = FakeMesh("geo_10", [FakeModifier("Armature", "ARMATURE",
                                               show_viewport=False)])
    unskinned = FakeMesh("geo_11", modifiers=[])
    other = FakeMesh("geo_12", [FakeModifier("Decimate", "DECIMATE",
                                             show_viewport=False)])
    result = vp_modnorm.normalize_armature_modifiers(
        [skinned, unskinned, other], log=lambda s: None)
    assert [r[0] for r in result] == ["geo_10"]
    assert skinned.modifiers[0].show_viewport is True
    assert other.modifiers[0].show_viewport is False
