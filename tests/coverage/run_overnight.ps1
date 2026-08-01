<#
.SYNOPSIS
  U53 カバレッジ検査を無人で一晩回す(1コマンド)。

.DESCRIPTION
  これ1本で完結する。途中で人の操作を求めない。

    pwsh -NoProfile -File tests\coverage\run_overnight.ps1

  * 実変換は行う(--allow-convert)。1本あたり数分 × 15本程度 = 2〜3時間目安
  * **実機(Palworld)には一切触らない**(--allow-machine を付けないので
    @machine のテストは pytest.ini の `-m "not machine"` で除外される)
  * 1件 FAIL しても最後まで回る(-x を付けない)
  * 結果は work\u53_cov\reports\<timestamp>\ に残る
      progress.log   … 1件ごとの進行(実行中でも読める)
      report.md      … 判定一覧(FAIL → SKIP → PASS 順)
      coverage.md    … カバー状況の表
      gates.jsonl / tests.jsonl / provenance.json
      pytest_stdout.log … pytest の生出力

.PARAMETER Machine
  指定すると実機ゲート(E: クラッシュ / F: プレイ開始)も回す。
  **既定では回らない。**Palworld を起動してよい状況でだけ付けること。

.PARAMETER Unity
  指定すると .prefab 検体(C:\UnityP\ の4体)を Unity ヘッドレスで輸出し、
  MA(NDMF)ベイク込みで端から端まで通す。**既定では回らない。**

  付ける前に確認すること:
    * 対象の Unity プロジェクトを **Unity で開いていないこと**(二重起動禁止)
    * **プロジェクト側へ書き込みが起きる**ことを許容できること
      (Assets\Editor\DiveToPalworldExporter.cs の複製、
       FBX Exporter 未導入なら Packages\manifest.json への追記)
  1体あたり数分〜十数分(初回インポートを含むとさらに)。

.PARAMETER Specimens
  入力形式軸で回す検体(既定 all)。配線確認だけなら `fast`。
  ※ prefab 検体はこの指定の対象外(常に4体すべて)。

.PARAMETER SelfTestOnly
  負の対照(モック自己検証)だけを回す。実変換も実機接触も起きない。数秒で終わる。
#>
[CmdletBinding()]
param(
    [switch]$Machine,
    [switch]$Unity,
    [string]$Specimens = "all",
    [switch]$SelfTestOnly
)

$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$repo = Split-Path (Split-Path $PSCommandPath -Parent) -Parent
$repo = Split-Path $repo -Parent   # tests\coverage -> tests -> repo
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $repo "work\u53_cov\reports\$stamp"
New-Item -ItemType Directory -Force $runDir | Out-Null

$suite = Join-Path $repo "tests\coverage"
# $args はPowerShellの自動変数なので使わない(CmdletBinding付きスクリプトでは
# 代入できずスクリプトごと死ぬ)
$pyArgs = @("-m", "pytest", $suite, "--run-dir", $runDir, "-v")

if ($SelfTestOnly) {
    $pyArgs = @("-m", "pytest", (Join-Path $suite "selftest"), "--run-dir", $runDir, "-v")
} else {
    $pyArgs += @("--allow-convert", "--specimens", $Specimens)
    # pytest.ini の addopts が `-m "not machine"` なので、後勝ちで全部拾う式へ上書きする
    if ($Machine) { $pyArgs += @("-m", "machine or not machine", "--allow-machine") }
    if ($Unity) { $pyArgs += @("--allow-unity") }
}

Write-Host "=== U53 カバレッジ検査 ==="
Write-Host "run_dir : $runDir"
Write-Host "cmd     : python $($pyArgs -join ' ')"
Write-Host "実機接触: $(if ($Machine) { '**あり**' } else { 'なし(既定)' })"
Write-Host "Unity起動: $(if ($Unity) { '**あり**(prefab 4体。プロジェクトを閉じておくこと)' } else { 'なし(既定)' })"
Write-Host ""
Write-Host "進行は次のファイルで追える(別ウィンドウで):"
Write-Host "  Get-Content -Wait '$runDir\progress.log'"
Write-Host ""

$stdout = Join-Path $runDir "pytest_stdout.log"
& python @pyArgs 2>&1 | Tee-Object -FilePath $stdout
$code = $LASTEXITCODE

Write-Host ""
Write-Host "=== 終了 (pytest exit=$code) ==="
Write-Host "レポート: $runDir\report.md"
Write-Host "カバー表: $runDir\coverage.md"
# 無人運転なので、FAIL があっても このスクリプト自体は結果コードをそのまま返す。
exit $code
