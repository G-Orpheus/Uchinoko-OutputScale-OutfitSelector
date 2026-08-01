import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "py"))

import vp_atlas
import vp_tex


def test_dxt1_keeps_binary_alpha_for_masked_materials():
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[:, :, :3] = (220, 120, 40)
    rgba[:, :, 3] = 255
    rgba[:, :2, 3] = 0
    decoded = vp_tex.decode_dxt(vp_tex.encode_dxt1(rgba), 4, 4, "PF_DXT1")
    assert np.all(decoded[:, :2, 3] == 0)
    assert np.all(decoded[:, 2:, 3] == 255)


def test_dxt1_opaque_input_stays_opaque():
    rgba = np.full((8, 8, 4), 255, dtype=np.uint8)
    rgba[:, :, :3] = (10, 80, 200)
    decoded = vp_tex.decode_dxt(vp_tex.encode_dxt1(rgba), 8, 8, "PF_DXT1")
    assert np.all(decoded[:, :, 3] == 255)


def test_atlas_copies_rgba_including_alpha():
    opaque = np.full((4, 4, 4), 255, dtype=np.uint8)
    transparent = opaque.copy()
    transparent[:, :, 3] = 0
    canvas, rows, cols, cell = vp_atlas.build_atlas_image(
        [opaque, transparent], cell_size=4, max_canvas=16)
    assert (rows, cols, cell) == (1, 2, 4)
    assert np.all(canvas[:, :4, 3] == 255)
    assert np.all(canvas[:, 4:, 3] == 0)


def test_alpha_stats_report_transparent_and_partial_pixels():
    rgba = np.zeros((1, 3, 4), dtype=np.uint8)
    rgba[0, :, 3] = (0, 127, 255)
    stats = vp_tex.alpha_stats(rgba)
    assert stats == {
        "min": 0, "max": 255, "transparent": 1, "partial": 1,
        "below_128": 2, "pixels": 3,
    }
