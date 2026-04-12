Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

git config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Failed to set git hooks path."
}

Write-Host "Git hooks installed: core.hooksPath=.githooks"
