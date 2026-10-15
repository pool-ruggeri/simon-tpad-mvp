# Create and verify an isolated environment. Never installs system prerequisites.
[CmdletBinding()]
param(
    [string]$PythonExe,
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$previousNoUserSite = $env:PYTHONNOUSERSITE
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'A 64-bit Windows installation is required.'
    }
    $env:PYTHONNOUSERSITE = '1'
    $venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $checkPython = "import platform, struct, sys; assert platform.python_implementation() == 'CPython' and sys.version_info[:3] == (3, 11, 9) and struct.calcsize('P') == 8, 'Required: CPython 3.11.9, 64-bit'; print(sys.version)"

    if ($VerifyOnly) {
        if (-not (Test-Path -LiteralPath $venvPython)) {
            throw 'No .venv interpreter found. Run setup_windows.ps1 without -VerifyOnly first.'
        }
    } else {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv')) {
            throw 'An existing .venv was preserved. Use -VerifyOnly to check it; see docs/INSTALL_ON_NEW_PC.md for recovery.'
        }
        if ($PythonExe) {
            $basePython = $PythonExe
            $baseArguments = @()
        } else {
            $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
            if (-not $launcher) {
                throw 'Install CPython 3.11.9 x64 with its launcher, or pass -PythonExe C:\path\to\python.exe. Setup does not install Python.'
            }
            $basePython = $launcher.Source
            $baseArguments = @('-3.11-64')
        }
        & $basePython @baseArguments -c $checkPython
        if ($LASTEXITCODE -ne 0) { throw 'Required: CPython 3.11.9 x64. No environment was created.' }
        & $basePython @baseArguments -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check the interpreter, disk space and folder permissions.' }
    }

    & $venvPython -c $checkPython
    if ($LASTEXITCODE -ne 0) { throw 'The .venv interpreter does not match CPython 3.11.9 x64.' }
    & $venvPython -c "import sys; assert sys.prefix != sys.base_prefix, 'Not an isolated virtual environment'"
    if ($LASTEXITCODE -ne 0) { throw 'The interpreter is not an isolated virtual environment.' }

    if (-not $VerifyOnly) {
        & $venvPython -m pip install --disable-pip-version-check -r requirements-bootstrap.txt
        if ($LASTEXITCODE -ne 0) { throw 'Packaging-tool installation failed. Check network/index access; see the manual recovery commands.' }
        & $venvPython -m pip install --disable-pip-version-check -r requirements-lock.txt
        if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed. Keep the pip error above; see docs/INSTALL_ON_NEW_PC.md. No global packages were changed.' }
    }

    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency conflicts found. Do not use this environment for data collection.' }
    $verify = @'
import importlib.metadata as metadata
from pathlib import Path
for filename in ('requirements-bootstrap.txt', 'requirements-lock.txt'):
    for line in Path(filename).read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name, expected = line.strip().split('==')
        actual = metadata.version(name)
        if actual != expected:
            raise RuntimeError(f'{name}: expected {expected}, found {actual}')
import serial
from unittest.mock import patch
with patch('serial.Serial', side_effect=RuntimeError('Setup must not open hardware')):
    import run_simon, calibrate_opto, opto_diagnostic, tpad_serial, trial_logic
    calibrate_opto.load_psychopy()
print('Pinned packages and application/PsychoPy visual imports passed; no window or serial port opened.')
'@
    & $venvPython -c $verify
    if ($LASTEXITCODE -ne 0) { throw 'Version/import check failed. Check the exact pinned packages and Windows runtime/graphics prerequisites in the installation guide.' }
    foreach ($application in @('run_simon.py', 'calibrate_opto.py', 'opto_diagnostic.py')) {
        & $venvPython $application --help
        if ($LASTEXITCODE -ne 0) { throw "CLI startup failed: $application" }
    }
    & $venvPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed. Retain the output and resolve failures before laboratory use.' }
    Write-Host 'Software setup verified. No hardware was tested. Continue with docs/INSTALL_ON_NEW_PC.md.'
} catch {
    Write-Error -Message $_ -ErrorAction Continue
    exit 1
} finally {
    $env:PYTHONNOUSERSITE = $previousNoUserSite
    Pop-Location
}
