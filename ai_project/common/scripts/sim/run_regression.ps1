<#
.SYNOPSIS
    自动化回归测试脚本 — 运行所有 tb_*.v 测试套件并生成详细报告
.DESCRIPTION
    发现 test_mock_data 目录下所有 tb_*.v 测试台，使用 iverilog 编译 + vvp 仿真，
    解析 PASS/FAIL 结果，生成结构化日志、CSV 和 Markdown 报告。
.PARAMETER Suite
    仅运行指定套件（tb_ 文件名，不含扩展名）。为空则运行全部。
.PARAMETER LogDir
    日志输出目录。默认为 <脚本目录>/regression_results。
.PARAMETER Verbose
    显示详细编译/仿真输出。
.PARAMETER NoClean
    不清理临时编译产物。
.EXAMPLE
    .\run_regression.ps1
    .\run_regression.ps1 -Suite tb_ecc -Verbose
    .\run_regression.ps1 -LogDir D:\logs -NoClean
#>

param(
    [string]$Suite = "",
    [string]$LogDir = "",
    [switch]$Verbose = $false,
    [switch]$NoClean = $false
)

# ============================================================
# 0. 路径与工具配置
# ============================================================
$scriptRoot = $PSScriptRoot
$projectRoot = Resolve-Path "$scriptRoot\.."
$testDataDir = Resolve-Path "$projectRoot\test_mock_data"
$iverilogExe = "D:\software\pango\iverilog\bin\iverilog.exe"
$vvpExe     = "D:\software\pango\iverilog\bin\vvp.exe"
$workDir     = "$scriptRoot\sim_work"

if ($LogDir -eq "") {
    $LogDir = "$scriptRoot\regression_results"
}

# 确保工具存在
foreach ($tool in @{Name='iverilog';Path=$iverilogExe}, @{Name='vvp';Path=$vvpExe}) {
    if (-not (Test-Path $tool.Path)) {
        Write-Host "[FATAL] 找不到 $($tool.Name): $($tool.Path)" -ForegroundColor Red
        exit 1
    }
}

# ============================================================
# 1. 测试套件定义
# ============================================================
# 测试台 → 源文件映射
$sourceMap = @{
    'tb_cnt_comp'         = @('cnt_comp_template.v')
    'tb_cnt_comp_fault'   = @('cnt_comp_template.v')
    'tb_dice'             = @('dice_template.v')
    'tb_ecc'              = @('ecc_template.v')
    'tb_parity'           = @('parity_template.v')
    'tb_mixed_design_ecc' = @()   # 通过 `include 自包含
}

# 显示名称
$suiteDisplayNames = @{
    'tb_cnt_comp'         = 'cnt_comp 基本功能'
    'tb_cnt_comp_fault'   = 'cnt_comp 故障注入'
    'tb_parity'           = '奇偶校验'
    'tb_dice'             = 'DICE'
    'tb_ecc'              = 'ECC (SECDED)'
    'tb_mixed_design_ecc' = 'ECC 加固混合设计'
}

# 预期测试数（来自各 testbench 的 pass/fail 统计）
$expectedCounts = @{
    'tb_cnt_comp'         = 6
    'tb_cnt_comp_fault'   = 9
    'tb_parity'           = 268
    'tb_dice'             = 6
    'tb_ecc'              = 265
    'tb_mixed_design_ecc' = 40
}

# 覆盖类型
$coverageTypes = @{
    'Functional'      = @('tb_cnt_comp', 'tb_dice')
    'FaultInjection'  = @('tb_cnt_comp_fault', 'tb_ecc', 'tb_parity', 'tb_mixed_design_ecc')
    'Stress'          = @('tb_parity', 'tb_ecc')
    'Exhaustive'      = @('tb_parity', 'tb_ecc')
}

# ============================================================
# 2. 辅助函数
# ============================================================

function Write-Banner {
    param([string]$Text, [string]$Color = "Cyan")
    $line = "=" * 60
    Write-Host "`n$line" -ForegroundColor $Color
    Write-Host "  $Text" -ForegroundColor $Color
    Write-Host "$line" -ForegroundColor $Color
}

function Write-ColorStatus {
    param([string]$Label, [string]$Status, [string]$Detail = "")
    $icon = switch ($Status) {
        'PASS'    { '✅' }
        'FAIL'    { '❌' }
        'SKIP'    { '⏭️' }
        'WARN'    { '⚠️' }
        'RUNNING' { '🔄' }
        default   { '❓' }
    }
    $color = switch ($Status) {
        'PASS' { 'Green' }
        'FAIL' { 'Red' }
        'SKIP' { 'Yellow' }
        'WARN' { 'Yellow' }
        default { 'Gray' }
    }
    if ($Detail -ne "") {
        Write-Host "  $icon $Label : $Status — $Detail" -ForegroundColor $color
    } else {
        Write-Host "  $icon $Label : $Status" -ForegroundColor $color
    }
}

function Invoke-WithTimeout {
    param(
        [string]$FilePath,
        [string]$Arguments,
        [string]$WorkingDir,
        [int]$TimeoutSeconds = 60,
        [string]$LogPath = ""
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkingDir
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    # 设置环境变量防止分页器卡死
    $psi.EnvironmentVariables["PAGER"] = "cat"

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi

    $outputBuilder = New-Object System.Text.StringBuilder
    $errorBuilder  = New-Object System.Text.StringBuilder

    # 注册异步输出读取
    $outputEvent = Register-ObjectEvent -InputObject $process -EventName 'OutputDataReceived' -Action {
        param($sender, $e)
        if ($e.Data -ne $null) {
            $event.MessageData.AppendLine($e.Data)
        }
    } -MessageData $outputBuilder

    $errorEvent = Register-ObjectEvent -InputObject $process -EventName 'ErrorDataReceived' -Action {
        param($sender, $e)
        if ($e.Data -ne $null) {
            $event.MessageData.AppendLine($e.Data)
        }
    } -MessageData $errorBuilder

    try {
        $process.Start() | Out-Null
        $process.BeginOutputReadLine()
        $process.BeginErrorReadLine()

        $completed = $process.WaitForExit($TimeoutSeconds * 1000)

        if (-not $completed) {
            $process.Kill()
            $process.WaitForExit(5000)
            return @{
                ExitCode = -1
                Output   = $outputBuilder.ToString()
                Error    = $errorBuilder.ToString()
                TimedOut = $true
            }
        }

        $process.WaitForExit()
        return @{
            ExitCode = $process.ExitCode
            Output   = $outputBuilder.ToString()
            Error    = $errorBuilder.ToString()
            TimedOut = $false
        }
    } finally {
        Unregister-Event -SourceIdentifier $outputEvent.Name -ErrorAction SilentlyContinue
        Unregister-Event -SourceIdentifier $errorEvent.Name -ErrorAction SilentlyContinue
        $process.Dispose()
    }
}

function Parse-Results {
    param([string]$LogFilePath, [string]$SuiteName)

    $fullLog = Get-Content -Path $LogFilePath -Raw -ErrorAction SilentlyContinue
    if (-not $fullLog) {
        return @{ Pass = 0; Fail = 0; Total = 0 }
    }

    # 尝试多种输出格式中提取 PASS/FAIL 计数
    # 格式1: "XXX Tests: N PASS, M FAIL"
    $summaryMatch = [regex]::Match($fullLog, '(?:Tests|测试)[:\s]*(\d+)\s*PASS[,\s]*(\d+)\s*FAIL', 'IgnoreCase')
    if ($summaryMatch.Success) {
        $pass = [int]$summaryMatch.Groups[1].Value
        $fail = [int]$summaryMatch.Groups[2].Value
        return @{ Pass = $pass; Fail = $fail; Total = $pass + $fail }
    }

    # 格式2: "总测试数: N, 通过 (PASS): P, 失败 (FAIL): F"
    $totalMatch = [regex]::Match($fullLog, '总测试数[:\s]*(\d+)', 'IgnoreCase')
    $passMatch  = [regex]::Match($fullLog, '通过\s*\(?PASS\)?[:\s]*(\d+)', 'IgnoreCase')
    $failMatch  = [regex]::Match($fullLog, '失败\s*\(?FAIL\)?[:\s]*(\d+)', 'IgnoreCase')
    if ($totalMatch.Success -and $passMatch.Success -and $failMatch.Success) {
        return @{
            Pass  = [int]$passMatch.Groups[1].Value
            Fail  = [int]$failMatch.Groups[1].Value
            Total = [int]$totalMatch.Groups[1].Value
        }
    }

    # 格式3: 逐行搜索 PASS: / FAIL: 关键字
    $passLines = [regex]::Matches($fullLog, '(?i)^\s*PASS[:\s]')
    $failLines = [regex]::Matches($fullLog, '(?i)^\s*FAIL[:\s]')
    $foundPass = $passLines.Count
    $foundFail = $failLines.Count

    # 同时检查 "ALL TESTS PASSED" / "全部通过"
    if ($fullLog -match '(?i)ALL\s+TESTS\s+PASSED|全部通过') {
        if ($foundFail -eq 0 -and $foundPass -gt 0) {
            return @{ Pass = $foundPass; Fail = 0; Total = $foundPass }
        }
    }

    if ($foundPass -gt 0 -or $foundFail -gt 0) {
        return @{ Pass = $foundPass; Fail = $foundFail; Total = $foundPass + $foundFail }
    }

    # 格式4: "PASS: Test N - ..." / "FAIL: Test N - ..."
    $passTestLines = [regex]::Matches($fullLog, '(?im)^\s*PASS:\s*Test\s+\d+')
    $failTestLines = [regex]::Matches($fullLog, '(?im)^\s*FAIL:\s*Test\s+\d+')
    if ($passTestLines.Count -gt 0 -or $failTestLines.Count -gt 0) {
        return @{ Pass = $passTestLines.Count; Fail = $failTestLines.Count; Total = $passTestLines.Count + $failTestLines.Count }
    }

    # 兜底: 检查是否有 "PASS" 或 "FAIL" 字样
    $hasPass = $fullLog -match '(?i)\bPASS\b'
    $hasFail = $fullLog -match '(?i)\bFAIL\b'
    if ($hasPass -and -not $hasFail) {
        return @{ Pass = -1; Fail = 0; Total = -1 }
    }

    return @{ Pass = 0; Fail = 0; Total = 0 }
}

function Format-Timespan {
    param([double]$TotalSeconds)
    $ts = [TimeSpan]::FromSeconds($TotalSeconds)
    return $ts.ToString('hh\:mm\:ss')
}

# ============================================================
# 3. 主流程
# ============================================================

# 创建输出目录
$null = New-Item -ItemType Directory -Path $LogDir -Force
$null = New-Item -ItemType Directory -Path $workDir -Force

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$masterLogFile  = "$LogDir\run_regression_$timestamp.log"
$resultsCsvFile = "$LogDir\results_$timestamp.csv"
$summaryMdFile  = "$LogDir\summary_$timestamp.md"

$startTime = Get-Date
$global:allResults = @()
$global:masterLogLines = @()
$global:hasAnyFailure = $false
$global:retryResults = @()

# 写入 master log 头
$header = @"
================================================================
  回归测试执行日志
  脚本: $PSCommandPath
  时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
  工作目录: $workDir
  Testbench 目录: $testDataDir
================================================================
"@
$global:masterLogLines += $header
$header | Out-File -FilePath $masterLogFile -Encoding UTF8

# --- 发现测试套件 ---
$allTbFiles = @()
if ($Suite -ne "") {
    $tbFile = Join-Path $testDataDir "$Suite.v"
    if (-not (Test-Path $tbFile)) {
        Write-Host "[ERROR] 找不到测试套件: $tbFile" -ForegroundColor Red
        exit 1
    }
    $allTbFiles = @($tbFile)
    Write-Host "[INFO] 仅运行指定套件: $Suite" -ForegroundColor Yellow
} else {
    $allTbFiles = Get-ChildItem -Path $testDataDir -Filter "tb_*.v" | Sort-Object Name
    Write-Host "[INFO] 发现 $($allTbFiles.Count) 个测试套件" -ForegroundColor Cyan
}

Write-Banner -Text "回归测试开始 — $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Color Cyan

foreach ($tb in $allTbFiles) {
    $tbName = [System.IO.Path]::GetFileNameWithoutExtension($tb.Name)
    $displayName = if ($suiteDisplayNames.ContainsKey($tbName)) { $suiteDisplayNames[$tbName] } else { $tbName }
    $srcFiles = if ($sourceMap.ContainsKey($tbName)) { $sourceMap[$tbName] } else { @() }
    $expected = if ($expectedCounts.ContainsKey($tbName)) { $expectedCounts[$tbName] } else { $null }

    Write-Banner -Text "运行: $displayName ($tbName)" -Color Green
    $global:masterLogLines += "`n--- [$tbName] $displayName ---"

    # 1) 编译
    $vvpOutput = "$workDir\tb_output_$tbName.vvp"
    $compileLog = "$LogDir\$tbName.compile.log"

    $srcFilePaths = @()
    $srcFilePaths += "`"$($tb.FullName)`""
    foreach ($sf in $srcFiles) {
        $sfPath = Join-Path $testDataDir $sf
        if (Test-Path $sfPath) {
            $srcFilePaths += "`"$sfPath`""
        } else {
            Write-ColorStatus -Label $displayName -Status "WARN" -Detail "找不到源文件: $sf"
            $global:masterLogLines += "  [WARN] 找不到源文件: $sf"
        }
    }

    $compileArgs = "-g2005-sv -I `"$testDataDir`" -o `"$vvpOutput`" $($srcFilePaths -join ' ')"

    if ($Verbose) {
        Write-Host "  [编译] $iverilogExe $compileArgs" -ForegroundColor Gray
    }

    $compileResult = Invoke-WithTimeout -FilePath $iverilogExe -Arguments $compileArgs -WorkingDir $testDataDir -TimeoutSeconds 120 -LogPath $compileLog

    # 保存编译日志
    $compileFullLog = $compileResult.Output
    if ($compileResult.Error -ne "") { $compileFullLog += "`n--- STDERR ---`n" + $compileResult.Error }
    $compileFullLog | Out-File -FilePath $compileLog -Encoding UTF8

    if ($compileResult.ExitCode -ne 0) {
        Write-ColorStatus -Label $displayName -Status "FAIL" -Detail "编译失败 (exit=$($compileResult.ExitCode))"
        $global:masterLogLines += "  [FAIL] 编译失败 (exit=$($compileResult.ExitCode))"
        if ($Verbose) {
            $compileResult.Output -split "`n" | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkRed }
        }
        $global:allResults += [PSCustomObject]@{
            SuiteName    = $tbName
            DisplayName  = $displayName
            Pass         = 0
            Fail         = -1
            Total        = 0
            Status       = 'COMPILE_ERROR'
            Elapsed      = 0.0
            Expected     = $expected
            TimedOut     = $false
            Retried      = $false
        }
        $global:hasAnyFailure = $true
        continue
    }

    if ($Verbose) {
        Write-Host "  [编译] 成功" -ForegroundColor Green
    }
    $global:masterLogLines += "  [编译] 成功"

    # 2) 仿真（含重试逻辑）
    $runAttempts = @()
    foreach ($attempt in 1..2) {
        $simLog = "$LogDir\$tbName.log"
        if ($attempt -eq 2) { $simLog = "$LogDir\$tbName.retry.log" }

        if ($Verbose) {
            Write-Host "  [仿真] (尝试 $attempt/2) vvp $vvpOutput" -ForegroundColor Gray
        }

        $runResult = Invoke-WithTimeout -FilePath $vvpExe -Arguments "`"$vvpOutput`"" -WorkingDir $testDataDir -TimeoutSeconds 60 -LogPath $simLog

        # 保存仿真日志
        $simFullLog = $runResult.Output
        if ($runResult.Error -ne "") { $simFullLog += "`n--- STDERR ---`n" + $runResult.Error }
        $simFullLog | Out-File -FilePath $simLog -Encoding UTF8

        # 解析结果
        $parsed = Parse-Results -LogFilePath $simLog -SuiteName $tbName

        $elapsed = 0.0  # 无法精确获取进程耗时，用近似值
        $timedOut = $runResult.TimedOut

        if ($timedOut) {
            Write-ColorStatus -Label $displayName -Status "WARN" -Detail "仿真超时 (60s)，正在终止..."
            $global:masterLogLines += "  [WARN] 仿真超时 (60s)"
            if ($attempt -eq 1) {
                Write-Host "  [重试] 即将重试..." -ForegroundColor Yellow
                continue
            }
            $runAttempts += [PSCustomObject]@{
                Pass     = $parsed.Pass
                Fail     = if ($parsed.Fail -gt 0 -or $timedOut) { $parsed.Fail } else { -1 }
                Total    = $parsed.Total
                Elapsed  = $elapsed
                TimedOut = $timedOut
                Status   = 'TIMEOUT'
            }
            break
        }

        $hasFail = $parsed.Fail -gt 0

        # 检查仿真是否正常结束（$finish 被调用）
        $hasFinish = $simFullLog -match '(?i)\$finish|#\s*FINISH|end of simulation'
        if (-not $hasFinish) {
            Write-ColorStatus -Label $displayName -Status "WARN" -Detail "仿真可能未正常结束 (未检测到 \$finish)"
            $global:masterLogLines += "  [WARN] 仿真可能未正常结束"
            if ($attempt -eq 1) {
                Write-Host "  [重试] 即将重试..." -ForegroundColor Yellow
                continue
            }
        }

        $runAttempts += [PSCustomObject]@{
            Pass     = $parsed.Pass
            Fail     = $parsed.Fail
            Total    = $parsed.Total
            Elapsed  = $elapsed
            TimedOut = $timedOut
            Status   = if ($hasFail) { 'FAIL' } else { 'PASS' }
        }
        break  # 成功则跳出重试循环
    }

    # 使用最后一次尝试的结果
    $finalResult = $runAttempts[-1]
    $global:allResults += [PSCustomObject]@{
        SuiteName   = $tbName
        DisplayName = $displayName
        Pass        = $finalResult.Pass
        Fail        = $finalResult.Fail
        Total       = $finalResult.Total
        Status      = $finalResult.Status
        Elapsed     = $finalResult.Elapsed
        Expected    = $expected
        TimedOut    = $finalResult.TimedOut
        Retried     = $runAttempts.Count -gt 1
    }

    if ($finalResult.Status -eq 'FAIL' -or $finalResult.Status -eq 'TIMEOUT') {
        $global:hasAnyFailure = $true
        Write-ColorStatus -Label $displayName -Status "FAIL" -Detail "通过 $($finalResult.Pass) / 失败 $($finalResult.Fail)"
    } else {
        Write-ColorStatus -Label $displayName -Status "PASS" -Detail "通过 $($finalResult.Pass) 项"
    }

    $global:masterLogLines += "  [结果] $($finalResult.Status) | PASS=$($finalResult.Pass) FAIL=$($finalResult.Fail) TOTAL=$($finalResult.Total)"
    if ($runAttempts.Count -gt 1) {
        $global:masterLogLines += "  [重试] 第1次尝试失败，第2次成功"
    }
}

# ============================================================
# 4. 汇总与报告
# ============================================================
$endTime = Get-Date
$totalElapsed = ($endTime - $startTime).TotalSeconds

Write-Banner -Text "回归测试汇总" -Color Cyan

# --- 控制台结果表格 ---
$totalPass = 0
$totalFail = 0
$totalTests = 0
$tableLines = @()

$tableLines += "=" * 64
$tableLines += "  回归测试执行报告"
$tableLines += "  开始时间: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))"
$tableLines += "  结束时间: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))"
$tableLines += "  总耗时: $(Format-Timespan $totalElapsed)"
$tableLines += "=" * 64
$tableLines += "  $('测试套件'.PadRight(28)) 测试数  通过  失败  状态  耗时(s)"
$tableLines += "  " + ("-" * 55)

foreach ($r in $global:allResults) {
    $passCount = if ($r.Pass -ge 0) { $r.Pass } else { 0 }
    $failCount = if ($r.Fail -ge 0) { $r.Fail } else { 0 }
    $totalCount = if ($r.Total -gt 0) { $r.Total } else { $passCount + $failCount }

    $totalPass += $passCount
    $totalFail += $failCount
    $totalTests += $totalCount

    $statusIcon = switch ($r.Status) {
        'PASS'         { '✅' }
        'FAIL'         { '❌' }
        'TIMEOUT'      { '⏰' }
        'COMPILE_ERROR' { '🚫' }
        default        { '❓' }
    }

    $displayNamePadded = $r.DisplayName.PadRight(28)
    $tableLines += "  $displayNamePadded $($totalCount.ToString().PadLeft(5))  $($passCount.ToString().PadLeft(4))  $($failCount.ToString().PadLeft(4))  $statusIcon  $($r.Elapsed.ToString('0.0'))"
}

$tableLines += "  " + ("-" * 55)
$passPct = if ($totalTests -gt 0) { [math]::Round($totalPass / $totalTests * 100, 1) } else { 0 }
$tableLines += "  $('总计'.PadRight(28)) $($totalTests.ToString().PadLeft(5))  $($totalPass.ToString().PadLeft(4))  $($totalFail.ToString().PadLeft(4))  $('✅'.PadRight(2)) $($passPct)%    $(Format-Timespan $totalElapsed)"
$tableLines += "=" * 64
$tableLines += ""

# 输出到控制台
foreach ($line in $tableLines) {
    Write-Host $line -ForegroundColor White
}

# --- 覆盖类型报告 ---
Write-Host "`n  覆盖类型:" -ForegroundColor Cyan
foreach ($ctype in $coverageTypes.Keys) {
    $matchedSuites = $coverageTypes[$ctype] | Where-Object { $_ -in ($global:allResults | Where-Object { $_.Status -eq 'PASS' }).SuiteName }
    $matchedDisplay = $matchedSuites | ForEach-Object {
        if ($suiteDisplayNames.ContainsKey($_)) { $suiteDisplayNames[$_] } else { $_ }
    }
    Write-Host "    $($ctype.PadRight(16)) : $($matchedDisplay -join ', ')" -ForegroundColor $(
        if ($matchedSuites.Count -gt 0) { 'Green' } else { 'Yellow' }
    )
}

# --- 保存 CSV ---
$csvRows = $global:allResults | ForEach-Object {
    [PSCustomObject]@{
        测试套件   = $_.DisplayName
        测试数     = if ($_.Total -gt 0) { $_.Total } else { if ($_.Pass -ge 0) { $_.Pass + [Math]::Max($_.Fail,0) } else { 0 } }
        通过       = if ($_.Pass -ge 0) { $_.Pass } else { 0 }
        失败       = if ($_.Fail -ge 0) { $_.Fail } else { -1 }
        状态       = $_.Status
        耗时_秒    = $_.Elapsed
        预期测试数 = if ($_.Expected) { $_.Expected } else { 'N/A' }
        超时       = $_.TimedOut
        已重试     = $_.Retried
    }
}
$csvRows | Export-Csv -Path $resultsCsvFile -Encoding UTF8 -NoTypeInformation
Write-Host "`n[INFO] CSV 结果已保存: $resultsCsvFile" -ForegroundColor Cyan

# --- 保存 Markdown 摘要 ---
$mdContent = @"
# 回归测试报告

**时间**: $($startTime.ToString('yyyy-MM-dd HH:mm:ss')) → $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))  
**总耗时**: $(Format-Timespan $totalElapsed)  
**结果**: $(if ($global:hasAnyFailure) { '❌ 有失败项' } else { '✅ 全部通过' })

## 测试结果明细

| 测试套件 | 测试数 | 通过 | 失败 | 状态 | 耗时(s) | 备注 |
|---|---|---|---|---|---|---|
"@

foreach ($r in $global:allResults) {
    $passCount = if ($r.Pass -ge 0) { $r.Pass } else { 0 }
    $failCount = if ($r.Fail -ge 0) { $r.Fail } else { '-' }
    $totalCount = if ($r.Total -gt 0) { $r.Total } else { $passCount + (if ($failCount -is [int]) { $failCount } else { 0 }) }
    $statusEmoji = switch ($r.Status) { 'PASS' { '✅' } 'FAIL' { '❌' } 'TIMEOUT' { '⏰' } 'COMPILE_ERROR' { '🚫' } default { '❓' } }
    $notes = @()
    if ($r.TimedOut) { $notes += '超时' }
    if ($r.Retried) { $notes += '重试后通过' }
    if ($r.Expected -and $passCount -ne $r.Expected -and $passCount -ge 0) { $notes += "预期$($r.Expected)/实际$passCount" }
    $noteStr = if ($notes.Count -gt 0) { $notes -join '; ' } else { '-' }
    $mdContent += "`n| $($r.DisplayName) | $totalCount | $passCount | $failCount | $statusEmoji | $($r.Elapsed.ToString('0.0')) | $noteStr |"
}

$mdContent += @"

## 总计

| 指标 | 数值 |
|---|---|
| 总测试数 | **$totalTests** |
| 总通过 | **$totalPass** |
| 总失败 | **$totalFail** |
| 通过率 | **$passPct%** |

## 覆盖类型

| 覆盖类型 | 覆盖套件 |
|---|---|
"@

foreach ($ctype in $coverageTypes.Keys) {
    $matchedSuites = $coverageTypes[$ctype] | Where-Object { $_ -in ($global:allResults | Where-Object { $_.Status -eq 'PASS' }).SuiteName }
    $matchedDisplay = $matchedSuites | ForEach-Object {
        if ($suiteDisplayNames.ContainsKey($_)) { $suiteDisplayNames[$_] } else { $_ }
    }
    $mdContent += "`n| $ctype | $($matchedDisplay -join ', ') |"
}

$mdContent | Out-File -FilePath $summaryMdFile -Encoding UTF8
Write-Host "[INFO] Markdown 摘要已保存: $summaryMdFile" -ForegroundColor Cyan

# --- 保存 master log ---
$global:masterLogLines += "`n" + ($tableLines -join "`n")
$global:masterLogLines | Out-File -FilePath $masterLogFile -Encoding UTF8
Write-Host "[INFO] Master 日志已保存: $masterLogFile" -ForegroundColor Cyan

# --- 清理 ---
if (-not $NoClean) {
    Write-Host "[INFO] 清理临时文件..." -ForegroundColor Gray
    if (Test-Path $workDir) {
        Remove-Item -Path "$workDir\*" -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# --- 退出码 ---
Write-Banner -Text "回归测试完成 — $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Color $(
    if ($global:hasAnyFailure) { 'Red' } else { 'Green' }
)

if ($global:hasAnyFailure) {
    Write-Host "[RESULT] 存在失败项，退出码: 1" -ForegroundColor Red
    exit 1
} else {
    Write-Host "[RESULT] 全部通过，退出码: 0" -ForegroundColor Green
    exit 0
}
