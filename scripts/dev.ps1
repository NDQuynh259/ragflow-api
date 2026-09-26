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
    Automatically starts the PostgreSQL pgvector and RabbitMQ containers if not running.
.PARAMETER Worker
    Starts the document ingestion worker instead of the Web API.
#>
param(
    [int]$Port = 8000,
    [string]$Hostname = "127.0.0.1",
    [switch]$WithDb,
    [switch]$Worker
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "====================================================" -ForegroundColor Cyan
if ($Worker) {
    Write-Host "  RAG Platform - Background Worker Startup          " -ForegroundColor Cyan
} else {
    Write-Host "  RAG Platform - Local Development Server Startup  " -ForegroundColor Cyan
}
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

# 3. Optional DB, RabbitMQ & MinIO Container Check
if ($WithDb) {
    Write-Host "[INFO] Starting PostgreSQL pgvector, RabbitMQ & MinIO containers..." -ForegroundColor Yellow
    $composeFile = Join-Path $RepoRoot "deploy\docker-compose.yml"
    docker compose -f $composeFile up -d postgres rabbitmq minio
    Write-Host "[INFO] RabbitMQ Web UI: http://localhost:15672 (user: guest / pass: guest)" -ForegroundColor Yellow
    Write-Host "[INFO] MinIO Web UI: http://localhost:9001 (user: minioadmin / pass: minioadmin)" -ForegroundColor Yellow
}

Set-Location $RepoRoot

# 4. Start Worker or API
if ($Worker) {
    Write-Host "[INFO] Starting Background Worker..." -ForegroundColor Green
    Write-Host "[INFO] Press Ctrl+C to stop the worker." -ForegroundColor Gray
    Write-Host "----------------------------------------------------" -ForegroundColor Gray
    $Poe = Join-Path $RepoRoot ".venv\Scripts\poe.exe"
    & $Poe worker
} else {
    Write-Host "[INFO] Starting Chat API on http://${Hostname}:${Port}..." -ForegroundColor Green
    Write-Host "[INFO] Swagger Docs: http://${Hostname}:${Port}/docs" -ForegroundColor Green
    Write-Host "[INFO] Press Ctrl+C to stop the server." -ForegroundColor Gray
    Write-Host "----------------------------------------------------" -ForegroundColor Gray
    $Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $DevScript = Join-Path $RepoRoot "scripts\dev.py"
    & $Python $DevScript $Port
}
