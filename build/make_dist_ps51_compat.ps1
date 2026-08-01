# BOOTH配布用フルセットzipを作る(Blenderポータブル同梱・約390MB)
# 使い方: pwsh -File make_dist.ps1 [-Version v0.1.0] [-Suffix _NEWLAYOUT]
# 出力: dist\Uchinoko_for_Palworld_<Version>_full<Suffix>.zip
# (v2.0.0改名: ユーザー可視面のみ Uchinoko for Palworld。ソース・内部名はDiveToPalworldのまま)
#
# U50: zipルートを「exe / _internal\ / README.md」の3点だけにする。
# 本体一式(exe実体を含む)を _internal\ へ丸ごと移し、相対関係を一切変えずに
# 畳んでいる。ルートのexeは _internal\Uchinoko.exe を起動するだけの
# ラッパー(本スクリプト内でソース生成→csc.exeでコンパイル)。
# この構成なら app\DiveToPalworld.cs の appRoot 解決
# (= Path.GetDirectoryName(Application.ExecutablePath) 直下に pipeline\ がある)
# も、pipeline\配下の $PSScriptRoot / REPO_DIR=dirname(pipeline) 相対解決も
# 従来どおりそのまま成立する(パス解決コードの改修ゼロ)。
param([string]$Version = "v1.0.0", [string]$Suffix = "")
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Stage = Join-Path $Root "dist\stage\Uchinoko_for_Palworld"
# U50: 配布物の中身はすべてここ(ルートに出るのは exe / _internal\ / README.md のみ)
$Internal = Join-Path $Stage "_internal"
$OutZip = Join-Path $Root "dist\Uchinoko_for_Palworld_${Version}_full${Suffix}.zip"

# u54(2026-07-27): Blenderポータブルの同梱を廃止した。配布zipにはBlender本体を
# 含めず、初回起動時に pipeline\cli\ensure_blender.ps1 が公式サイトから取得する
# (配布容量408MB→約9割を占めていたBlenderポータブル989MBが主因だった)。
# そのためmake_dist.ps1自体はもうBlenderポータブルの実体を必要としない
# (旧: tools\ / D2P_BLENDER_DIR からの探索+同梱処理。下の「pyooz/python3.dllの
# 差し込み素材同梱」節でensure_blender.ps1が使う小容量の差し込み素材だけを用意する)。

# U28: バージョン整合チェック(FRESH_QAレビュー3-9恒久対策)。
# app\DiveToPalworld.cs の ToolVersion と本スクリプトの $Version が食い違ったまま
# zipを作ると、配布物内部の表示バージョンとzipファイル名/呼び出し引数が
# ズレた状態で出荷されてしまう(過去の実害はまだ無いが構造的リスク)。
# 機械チェックとしてビルド前に強制検証する
Write-Host "=== バージョン整合チェック ==="
$CsPath = Join-Path $Root "app\DiveToPalworld.cs"
$CsContent = Get-Content $CsPath -Raw
$VersionMatch = [regex]::Match($CsContent, 'const\s+string\s+ToolVersion\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) { Write-Error "app\DiveToPalworld.cs内にToolVersion定数が見つからない"; exit 1 }
$CsVersion = $VersionMatch.Groups[1].Value
if ($CsVersion -ne $Version) {
    Write-Error "バージョン不一致: app\DiveToPalworld.cs の ToolVersion='$CsVersion' に対し make_dist.ps1 の `$Version='$Version'。一致させてから再実行してください(-Version引数 または ToolVersion定数を修正)"
    exit 1
}
Write-Host "  OK: ToolVersion = $Version"

Write-Host "=== ステージング ==="
Remove-Item (Join-Path $Root "dist\stage") -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Stage | Out-Null
New-Item -ItemType Directory -Force $Internal | Out-Null

# GUIをステージングへ直接ビルド(起動中のexeに触らない — ロック事故防止)
# U50: exe実体は _internal\ に置く。こうすると appRoot=_internal となり、
# pipeline\ / assets\ / research\ / unity\ / work\ / settings_*.txt / ue_project\
# の相対関係が従来の配布ルートとまったく同じになる(コード改修不要)
& pwsh -File (Join-Path $Root "app\build_app.ps1") -Out (Join-Path $Internal "Uchinoko.exe")
if ($LASTEXITCODE -ne 0) { exit 1 }

# U50: ルートのUchinoko.exe = _internal\Uchinoko.exe を起動するだけの
# 小さなラッパー。ソースはここで生成してcsc.exeでコンパイルし、ソースは梱包しない
# (リポジトリにファイルを増やさず、配布物のためだけの成果物をこのスクリプトに閉じる)。
# 形式に.exeを選んだ理由: ①ダブルクリック起動でコンソール窓が出ない(winexe)
# ②アイコンを持てる(本体と同じ ico\favicon.ico)③.lnkのようなターゲット解決の
# 曖昧さ(展開先が変わると壊れうる)が無く、常に自分の隣の_internal\を見る
Write-Host "=== ルート用ランチャーexeのビルド ==="
$LauncherDir = Join-Path $Root "dist\stage\_launcher"   # $Stageの外(zipに入らない)
New-Item -ItemType Directory -Force $LauncherDir | Out-Null
$LauncherCs = Join-Path $LauncherDir "Launcher.cs"
$LauncherSrc = @'
// Uchinoko for Palworld 起動ラッパー(配布zipルート専用)
// 本体は _internal\Uchinoko.exe。ルートを exe / _internal\ / README.md の
// 3点だけに保つため、本体一式は _internal\ に畳んである(相対関係は据え置き)。
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class DiveToPalworldLauncher
{
    [STAThread]
    static void Main()
    {
        string here = Application.StartupPath;
        string target = Path.Combine(Path.Combine(here, "_internal"), "Uchinoko.exe");
        if (!File.Exists(target))
        {
            MessageBox.Show(
                "Uchinoko for Palworld本体が見つかりません。" + Environment.NewLine + target + Environment.NewLine
                + Environment.NewLine
                + "zipを展開したフォルダの中の _internal フォルダを移動・削除していないか確認してください。",
                "Uchinoko for Palworld", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(target);
            psi.WorkingDirectory = Path.GetDirectoryName(target);
            psi.UseShellExecute = false;
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            MessageBox.Show("起動に失敗しました。" + Environment.NewLine + ex.Message,
                "Uchinoko for Palworld", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
'@
# csc.exeはBOMが無いソースをANSIコードページとして読むため、日本語(メッセージ本文)
# が化ける。BOM付きUTF-8で明示的に書き出す
[System.IO.File]::WriteAllText($LauncherCs, $LauncherSrc, (New-Object System.Text.UTF8Encoding($true)))
$Csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $Csc)) { Write-Error "csc.exeが無い(.NET Framework 4.8必須)"; exit 1 }
$LauncherOut = "/out:" + (Join-Path $Stage "Uchinoko.exe")
$LauncherIcon = Join-Path $Root "ico\favicon.ico"
$LauncherIconArg = if (Test-Path $LauncherIcon) { "/win32icon:$LauncherIcon" } else { "" }
& $Csc /nologo /target:winexe $LauncherOut /optimize+ $LauncherIconArg `
    /r:System.dll /r:System.Windows.Forms.dll $LauncherCs
if ($LASTEXITCODE -ne 0) { Write-Error "ランチャーのコンパイル失敗"; exit 1 }
Remove-Item $LauncherDir -Recurse -Force
# README.md / manual.html をルートに残す(ユーザーが最初に読むもの)。
# LICENSE / THIRD_PARTY_LICENSES.txt は配布物に同梱したまま _internal\ へ収める
# (MIT/GPLv3ともに「配布物に添付されていること」が要件であり、ルート直下である
#  必要はない。ライセンス本文・適用範囲・third_party\の同梱内容は一切変更していない)
Copy-Item (Join-Path $Root "README.md") $Stage
Copy-Item (Join-Path $Root "manual\manual.html") $Stage
Copy-Item (Join-Path $Root "LICENSE") $Internal
# U44: zipルート簡素化。pipeline\/unity\は直下のまま
# (根拠: pipeline\はtests\shipcheck\gates.py・README.mdのCLI手順が
#  "<配布物ルート>\pipeline\cli\convert.ps1" を固定パスで前提にしており、
#  unity\はpipeline\cli\export_from_unity.ps1の$Root相対解決
#  (このファイルも書き込み許可対象外)がpipeline\の直接の兄弟を要求する。
#  一方third_party\/tools\はjob.json経由(app\DiveToPalworld.csが解決)でしか
#  参照されないため安全に移動でき、assets\配下へ集約した(4節フォルダ→2節分削減)。
#  ico\は同梱そのものを廃止(下記参照)。詳細根拠はdocs\REPORT_U44_2026-07-25.md)
# (U50: これらの相互の相対関係は変えず、まとめて _internal\ の下へ移した)
# (U51: research\ue_exit\の実行時依存6ファイルをpipeline\py\へ移設したため、
#  research\は配布物に一切不要になった。以前はここでpipeline\/unity\と並んで
#  research\ue_exit\の一部だけを個別梱包していたが、その処理は削除した
#  — 下の「U14(廃止、U51で移設完了)」コメント参照)
foreach ($d in @("pipeline", "unity")) {
    Copy-Item (Join-Path $Root $d) (Join-Path $Internal $d) -Recurse
}

# 2026-07-25: 「影のみ更新」は convert.ps1 -MaterialsOnly → pipeline\py\fast_repack.py
# という経路で動く(noueモード)。2026-07-26: fast_repack.py はdevtools\から
# pipeline\py\へ移設済み(devtools\全体は非公開のため、出荷物側の実行時
# コンポーネントを置けない)。したがって上のforeach($d in @("pipeline","unity"))が
# pipeline\を丸ごとコピーする時点でfast_repack.pyも自動的に含まれる。
# 個別コピー・devtools\フォルダの作成はもう不要(旧実装はここで別途コピーしていた)。
New-Item -ItemType Directory -Force (Join-Path $Internal "assets") | Out-Null
Copy-Item (Join-Path $Root "third_party") (Join-Path $Internal "assets\third_party") -Recurse
# 梱包しない開発物の掃除
Remove-Item (Join-Path $Internal "pipeline\cli\smoke_all.ps1") -ErrorAction SilentlyContinue

# U14(廃止、U51で移設完了): かつてbuild_pak_from_avatar.pyがresearch\ue_exit\の
# 一部を直接import/subprocessしており、実行時に必要な6ファイル
# (dump_avatar_mesh.py/build_avatar_variant.py/build_avatar_variant_all.py/
# parse_sk_structure.py/parse_sk_full.py/parse_uasset_header.py)だけをここで
# 個別に梱包していた。U51でこれら6ファイルをpipeline\py\へ実体移設し(research\
# ue_exit\側は開発参照用に残置、無改変)、参照元(build_pak_from_avatar.py/
# live_template.py/preflight_pak.py/vp_matparam.py)もpipeline\py\の同居ファイルを
# 直接importするよう更新した。よって上のforeach(pipeline\をまるごとコピー)で
# 既にこの6ファイルも含まれており、research\ue_exit\の個別梱包は不要になった
# (=リポジトリのresearch\を配布物に一切含めなくても変換が完走する)。

# U18: 旧U14方式(開発側で一度cookしたPalworld本体由来の443ファイルテンプレを
# zipへ直接梱包)は廃止。テンプレート資産(vanilla由来)はPalworld本体
# (Pocketpair社の著作物)を含むため配布不可と判明したため(docs\ISSUES.md 2節、
# docs\REPORT_U18_2026-07-23.md参照)。既定noue経路は変換の都度ユーザー自身の
# Palworldインストールからライブ抽出する設計になり(pipeline\py\live_template.py/
# pak_live_extract.py、上のforeachで既にpipeline一式に含まれる)、事前cook済み
# テンプレフォルダの同梱は不要になった。プロジェクト独自資産(恒久マスター4種・
# noue_variants等、Palworld著作物ではない)は`pipeline\py\noue_master\`に
# 同梱済みで、pipelineディレクトリ丸ごとコピー(上のforeach)で既に含まれている

# U18: pyooz(GPLv3+、Oodle互換解凍。ooz_worker_gpl.py経由でsubprocess起動、
# 本体からimportしない)の実行環境を同梱。以下2点が無いとBlender同梱Python単独
# では`import ooz`が失敗すると判明(python3.dll不在によるDLL load failed):
#   ① ooz.pyd + 配布メタデータ(pyoozパッケージそのもの)をBlender同梱Pythonの
#      site-packagesへ配置(以後 sys.executable=Blender同梱pythonでそのままimport可能、
#      pak_live_extract.py._resolve_ooz_python()の②候補がここで解決する)
#   ② python3.dll(stable ABI用リダイレクタ。CPython公式配布物の一部、PSFライセンス、
#      ooz.pydがstable ABIビルドのため依存する。Blender同梱Pythonにはpython311.dllのみで
#      python3.dllが無いためDLL解決に失敗する。python.org公式配布のPython 3.11
#      python\bin\へ1ファイル追加するだけで解決、実機確認済み)
# 複雑なパッケージング技術(exe化等)は使わず、最も単純な形(ソース/バイナリ一式の
# ファイルコピー)に留める(0節聖域条項、指示書付録参照)
Write-Host "=== pyooz(GPLv3+、Oodle互換解凍)の同梱 ==="
$OozSitePkgSrc = "$env:APPDATA\Python\Python313\site-packages"
$OozPyd = Join-Path $OozSitePkgSrc "ooz.pyd"
if (-not (Test-Path $OozPyd)) { Write-Error "ooz.pydが見つからない: $OozPyd (pip install pyoozが必要)"; exit 1 }
# 2026-07-26: 開発機ユーザー名決め打ちパスを撤廃。$env:LOCALAPPDATAは呼び出したユーザーの
# AppData\Localへ自動解決されるため、python.orgの既定インストール先(ユーザー単位)であれば
# 誰の環境でもこの1行だけで足りる。既定と異なる場所に入れている場合は
# D2P_PYTHON311_DLL で明示指定できるようにした。
$Python3Dll = @(
    $env:D2P_PYTHON311_DLL,
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python3.dll")
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Python3Dll) {
    Write-Error (
        "python3.dll(Python 3.11版)が見つからない。`n" +
        "入手方法: https://www.python.org/downloads/release/python-3110/ (python.org公式)から" +
        "Windows installer (64-bit)を取得し、Python 3.11をインストールする" +
        "(python3.dllは同梱される)。`n" +
        "配置方法(いずれか一方):`n" +
        "  (1) 既定の場所(python.orgインストーラの既定: " +
        "%LOCALAPPDATA%\Programs\Python\Python311\python3.dll)にインストールする`n" +
        "  (2) python3.dllのフルパスを環境変数 D2P_PYTHON311_DLL に設定する`n" +
        "      例: `$env:D2P_PYTHON311_DLL = 'C:\path\to\Python311\python3.dll'"
    )
    exit 1
}

# u54(2026-07-27): Blender本体の同梱をやめ、代わりに ensure_blender.ps1 が
# 初回起動時に使う「差し込み素材」だけを小容量で同梱する。
# 旧実装(このすぐ上のコメント参照)はここでBlenderポータブル一式(989MB)を
# コピーしてから、その中のPython環境へooz.pyd/pyooz dist-info/python3.dllを
# 差し込み、続けてVC++ランタイム3本もBlender自身のblender.crt\から複製していた。
# 新実装ではBlenderの実体が無い(ダウンロードは初回起動時)ため、Blenderの
# Python環境への差し込みそのものができない。そこで「差し込む中身」だけを
# _internal\assets\blender_patch\ へ小容量(ooz.pyd + dist-info + python3.dll、
# 合計200KB弱)で同梱し、実際の差し込み(コピー先ディレクトリへの配置)は
# ensure_blender.ps1がダウンロード直後のBlenderに対して行う
# (pipeline\cli\ensure_blender.ps1 参照。VC++ランタイム3本はここでは同梱しない。
#  ダウンロードするBlender自身のblender.crt\に元々含まれているため、
#  ensure_blender.ps1がその場で複製する=新規追加なし、の方針を維持)。
Write-Host "=== blender_patch素材の同梱(ooz.pyd/pyooz dist-info/python3.dll) ==="
$BlenderPatchDir = Join-Path $Internal "assets\blender_patch"
New-Item -ItemType Directory -Force $BlenderPatchDir | Out-Null
Copy-Item $OozPyd (Join-Path $BlenderPatchDir "ooz.pyd") -Force
Get-ChildItem $BlenderPatchDir -Directory -Filter "pyooz-*.dist-info" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $OozSitePkgSrc "pyooz-*.dist-info") $BlenderPatchDir -Recurse
Copy-Item $Python3Dll (Join-Path $BlenderPatchDir "python3.dll") -Force
Write-Host "  ooz.pyd / pyooz-*.dist-info / python3.dll -> $BlenderPatchDir"

# U18: GPLv3+第三者コンポーネント(ooz_worker_gpl.py本体+pyooz)の存在とライセンスを明記
Write-Host "=== THIRD_PARTY_LICENSES.txt の作成 ==="
@"
DiveToPalworld本体は MIT License(LICENSE参照)です。

以下のコンポーネントはGPLv3+ (GNU General Public License v3 or later) であり、
本体からは常にsubprocess経由でのみ起動されます(importもリンクもしない、
"mere aggregation"構成。ffmpeg.exe等の外部実行ファイルをMITツールが
subprocessで呼ぶのと同じ扱いです)。

1. _internal\pipeline\py\ooz_worker_gpl.py
   本体からpyoozを呼び出すための単独完結した別プロセス実行体。
   ライセンス: GPLv3 (ファイル冒頭のヘッダ参照)

2. pyooz (初回起動時にダウンロードするBlenderの
   python\lib\site-packages\ooz.pyd等へ配置。差し込み素材そのものは
   _internal\assets\blender_patch\ooz.pyd に小容量で同梱)
   Oodle互換解凍ライブラリoozのPythonバインディング。
   配布元: https://pypi.org/project/pyooz/ (https://github.com/zao/pyooz)
   ライセンス: GPLv3+ (GNU General Public License v3 or later)

GPLv3全文: https://www.gnu.org/licenses/gpl-3.0.txt

Blender Portable(GPL、公式配布に GPL-3.0-or-later.txt / GPL-2.0-or-later.txt 同梱)は
この配布物(zip)には含まれません。初回起動時にツールが公式サイト
(https://www.blender.org/download/) から自動的にダウンロードし、
_internal\assets\tools\ に配置します(SHA256をピン留めして照合。
pipeline\cli\ensure_blender.ps1 参照)。

python3.dll(初回起動時にダウンロードするBlenderの
python\bin\python3.dll へ配置。差し込み素材そのものは
_internal\assets\blender_patch\python3.dll に同梱)は
CPython公式配布物の一部(PSFライセンス)です。 https://www.python.org/

vcruntime140.dll / vcruntime140_1.dll / msvcp140.dll(初回起動時にダウンロードする
Blenderのpython\bin\および python\lib\site-packages\に配置)はMicrosoft Visual
C++ Redistributableの一部です。この配布物(zip)には含まれません。新規に追加
するものではなく、初回起動時にダウンロードするBlenderポータブル本体
(blender.crt\)が元々再頒布している実体を、そのまま複製配置するだけです
(2026-07-26追加、Windows Sandboxでのpython.exe起動失敗対策。u54でBlender
本体の取得タイミングが変わった後も複製元・複製内容は不変)。
"@ | Set-Content -Encoding utf8 (Join-Path $Internal "THIRD_PARTY_LICENSES.txt")

# U28: 開発残骸の除外(FRESH_QAレビュー3-7)。pipeline\をCopy-Item -Recurseで
# 丸ごとコピーしているため開発中の*.bak系ファイルが混入する事故クラスが判明。
# (u54でBlenderポータブル本体の同梱自体を廃止したため、旧来の「梱包する
# Blenderポータブル自体に付着した__pycache__」という混入経路は無くなったが、
# pipeline\の__pycache__混入経路は変わらず残るため、本チェック自体は維持する)
# 本チェックはblender_patch素材同梱が終わった後・zip作成直前(ステージング全体が
# 揃った時点)で実行する。パターンは監査(devtools\u28_zip_audit.py)と
# 同じ根拠で選定。過剰除外を避けるため、正式に必要なファイルを指す
# パターンにはしていない(例: *.jsonのような広いパターンは使わない)
Write-Host "=== 開発残骸の除外(ステージング全体) ==="
$ResidueDirFilters = @("__pycache__", ".pytest_cache")
foreach ($filt in $ResidueDirFilters) {
    Get-ChildItem $Stage -Recurse -Directory -Filter $filt -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
# 「*_diag」で終わる作業ディレクトリ(u21_diag等、本来work\配下限定だが
# 将来pipeline\配下に迷い込む事故に備えた防御的除外)
Get-ChildItem $Stage -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "*_diag" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$ResidueFileFilters = @("*.bak", "*.bak_*", "*.bak2_*", "*.orig", "*.log")
foreach ($filt in $ResidueFileFilters) {
    Get-ChildItem $Stage -Recurse -File -Filter $filt -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-Host "=== zip作成 ==="
New-Item -ItemType Directory -Force (Join-Path $Root "dist") | Out-Null
Remove-Item $OutZip -ErrorAction SilentlyContinue
Compress-Archive -Path $Stage -DestinationPath $OutZip -CompressionLevel Optimal
Remove-Item (Join-Path $Root "dist\stage") -Recurse -Force

Write-Host ""
Write-Host ("完成: {0} ({1:F0} MB)" -f $OutZip, ((Get-Item $OutZip).Length / 1MB))
Write-Host "BOOTHへアップロードしてください(1ファイル1GB上限内)"
