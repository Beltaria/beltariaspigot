# Republishes beltariaspigot-api from the local BeltariaSpigot checkout into this
# repository. Run from anywhere; paths resolve relative to this script.
param(
    [string]$PandaSpigot = (Join-Path $PSScriptRoot '..\pandaspigot')
)

$ErrorActionPreference = 'Stop'

Push-Location $PandaSpigot
try {
    & .\gradlew.bat :beltariaspigot-api:publishToMavenLocal
    if ($LASTEXITCODE -ne 0) { throw "publishToMavenLocal failed" }
} finally {
    Pop-Location
}

$source = Join-Path $env:USERPROFILE '.m2\repository\net\beltaria'
$target = Join-Path $PSScriptRoot 'net\beltaria'

if (Test-Path $target) { Remove-Item -Recurse -Force $target }
New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
Copy-Item -Recurse $source $target

# mavenLocal writes maven-metadata-local.xml; remote resolvers expect maven-metadata.xml
Get-ChildItem -Recurse $target -Filter 'maven-metadata-local.xml' | ForEach-Object {
    Rename-Item $_.FullName 'maven-metadata.xml'
}

git -C $PSScriptRoot add -A
git -C $PSScriptRoot commit -m "Publish beltariaspigot-api"
git -C $PSScriptRoot push

Write-Host 'Published. raw.githubusercontent.com may take ~5 minutes to serve the new files.'
