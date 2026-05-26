param(
    [string]$EnvFile = ".env",
    [string]$PythonPath = ""
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

    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        return $VenvPython
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

    throw "Python is not installed or dependencies are not installed. Run .\install_windows.ps1 after installing Python 3.11+."
}

function Import-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
}

$EnvPath = Join-Path $Root $EnvFile
Import-EnvFile $EnvPath

$Python = Resolve-Python $PythonPath
Write-Host "Starting APR Gateway with Python: $Python"
Set-Location $Root

$ExtraPythonPaths = @($Root)
$LocalPackages = Join-Path $Root ".python_packages"
if (Test-Path $LocalPackages) {
    $ExtraPythonPaths += $LocalPackages
}
$ParentSitePackages = Join-Path (Split-Path -Parent $Root) "Lib\site-packages"
if (Test-Path $ParentSitePackages) {
    $ExtraPythonPaths += $ParentSitePackages
}
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = ($ExtraPythonPaths + $env:PYTHONPATH) -join ";"
} else {
    $env:PYTHONPATH = $ExtraPythonPaths -join ";"
}

& $Python app.py
