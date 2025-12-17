# run.ps1
# Purpose: Activate the virtual environment and run the main Python script

$ErrorActionPreference = "Stop"

$venvPath = "venv"

# Check virtual environment existence
if (-not (Test-Path "$venvPath\Scripts\Activate.ps1")) {
    Write-Error "Virtual environment not found. Please run install.ps1 first."
    exit 1
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
. "$venvPath\Scripts\Activate.ps1"

# Optional: verify correct Python interpreter
Write-Host "Using Python interpreter:"
python --version

# Run the main script
if (-not (Test-Path ".\Operation_files\main_operation_file.py")) {
    Write-Error "main_operation_file.py not found."
    exit 1
}

Write-Host "Running main Python script..." -ForegroundColor Cyan
python .\Operation_files\main_operation_file.py

Write-Host "Execution completed." -ForegroundColor Green
