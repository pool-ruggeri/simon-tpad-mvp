# Forward arguments to the existing application in this repository's .venv.
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Run setup_windows.ps1 first; see docs/INSTALL_ON_NEW_PC.md.'
}
& $taskPython (Join-Path $PSScriptRoot 'opto_diagnostic.py') @args
exit $LASTEXITCODE
