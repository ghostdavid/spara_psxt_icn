$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$count = 0
function Get-ProjectFiles([string]$Directory) {
    foreach ($item in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        if ($item.PSIsContainer) { Get-ProjectFiles $item.FullName }
        else { $item }
    }
}
foreach ($file in Get-ProjectFiles $root) {
    $streams = @(Get-Item -LiteralPath $file.FullName -Stream * -ErrorAction Stop)
    if ($streams.Stream -contains 'Zone.Identifier') {
        Write-Output $file.FullName
        $count++
    }
}
if ($count -gt 0) {
    Write-Error "Found $count Zone.Identifier streams. Verify file provenance and explicitly unblock trusted files before building."
    exit 1
}
Write-Output 'Zone.Identifier count: 0'
