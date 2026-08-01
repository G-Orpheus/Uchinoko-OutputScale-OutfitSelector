# GUIのビルド(Windows同梱の.NET Framework 4.8 csc.exeを使用、追加SDK不要)
# 出力: リポジトリ直下の Uchinoko.exe(v2.0.0改名。ソース・内部名はDiveToPalworldのまま)
param([string]$Out = "")  # 省略時はリポジトリ直下。梱包時はステージング先を指定
$ErrorActionPreference = "Stop"
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { Write-Error "csc.exeが無い(.NET Framework 4.8必須)"; exit 1 }
$here = $PSScriptRoot
$out = if ($Out) { $Out } else { Join-Path (Split-Path $here -Parent) "Uchinoko.exe" }
# 2026-07-29: favicon.ico(128/48/16のみ、32が抜けている)ではWindowsが32px表示箇所
# (エクスプローラー中アイコン等)で誤った拡大縮小をしうるため、ico\の各PNGから
# 16/32/48/128/256を作った ico\app.ico(work\wp_icon\build_ico.py生成)を使う。
# 無ければ従来のfavicon.icoへフォールバックする
$icon = Join-Path (Split-Path $here -Parent) "ico\app.ico"
if (-not (Test-Path $icon)) { $icon = Join-Path (Split-Path $here -Parent) "ico\favicon.ico" }
$iconArg = if (Test-Path $icon) { "/win32icon:$icon" } else { "" }

$srcPath = Join-Path $here "DiveToPalworld.cs"
$compileSrc = $srcPath
$src = Get-Content $srcPath -Raw -Encoding UTF8
# 2026-07-31: アセンブリメタデータ(AssemblyTitle/Product/Company/
# Version/FileVersion/Copyright/Description)の付与。バージョン番号はハードコード
# せず、DiveToPalworld.cs の ToolVersion 定数(既存のバージョン管理の唯一の正)から
# 取る。app\AssemblyInfo.cs のプレースホルダ("0.0.0.0")をここで実バージョンへ
# 置換した一時コピーを作り、DiveToPalworld.csと一緒にコンパイルする。
$versionMatch = [regex]::Match($src, 'const\s+string\s+ToolVersion\s*=\s*"v?([^"]+)"')
if (-not $versionMatch.Success) {
    Write-Error "DiveToPalworld.cs内にToolVersion定数が見つからない(アセンブリバージョンを決定できない)"
    exit 1
}
$assemblyVersion = $versionMatch.Groups[1].Value
$assemblyInfoPath = Join-Path $here "AssemblyInfo.cs"
$assemblyInfoSrc = Get-Content $assemblyInfoPath -Raw -Encoding UTF8
$versionPlaceholder = '0.0.0.0'
if ($assemblyInfoSrc -notlike "*$versionPlaceholder*") {
    Write-Error "AssemblyInfo.cs内にバージョンプレースホルダ($versionPlaceholder)が見つからない"
    exit 1
}
$patchedAssemblyInfo = $assemblyInfoSrc.Replace($versionPlaceholder, $assemblyVersion)
$compileAssemblyInfo = Join-Path ([System.IO.Path]::GetTempPath()) ("D2P_asmversion_" + [guid]::NewGuid().ToString("N") + ".cs")
[System.IO.File]::WriteAllText($compileAssemblyInfo, $patchedAssemblyInfo, (New-Object System.Text.UTF8Encoding($true)))

# 追加の圧縮・ネットワーク用アセンブリ参照は不要。
& $csc /nologo /target:winexe /out:$out /optimize+ $iconArg `
    /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll `
    $compileSrc $compileAssemblyInfo
$buildExit = $LASTEXITCODE
if ($compileSrc -ne $srcPath) { Remove-Item $compileSrc -Force -ErrorAction SilentlyContinue }
Remove-Item $compileAssemblyInfo -Force -ErrorAction SilentlyContinue
if ($buildExit -ne 0) { Write-Error "コンパイル失敗"; exit 1 }
Write-Host "built: $out (version=$assemblyVersion)"
