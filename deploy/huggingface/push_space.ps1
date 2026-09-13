param(
    [Parameter(Mandatory = $true)][string]$Space,
    [switch]$Create
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$stage = Join-Path $env:TEMP ("identicare-space-" + [guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Force (Join-Path $stage "backend") | Out-Null
Copy-Item (Join-Path $PSScriptRoot "Dockerfile") $stage
Copy-Item (Join-Path $PSScriptRoot ".dockerignore") $stage
Copy-Item (Join-Path $PSScriptRoot "README.md") $stage
Copy-Item (Join-Path $root "backend\requirements.txt") (Join-Path $stage "backend")
Copy-Item (Join-Path $root "backend\ruff.toml") (Join-Path $stage "backend")
Copy-Item (Join-Path $root "backend\app") (Join-Path $stage "backend\app") -Recurse
Copy-Item (Join-Path $root "backend\scripts") (Join-Path $stage "backend\scripts") -Recurse
Get-ChildItem $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

if ($Create) {
    hf repo create $Space --repo-type space --space-sdk docker
}

hf upload $Space $stage . --repo-type space --commit-message "deploy identicare api"
Remove-Item $stage -Recurse -Force

Write-Host ""
Write-Host "Pushed. Build logs: https://huggingface.co/spaces/$Space"
Write-Host "Set secrets under Settings > Variables and secrets (see README.md), then:"
Write-Host "  flutter run --dart-define=API_BASE_URL=https://$($Space.Replace('/', '-').ToLower()).hf.space"
