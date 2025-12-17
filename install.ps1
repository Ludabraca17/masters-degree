# install.ps1
# Purpose: Create a Python virtual environment and install dependencies

$ErrorActionPreference = "Stop"

Write-Host "Starting Python environment setup..." -ForegroundColor Cyan

# Check if Python is available
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not available in PATH."
    exit 1
}

# Create virtual environment
$venvPath = "venv"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment at $venvPath"
    python -m venv $venvPath
} else {
    Write-Host "Virtual environment already exists."
}

# Activate virtual environment
Write-Host "Activating virtual environment..."
. "$venvPath\Scripts\Activate.ps1"

# Upgrade pip (recommended for reproducibility)
python -m pip install --upgrade pip

# Install required packages
if (-not (Test-Path "requirements_libraries.txt")) {
    Write-Error "requirements_libraries.txt not found."
    exit 1
}

Write-Host "Installing Python packages..."
pip install -r requirements_libraries.txt

Write-Host "Environment setup completed successfully." -ForegroundColor Green
