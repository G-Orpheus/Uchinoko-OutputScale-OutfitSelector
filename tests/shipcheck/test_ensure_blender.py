# -*- coding: utf-8 -*-
"""単体テスト: pipeline\\cli\\ensure_blender.ps1(u54 Blender同梱廃止)。

配布zipからBlender本体を外し、初回起動時に公式サイトから取得する方式に
変えた(work\\u54_unbundle\\wpA\\INSTRUCTIONS.md 4.1)。このテストは実ネットワーク
には出ず、4.7で実DL検証済みのキャッシュzip(work\\u54_unbundle\\cache\\
blender-4.3.2-windows-x64.zip)を -SourceZip で指定して確認する
(無効URLを注入する負の対照だけは例外的に実ネットワークへ出て404を踏む)。

pytestからも `python tests/shipcheck/test_ensure_blender.py` からも実行できる
(tests\\shipcheck\\test_palworld_locate.py と同じ構成)。

前提(無ければ各テストはSKIPして緑にはしない=無言スキップにはしない。ただし
テストコレクション自体は落とさない): キャッシュzip・ooz.pyd・python3.dllが
開発機に実在すること(いずれもmake_dist.ps1が使うのと同じ解決パス)。

WP-A2(2026-07-28)ホットフィックス: クリーンWindows Sandbox実機(v1.1.3)で
ensure_blender.ps1がParserError多発で死亡する事故が起きた。真因は
ensure_blender.ps1だけがBOM無しUTF-8で保存されており、実行系の
Windows PowerShell 5.1(powershell.exe)がBOM無しをANSI(CP932)扱いする
ため日本語コメント/文字列で構文が崩壊すること。開発機のこのテストは
`pwsh` で起動していたため検出できなかった(pwshはBOM無しでもUTF-8として
読むため無症状)。以後 `_run()` の既定シェルを実機と同じ`powershell.exe`に
変更し、加えてPS5.1のパーサで直接構文解析する再発防止テストを追加した
(test_ps51_parses_clean / test_ps51_parse_negative_control_no_bom_fails)。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
ENSURE_BLENDER_PS1 = os.path.join(REPO_ROOT, "pipeline", "cli", "ensure_blender.ps1")
CACHED_ZIP = os.path.join(REPO_ROOT, "work", "u54_unbundle", "cache", "blender-4.3.2-windows-x64.zip")

# make_dist.ps1と同じ解決先(開発機のpyooz/python3.dll実体、build\make_dist.ps1参照)。
OOZ_SITE_PKG_SRC = os.path.join(os.environ.get("APPDATA", ""), "Python", "Python313", "site-packages")
PYTHON311_DLL = os.environ.get("D2P_PYTHON311_DLL") or os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python3.dll")


def _skip_reason_if_prereqs_missing():
    if not os.path.isfile(ENSURE_BLENDER_PS1):
        return "ensure_blender.ps1が無い: {}".format(ENSURE_BLENDER_PS1)
    if not os.path.isfile(CACHED_ZIP):
        return ("キャッシュ済みBlender zipが無い(4.7の実DL検証で作成される想定): {}"
                 .format(CACHED_ZIP))
    if not os.path.isfile(os.path.join(OOZ_SITE_PKG_SRC, "ooz.pyd")):
        return "ooz.pydが無い(pip install pyoozが必要): {}".format(OOZ_SITE_PKG_SRC)
    if not os.path.isfile(PYTHON311_DLL):
        return "python3.dll(Python 3.11)が無い: {}".format(PYTHON311_DLL)
    return None


def _make_app_root(tmp, with_patch_materials=True):
    """AppRoot直下にassets\\blender_patch\\(差し込み素材)を用意する。"""
    app_root = os.path.join(tmp, "AppRoot")
    if not with_patch_materials:
        os.makedirs(app_root, exist_ok=True)
        return app_root
    patch_dir = os.path.join(app_root, "assets", "blender_patch")
    os.makedirs(patch_dir, exist_ok=True)
    shutil.copy(os.path.join(OOZ_SITE_PKG_SRC, "ooz.pyd"), patch_dir)
    for name in os.listdir(OOZ_SITE_PKG_SRC):
        low = name.lower()
        if low.startswith("pyooz-") and low.endswith(".dist-info"):
            shutil.copytree(os.path.join(OOZ_SITE_PKG_SRC, name), os.path.join(patch_dir, name))
    shutil.copy(PYTHON311_DLL, os.path.join(patch_dir, "python3.dll"))
    return app_root


# WP-A2: 実機(クリーンWindows)にpwshは無い。既定を実機と同じpowershell.exe
# (Windows PowerShell 5.1)にする。D2P_TEST_PS_SHELLで上書き可能(pwshも併用したい
# 場合のため残す。ただし規定値をpwshに戻すと今回の事故を再び見逃す)。
PS_SHELL = os.environ.get("D2P_TEST_PS_SHELL", "powershell.exe")


def _run(app_root, extra_args, timeout=300):
    args = [PS_SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ENSURE_BLENDER_PS1,
            "-AppRoot", app_root] + extra_args
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_normal_path_with_cached_sourcezip():
    """SourceZip正常系(キャッシュzip使用)。blender.exe実在+マーカー有効+
    差し込み(ooz.pyd/python3.dll/VCランタイム)まで確認する。冪等性(2回目は
    ダウンロード/展開なしで即PASS)も併せて確認する。"""
    skip = _skip_reason_if_prereqs_missing()
    if skip:
        print("SKIP: test_normal_path_with_cached_sourcezip: {}".format(skip))
        return
    tmp = tempfile.mkdtemp(prefix="d2p_ensure_blender_")
    try:
        app_root = _make_app_root(tmp)
        rc, out = _run(app_root, ["-SourceZip", CACHED_ZIP])
        assert rc == 0, "rc={}\n{}".format(rc, out[-3000:])
        target = os.path.join(app_root, "assets", "tools", "blender-4.3.2-windows-x64")
        assert os.path.isfile(os.path.join(target, "blender.exe"))
        marker_path = os.path.join(target, ".d2p_patched.json")
        assert os.path.isfile(marker_path)
        with open(marker_path, "r", encoding="utf-8") as f:
            marker = json.load(f)
        assert marker["patched"] is True
        assert marker["version"] == "4.3.2"
        site_packages = os.path.join(target, "4.3", "python", "lib", "site-packages")
        py_bin = os.path.join(target, "4.3", "python", "bin")
        assert os.path.isfile(os.path.join(site_packages, "ooz.pyd"))
        assert os.path.isfile(os.path.join(py_bin, "python3.dll"))
        assert os.path.isfile(os.path.join(py_bin, "vcruntime140.dll"))
        assert os.path.isfile(os.path.join(site_packages, "vcruntime140.dll"))
        # 一時作業ディレクトリが残っていないこと(アトミック移動の後始末確認)
        leftovers = [n for n in os.listdir(os.path.join(app_root, "assets", "tools"))
                     if n.startswith(".tmp_ensure_blender_")]
        assert not leftovers, "一時ディレクトリが残っている: {}".format(leftovers)

        # 冪等性: 2回目はダウンロード/展開なしで即PASSすること
        rc2, out2 = _run(app_root, [])
        assert rc2 == 0
        assert ("準備済み" in out2) or ("既に使用可能" in out2), out2[-1000:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_negative_sha256_mismatch_fails_closed():
    """負の対照(4.6b相当): SourceZipを1バイト改竄すると、SHA不一致でfail-closed
    すること(最終位置にディレクトリを残さないことも確認)。"""
    skip = _skip_reason_if_prereqs_missing()
    if skip:
        print("SKIP: test_negative_sha256_mismatch_fails_closed: {}".format(skip))
        return
    tmp = tempfile.mkdtemp(prefix="d2p_ensure_blender_")
    try:
        app_root = _make_app_root(tmp)
        corrupt_zip = os.path.join(tmp, "corrupt.zip")
        shutil.copy(CACHED_ZIP, corrupt_zip)
        with open(corrupt_zip, "r+b") as f:
            f.seek(1000)
            b = f.read(1)
            f.seek(1000)
            f.write(bytes([(b[0] + 1) % 256]))
        rc, out = _run(app_root, ["-SourceZip", corrupt_zip])
        assert rc != 0, "改竄zipなのに成功してしまった:\n{}".format(out[-2000:])
        assert "[D2P_BLENDER_SETUP_FAIL]" in out
        assert "SHA256" in out
        target = os.path.join(app_root, "assets", "tools", "blender-4.3.2-windows-x64")
        assert not os.path.isdir(target), "失敗したのに最終位置にディレクトリが残っている(fail-closed違反)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_negative_invalid_url_fails_closed_with_marker():
    """負の対照(4.6a相当): SourceZip省略+無効URL注入では、実ネットワーク越しに
    失敗し[D2P_BLENDER_SETUP_FAIL]マーカー付きで案内が出て非0終了すること。"""
    skip = _skip_reason_if_prereqs_missing()
    if skip:
        print("SKIP: test_negative_invalid_url_fails_closed_with_marker: {}".format(skip))
        return
    tmp = tempfile.mkdtemp(prefix="d2p_ensure_blender_")
    try:
        app_root = _make_app_root(tmp)
        rc, out = _run(app_root, [
            "-DownloadUrlOverride",
            "https://download.blender.org/release/Blender4.3/does-not-exist-12345.zip",
        ])
        assert rc != 0
        assert "[D2P_BLENDER_SETUP_FAIL]" in out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_negative_missing_patch_materials_fails_closed():
    """負の対照: assets\\blender_patch\\が無い(配布物が壊れている想定)場合、
    展開までは進んでも差し込みの段で検知してfail-closedすること
    (「展開はできたので成功扱い」のような無言の格下げをしないことの確認)。"""
    if not os.path.isfile(ENSURE_BLENDER_PS1) or not os.path.isfile(CACHED_ZIP):
        print("SKIP: test_negative_missing_patch_materials_fails_closed: 前提ファイル無し")
        return
    tmp = tempfile.mkdtemp(prefix="d2p_ensure_blender_")
    try:
        app_root = _make_app_root(tmp, with_patch_materials=False)
        rc, out = _run(app_root, ["-SourceZip", CACHED_ZIP])
        assert rc != 0
        assert "[D2P_BLENDER_SETUP_FAIL]" in out
        assert "差し込み素材" in out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _ps51_parse_error_count(path):
    """指定ps1をWindows PowerShell 5.1(powershell.exe)のパーサで直接構文解析し、
    構文エラー件数と、エラーメッセージ結合文字列を返す(実行は一切しない)。
    実ネットワーク・実ファイルI/Oを一切要求しないため前提スキップは無い
    (powershell.exeが無い環境=そもそも配布対象外のためSKIPはこの1点のみ許容)。
    """
    ps_script = (
        "$tokens = $null; $parseErrors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile('{}', [ref]$tokens, [ref]$parseErrors) "
        "| Out-Null; "
        "Write-Output ('COUNT=' + $parseErrors.Count); "
        "$parseErrors | ForEach-Object {{ Write-Output $_.Message }}"
    ).format(path.replace("'", "''"))
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    count = None
    for line in out.splitlines():
        if line.startswith("COUNT="):
            count = int(line[len("COUNT="):].strip())
            break
    return count, out


def test_ps51_parses_clean():
    """再発防止(WP-A2): ensure_blender.ps1はWindows PowerShell 5.1のパーサで
    構文エラー0件であること(BOM欠落・PS7専用構文混入の再発を機械的に守る)。"""
    if shutil.which("powershell.exe") is None:
        print("SKIP: test_ps51_parses_clean: powershell.exeが無い環境")
        return
    assert os.path.isfile(ENSURE_BLENDER_PS1), "ensure_blender.ps1が無い"
    count, out = _ps51_parse_error_count(ENSURE_BLENDER_PS1)
    assert count == 0, "PS5.1パースエラーが{}件検出された:\n{}".format(count, out[-3000:])


def test_ps51_parse_negative_control_no_bom_fails():
    """負の対照: BOMを剥がした一時コピーは、同じPS5.1パーサチェックで必ず
    赤(構文エラー>0件)になること。これが緑のままだと上のtest_ps51_parses_clean
    自体が「たまたま通っただけ」の疑いが晴れないため、検査能力そのものを確認する。"""
    if shutil.which("powershell.exe") is None:
        print("SKIP: test_ps51_parse_negative_control_no_bom_fails: powershell.exeが無い環境")
        return
    assert os.path.isfile(ENSURE_BLENDER_PS1), "ensure_blender.ps1が無い"
    with open(ENSURE_BLENDER_PS1, "rb") as f:
        data = f.read()
    assert data[:3] == b"\xef\xbb\xbf", (
        "ensure_blender.ps1がBOM無しに戻っている(本テストの前提=正常系はBOM有りが崩れた)")
    stripped = data[3:]
    tmp = tempfile.mkdtemp(prefix="d2p_ensure_blender_negctrl_")
    try:
        no_bom_copy = os.path.join(tmp, "ensure_blender_no_bom.ps1")
        with open(no_bom_copy, "wb") as f:
            f.write(stripped)
        count, out = _ps51_parse_error_count(no_bom_copy)
        assert count is not None and count > 0, (
            "BOMを剥がしたコピーがPS5.1パースを通ってしまった(検査が効いていない):\n{}"
            .format(out[-3000:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_TESTS = [
    test_normal_path_with_cached_sourcezip,
    test_negative_sha256_mismatch_fails_closed,
    test_negative_invalid_url_fails_closed_with_marker,
    test_negative_missing_patch_materials_fails_closed,
    test_ps51_parses_clean,
    test_ps51_parse_negative_control_no_bom_fails,
]


if __name__ == "__main__":
    failures = []
    for t in _TESTS:
        try:
            t()
            print("PASS: {}".format(t.__name__))
        except Exception as e:  # noqa: BLE001
            failures.append(t.__name__)
            print("FAIL: {}: {}".format(t.__name__, e))
    if failures:
        print("\n{} failed: {}".format(len(failures), ", ".join(failures)))
        sys.exit(1)
    print("\nall {} tests passed".format(len(_TESTS)))
