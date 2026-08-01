# -*- coding: utf-8 -*-
r"""カバレッジ軸: **UE非依存**。

README の売り文句は「Unreal Engine 5.1 は**不要です**。GUI は常に UE 不要の
経路で変換します」。これを 3 段で確かめる:

  1. 出力の来歴  … UE 経路でしか生まれないファイルが build\ に無い(gate D の再利用)
  2. 実行の痕跡  … 変換ログに UnrealPak / UnrealEditor-Cmd / RunUAT / BuildCookRun /
                    -run=pythonscript が1回も現れない
  3. 入力の依存  … job.json から `paths.ue_root` / `paths.ue_project` を
                    **丸ごと落として**も変換が成立する
                    (= UE がインストールされていない利用者の状況)

3 がいちばん強い。1・2 は「たまたま UE を呼ばなかった」も通してしまうが、
3 は「UE のパスが無いと動かない」設計だったら必ず落ちる。
"""
import os

import pytest

import matrix
import probes


@pytest.mark.slow
def test_ue_independent_conversion(build, allow_convert, gate, recorder):
    case = "ue_free"
    res = build(case, matrix.FLIP_BASE, overrides=None,
                allow_convert=allow_convert, drop_ue_paths=True)

    import gates as shipcheck_gates

    # 入力の依存: ue_root / ue_project が job.json に無いことを先に確認する
    # (make_job の drop_ue_paths が効いていなければ、この検査は無意味になる)
    paths = res.job_dict.get("paths", {})
    leaked = [k for k in ("ue_root", "ue_project") if k in paths]
    gate(probes._gate("PASS" if not leaked else "FAIL", "job_has_no_ue_paths",
                      leaked=leaked, paths=sorted(paths)),
         case=case, axis="UE非依存")

    gate(shipcheck_gates.gate_a_convert_exit0(res), case=case, axis="UE非依存")
    gate(shipcheck_gates.gate_b_pak_exists(res), case=case, axis="UE非依存")
    gate(probes.gate_preflight("C_preflight", res.log_text), case=case,
         axis="UE非依存")
    gate(shipcheck_gates.gate_d_noue_provenance(res.build_dir), case=case,
         axis="UE非依存")
    gate(probes.gate_engine_mode_is_noue("engine_mode_is_noue", res.log_text),
         case=case, axis="UE非依存")
    gate(probes.gate_no_ue_tool_in_log("no_ue_tool_invocation", res.log_text),
         case=case, axis="UE非依存")


def test_ue_detector_actually_detects(gate):
    r"""**検出器そのものの負の対照**(実変換不要)。

    `gate_no_ue_tool_in_log` が「何も検出しない検出器」に退化していたら、
    UE 非依存の実証は無意味になる。そこで **UE を確実に使う本物のテキスト**
    (`convert.ps1` の UE 分岐)を食わせて、必ず FAIL することを確かめる。

    これが PASS してしまったら検出器が壊れている。
    """
    p = os.path.join(matrix.REPO_ROOT, "pipeline", "cli", "convert.ps1")
    if not os.path.isfile(p):
        pytest.skip("convert.ps1 が無い: {}".format(p))
    with open(p, encoding="utf-8", errors="replace") as f:
        src = f.read()
    res = probes.gate_no_ue_tool_in_log("_detector_selfcheck", src)
    detected = [f["pattern"] for f in res.detail.get("found", [])]
    out = probes._gate(
        "PASS" if res.status == "FAIL" and len(detected) >= 3 else "FAIL",
        "ue_detector_is_not_a_noop",
        detected_patterns=detected,
        note="convert.ps1(UE分岐を含む)に対して検出器が反応することの確認")
    gate(out, case="detector", axis="UE非依存")
