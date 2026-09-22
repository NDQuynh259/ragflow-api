<#
.SYNOPSIS
    Automated testing and QA runner for RAG Platform.
.DESCRIPTION
    Runs pytest, test coverage, or full quality checks (lint + format + typecheck + test).
.PARAMETER CheckAll
    Runs full quality pipeline: lint, format:check, typecheck, and test.
.PARAMETER Coverage
    Runs pytest with code coverage analysis for core and chat-api.
.PARAMETER Match
    Filter expression for pytest (-k pattern).
#>
param(
    [switch]$CheckAll,
    [switch]$Coverage,
    [string]$Match = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Poe = Join-Path $RepoRoot ".venv\Scripts\poe.exe"
$Pytest = Join-Path $RepoRoot ".venv\Scripts\pytest.exe"

if ($CheckAll) {
    Write-Host "====================================================" -ForegroundColor Cyan
    Write-Host "  Running Full Production Quality Pipeline          " -ForegroundColor Cyan
    Write-Host "  (Lint -> Format Check -> Typecheck -> Test)       " -ForegroundColor Cyan
    Write-Host "====================================================" -ForegroundColor Cyan
    & $Poe check
    exit $LASTEXITCODE
}

if ($Coverage) {
    Write-Host "====================================================" -ForegroundColor Cyan
    Write-Host "  Running Test Suite with Code Coverage             " -ForegroundColor Cyan
    Write-Host "====================================================" -ForegroundColor Cyan
    & $Poe "test:cov"
    exit $LASTEXITCODE
}

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  Running Automated Pytest Suite                    " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

if ($Match -ne "") {
    & $Pytest -k $Match
} else {
    & $Pytest
}
exit $LASTEXITCODE
