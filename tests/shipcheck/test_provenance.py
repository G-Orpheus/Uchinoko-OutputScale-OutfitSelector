# -*- coding: utf-8 -*-
r"""wp_provenance(wp_stub検証官F-1/F-2対応): build_provenance.py の負の対照テストと
release.py 出自台帳ゲートの接続テスト。

負の対照(検証官がF-1で使った3種+SK系1種。全て検出=FAILになること):
  ①バニラ抽出テクスチャ(T_PalHair001_C.uexp)を noue_master に置く
  ②バニラbind pose生値JSON(vanilla_refskel_male.json)を noue_master に置く
  ③Palworldチャンクbin(Pal-Windows_chunk.bin)を noue_master に置く
  ④SK系スタブ命名(SK_*.uasset)→ palworld_derived 検出
正の対照:
  attestation全件が実ファイルとSHA256一致し、宣言どおり分類されること
  repo_inputs全体が --strict --require-zero-palworld でPASSすること
関所接続(F-2):
  release.run_zip_content_gates が provenance ゲートを含み、
  出自違反zipで all_green が偽になる(=リリースが止まりzipが破棄される)こと

実行: python -m pytest tests\shipcheck\test_provenance.py -v
"""
import hashlib
import json
import os
import subprocess
import sys
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEVTOOLS = os.path.join(REPO, "devtools")
BUILD_PROVENANCE = os.path.join(DEVTOOLS, "build_provenance.py")

if DEVTOOLS not in sys.path:
    sys.path.insert(0, DEVTOOLS)
import build_provenance as bp  # noqa: E402

STAGE = "Uchinoko_for_Palworld"   # v2.0.0改名(配布zipルートフォルダ名)

# 検証官(work\wp_stub\VERIFY.md F-1)の負の対照。旧分類器は全てfirst_party(誤)だった
NEGATIVE_CONTROLS = [
    ("pipeline/py/noue_master/pak_extract_extra/Player/Hair/Hair001/"
     "T_PalHair001_C.uexp", b"\x00fake-vanilla-texture-bytes\x00" * 8),
    ("pipeline/py/noue_master/vanilla_refskel_male.json",
     b'{"bones": [[0.1, 0.2, 0.3]]}'),
    ("pipeline/py/noue_master/Pal-Windows_chunk.bin",
     b"\xc1\x83*\x9e fake pak chunk bytes" * 4),
]


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _attestation():
    return bp.load_attestation()


def _run_script(args):
    proc = subprocess.run(
        [sys.executable, BUILD_PROVENANCE] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout + proc.stderr


# --- 負の対照(classify単体) -------------------------------------------------

@pytest.mark.parametrize("rel,data", NEGATIVE_CONTROLS,
                         ids=["vanilla_texture", "refskel_json", "chunk_bin"])
def test_negative_controls_not_permitted(rel, data):
    """F-1の負の対照3種: first_party/third_partyに分類されてはならない。"""
    cls, lic, note = bp.classify(rel, sha256=_sha256(data),
                                 attestation=_attestation())
    assert cls not in ("first_party", "third_party"), (rel, cls, note)


def test_negative_control_sk_stub_detected():
    """SK系命名はattestationにあっても検出ルール(FAIL側)が勝つ。"""
    cls, _, _ = bp.classify(
        "pipeline/py/noue_master/pak_extract_extra/Player/Hair/Hair001/"
        "SK_Player_Hair001.uasset", sha256="0" * 64, attestation=_attestation())
    assert cls == "palworld_derived"


def test_pipeline_vanilla_json_not_first_party():
    """検証官の追加対照: pipeline/py/vanilla/refskel_male.json も自作扱いにしない。"""
    cls, _, _ = bp.classify("pipeline/py/vanilla/refskel_male.json",
                            sha256="0" * 64, attestation=_attestation())
    assert cls == "unclassified"


# --- 負の対照(スクリプト一気通貫: stage-dirへ実際に置いて検出されること) -----

def test_negative_controls_fail_strict_gate(tmp_path):
    stage = tmp_path / "stage"
    for rel, data in NEGATIVE_CONTROLS:
        p = stage / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    out = tmp_path / "ledger.json"
    rc, log = _run_script(["--stage-dir", str(stage), "--strict",
                           "--out", str(out)])
    assert rc == 1, log
    ledger = json.loads(out.read_text(encoding="utf-8"))
    assert ledger["summary"]["unclassified"] == len(NEGATIVE_CONTROLS)
    assert ledger["summary"]["first_party"] == 0
    for fe in ledger["files"]:
        assert fe["class"] == "unclassified", fe


# --- 正の対照(attestation) ---------------------------------------------------

def test_attestation_all_entries_hash_match_and_classify():
    """attestation全件: 実ファイルが存在しSHA256一致、宣言どおりに分類される。"""
    att = _attestation()
    assert len(att) > 0
    for rel, ent in att.items():
        full = os.path.join(REPO, *rel.split("/"))
        assert os.path.isfile(full), f"attestation対象が無い: {rel}"
        h = hashlib.sha256()
        with open(full, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        assert h.hexdigest() == ent["sha256"], f"SHA256不一致: {rel}"
        cls, lic, _ = bp.classify(rel, sha256=ent["sha256"], attestation=att)
        assert cls == ent["class"], (rel, cls)


def test_attestation_hash_mismatch_is_unclassified():
    """attestationにパスがあってもハッシュが違えばfail-closed。"""
    att = _attestation()
    rel = next(iter(att))
    cls, _, note = bp.classify(rel, sha256="f" * 64, attestation=att)
    assert cls == "unclassified"
    assert "SHA256不一致" in note


def test_missing_attestation_file_fails_closed(tmp_path):
    rc, log = _run_script(["--stage-dir", str(tmp_path),
                           "--attestation", str(tmp_path / "no_such.json"),
                           "--out", str(tmp_path / "o.json")])
    assert rc == 1
    assert "attestation" in log


# --- 正の対照(repo_inputs全体、third_party実態一致) --------------------------

def test_repo_inputs_pass_and_third_party_matches_reality(tmp_path):
    out = tmp_path / "ledger.json"
    rc, log = _run_script(["--strict", "--require-zero-palworld",
                           "--out", str(out)])
    assert rc == 0, log
    ledger = json.loads(out.read_text(encoding="utf-8"))
    assert ledger["summary"]["palworld_derived"] == 0
    assert ledger["summary"]["unclassified"] == 0
    # third_party件数 = リポジトリthird_party\配下の実ファイル数(実態と一致)
    actual = 0
    for dirpath, dirnames, fns in os.walk(os.path.join(REPO, "third_party")):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        actual += len(fns)
    assert actual > 0
    assert ledger["summary"]["third_party"] == actual
    # GPL同梱物(pyooz対応ソース)が third_party として計上されている
    tp = [f for f in ledger["files"] if f["class"] == "third_party"]
    assert any(f["license"] == "GPL-3.0-or-later" for f in tp), tp


# --- 関所接続(F-2): release.py の provenance ゲート --------------------------

def _import_release():
    import importlib
    return importlib.import_module("release")


def _make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return str(path)


def _clean_entries():
    src_rel = "pipeline/py/vp_core.py"
    with open(os.path.join(REPO, *src_rel.split("/")), "rb") as f:
        sample = f.read()
    return [
        (STAGE + "/README.md", b"readme"),
        (STAGE + "/_internal/LICENSE", b"license"),
        (STAGE + "/_internal/" + src_rel, sample),
    ]


def test_release_gate_green_on_clean_zip(tmp_path):
    release = _import_release()
    zp = _make_zip(tmp_path / "clean.zip", _clean_entries())
    report = release.Report(str(tmp_path / "report.md"))
    g = release.run_provenance_gate(zp, str(tmp_path), report)
    assert g["name"] == "provenance"
    assert g["ok"], g


def test_release_gate_blocks_on_provenance_fail(tmp_path, monkeypatch):
    """出自違反(attestation外のバイナリ混入)zipでは、provenanceゲートが赤になり
    run_zip_content_gates 全体が all_green=False(=release.pyの_fail経路で
    zipが破棄され、リリースは止まる)。他のzipゲートはモックで緑に固定し、
    失敗がprovenanceゲート単独に帰着することを示す。"""
    release = _import_release()
    entries = _clean_entries() + [
        (STAGE + "/_internal/pipeline/py/noue_master/Pal-Windows_chunk.bin",
         b"\xc1\x83*\x9e fake pak chunk" * 4),
    ]
    zp = _make_zip(tmp_path / "dirty.zip", entries)
    monkeypatch.setattr(release, "run_u28_zip_audit",
                        lambda *a, **k: {"name": "u28_zip_audit", "ok": True, "rc": 0})
    monkeypatch.setattr(release, "run_dist_smoke",
                        lambda *a, **k: {"name": "dist_smoke", "ok": True, "rc": 0})
    monkeypatch.setattr(release, "run_dll_closure_check",
                        lambda *a, **k: {"name": "dll_closure_check", "ok": True, "rc": 0})
    report = release.Report(str(tmp_path / "report.md"))
    results = release.run_zip_content_gates(zp, str(tmp_path), report)
    names = [g["name"] for g in results]
    assert "provenance" in names
    prov = next(g for g in results if g["name"] == "provenance")
    assert not prov["ok"]
    assert not release.all_green(results)
    ledger = json.loads(
        (tmp_path / "provenance.json").read_text(encoding="utf-8"))
    assert ledger["summary"]["unclassified"] >= 1
