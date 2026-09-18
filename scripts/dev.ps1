<#
.SYNOPSIS
    Development runner script for RAG Platform.
.DESCRIPTION
    Ensures environment readiness (venv, .env, database) and starts the FastAPI server with live reload.
.PARAMETER Port
    Port number for the API server (default: 8000).
.PARAMETER Hostname
    Host binding for the server (default: 127.0.0.1).
.PARAMETER WithDb
    Automatically starts the PostgreSQL pgvector container if not running.
#>
param(
    [int]$Port = 8000,
    [string]$Hostname = "127.0.0.1",
    [switch]$WithDb
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  RAG Platform - Local Development Server Startup  " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Check & Copy .env if missing
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "[INFO] Created .env from .env.example" -ForegroundColor Yellow
    }
}

# 2. Check Virtual Environment
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[INFO] Virtual environment not found. Initializing with uv sync..." -ForegroundColor Yellow
    Set-Location $RepoRoot
    uv sync
}

# 3. Optional DB Container Check
if ($WithDb) {
    Write-Host "[INFO] Checking PostgreSQL pgvector container..." -ForegroundColor Yellow
    $composeFile = Join-Path $RepoRoot "deploy\docker-compose.yml"
    docker compose -f $composeFile up -d postgres
}

# 4. Start Development Server
Write-Host "[INFO] Starting Chat API on http://${Hostname}:${Port}..." -ForegroundColor Green
Write-Host "[INFO] Swagger Docs: http://${Hostname}:${Port}/docs" -ForegroundColor Green
Write-Host "[INFO] Press Ctrl+C to stop the server." -ForegroundColor Gray
Write-Host "----------------------------------------------------" -ForegroundColor Gray

Set-Location $RepoRoot
$Uvicorn = Join-Path $RepoRoot ".venv\Scripts\uvicorn.exe"
& $Uvicorn "chat_api.main:app" --reload --host $Hostname --port $Port
