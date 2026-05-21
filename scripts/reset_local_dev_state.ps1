[CmdletBinding()]
param(
    [switch]$RemoveCreatives,
    [switch]$SkipDocker,
    [switch]$SkipStorage,
    [switch]$SkipVectorStore,
    [switch]$SkipLogs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$storageRoot = Join-Path $repoRoot "storage"
$vectorStoreRoot = Join-Path $repoRoot "vector_store"
$logRoot = Join-Path $repoRoot "log"

function Assert-InRepo([string]$PathToCheck) {
    $resolvedRepo = [System.IO.Path]::GetFullPath($repoRoot)
    $resolvedPath = [System.IO.Path]::GetFullPath($PathToCheck)
    if (-not $resolvedPath.StartsWith($resolvedRepo, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to touch path outside repo: $resolvedPath"
    }
}

function Clear-DirectoryChildren {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [string[]]$ExcludeNames = @()
    )

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        return
    }

    Assert-InRepo $TargetPath

    Get-ChildItem -LiteralPath $TargetPath -Force | ForEach-Object {
        if ($ExcludeNames -contains $_.Name) {
            Write-Host "Keeping $($_.FullName)"
            return
        }
        Assert-InRepo $_.FullName
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
        Write-Host "Removed $($_.FullName)"
    }
}

Write-Host "Resetting local Violyt dev state under $repoRoot"

if (-not $SkipDocker) {
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCommand) {
        Write-Host "Stopping Docker compose services and removing compose volumes..."
        & $dockerCommand.Source compose down -v --remove-orphans
    }
    else {
        Write-Warning "Docker is not available on PATH here. Compose containers/volumes were not reset."
    }
}

if (-not $SkipStorage) {
    $excludeNames = @()
    if (-not $RemoveCreatives) {
        $excludeNames += "Creatives"
    }
    Write-Host "Clearing storage directory..."
    Clear-DirectoryChildren -TargetPath $storageRoot -ExcludeNames $excludeNames
}

if (-not $SkipVectorStore) {
    Write-Host "Clearing vector store directory..."
    Clear-DirectoryChildren -TargetPath $vectorStoreRoot
}

if (-not $SkipLogs) {
    Write-Host "Clearing log directory..."
    Clear-DirectoryChildren -TargetPath $logRoot
}

foreach ($path in @($storageRoot, $vectorStoreRoot)) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
        Write-Host "Created $path"
    }
}

Write-Host ""
Write-Host "Local state reset complete."
Write-Host "Next step: docker compose up --build api worker frontend postgres"
