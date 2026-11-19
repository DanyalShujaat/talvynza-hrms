param([int]$ApiPort = 8010, [int]$WebPort = 5180)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'apps/api/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Install the API dependencies first. See README.md.' }
& $pythonPath (Join-Path $PSScriptRoot 'run_demo.py') --api-port $ApiPort --web-port $WebPort
exit $LASTEXITCODE
