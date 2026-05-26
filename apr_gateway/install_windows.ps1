param(
    [string]$PythonPath = "",
    [switch]$WithMl
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-Python {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (Test-Path $ExplicitPath) {
            return (Resolve-Path $ExplicitPath).Path
        }
        throw "PythonPath does not exist: $ExplicitPath"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $probe = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $probe) {
            return $probe.Trim()
        }
    }

    throw "Python is not installed or is not visible on PATH. Install Python 3.11+ first, or rerun with -PythonPath C:\Path\to\python.exe."
}

$Python = Resolve-Python $PythonPath
$Venv = Join-Path $Root ".venv"

Write-Host "Using Python: $Python"
& $Python -m venv $Venv

$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")

if ($WithMl) {
    & $VenvPython -m pip install -r (Join-Path $Root "requirements-ml.txt")
}

Write-Host "Install complete."
Write-Host "Run: .\run_gateway.ps1"
