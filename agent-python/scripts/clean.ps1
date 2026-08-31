# 清除 agent-python 下的临时文件与编译产物（不默认删除 .venv）
param(
    [switch]$Venv,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if ($Help) {
    @"
Usage: scripts\clean.ps1 [options]

Options:
  -Venv      同时删除 .venv 虚拟环境
  -DryRun    只打印将删除的内容，不实际删除
  -Help      显示帮助
"@
    exit 0
}

function Remove-Target {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if ($DryRun) {
        Write-Host "would remove: $Path"
    } else {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "removed: $Path"
    }
}

Write-Host "Cleaning agent-python at: $Root"

$topLevel = @(
    "dist", "build", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "htmlcov", ".coverage", "tmp", "tmp_wheel", "tmp_extract"
)
foreach ($name in $topLevel) {
    Remove-Target (Join-Path $Root $name)
}

Get-ChildItem -Path $Root -Filter "*.egg-info" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Target $_.FullName }
Get-ChildItem -Path (Join-Path $Root "src") -Filter "*.egg-info" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Target $_.FullName }

$excludeVenv = if ($Venv) { @() } else { @((Join-Path $Root ".venv")) }

Get-ChildItem -Path $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $p = $_.FullName; -not ($excludeVenv | Where-Object { $p.StartsWith($_) }) } |
    ForEach-Object { Remove-Target $_.FullName }

foreach ($pattern in @("*.pyc", "*.pyo")) {
    Get-ChildItem -Path $Root -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue |
        Where-Object { $p = $_.FullName; -not ($excludeVenv | Where-Object { $p.StartsWith($_) }) } |
        ForEach-Object { Remove-Target $_.FullName }
}

if (-not $DryRun) {
    Write-Host "removed: __pycache__ / *.pyc / *.pyo (excluding .venv unless -Venv)"
}

if ($Venv) {
    Remove-Target (Join-Path $Root ".venv")
} else {
    Write-Host "skipped: .venv (use -Venv to remove)"
}

Write-Host "Done."
