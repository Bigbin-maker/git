param(
    [string]$MagicDrawHome = "E:\software\Catiamagic2022",
    [switch]$Install
)

$ErrorActionPreference = "Stop"

$PluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Join-Path $PluginRoot "src"
$BuildDir = Join-Path $PluginRoot "build"
$ClassesDir = Join-Path $BuildDir "classes"
$JarPath = Join-Path $BuildDir "ai-mbse-magicdraw-bridge.jar"
$EcjPath = Join-Path $BuildDir "tools\ecj.jar"
$JavaExe = Join-Path $MagicDrawHome "jre\bin\java.exe"
$InstallDir = Join-Path $MagicDrawHome "plugins\com.ai_mbse.magicdraw.bridge"

if (-not (Test-Path -LiteralPath $JavaExe)) {
    throw "MagicDraw java.exe not found: $JavaExe"
}
if (-not (Test-Path -LiteralPath $EcjPath)) {
    throw "ECJ compiler not found: $EcjPath"
}

New-Item -ItemType Directory -Force -Path $BuildDir, $ClassesDir | Out-Null
Remove-Item -LiteralPath $ClassesDir -Recurse -Force
New-Item -ItemType Directory -Force -Path $ClassesDir | Out-Null

$sources = Get-ChildItem -LiteralPath $SourceDir -Recurse -Filter "*.java" | ForEach-Object { $_.FullName }
if (-not $sources) {
    throw "No Java sources found under $SourceDir"
}

$classpath = (Get-ChildItem -LiteralPath (Join-Path $MagicDrawHome "lib") -Filter "*.jar" |
    ForEach-Object { $_.FullName }) -join [IO.Path]::PathSeparator

& $JavaExe -jar $EcjPath `
    -encoding UTF-8 `
    -source 1.8 `
    -target 1.8 `
    -cp $classpath `
    -d $ClassesDir `
    $sources

if ($LASTEXITCODE -ne 0) {
    throw "ECJ compilation failed with exit code $LASTEXITCODE"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (Test-Path -LiteralPath $JarPath) {
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    Copy-Item -LiteralPath $JarPath -Destination "$JarPath.bak-$stamp" -Force
    Remove-Item -LiteralPath $JarPath -Force
}

$zip = [System.IO.Compression.ZipFile]::Open($JarPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $base = (Resolve-Path -LiteralPath $ClassesDir).Path.TrimEnd("\") + "\"
    Get-ChildItem -LiteralPath $ClassesDir -Recurse -File | Sort-Object FullName | ForEach-Object {
        $entryName = $_.FullName.Substring($base.Length).Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip,
            $_.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $zip.Dispose()
}

$entries = [System.IO.Compression.ZipFile]::OpenRead($JarPath).Entries
try {
    $badEntry = $entries | Where-Object { $_.FullName.Contains("\") } | Select-Object -First 1
    if ($badEntry) {
        throw "Invalid JAR entry separator: $($badEntry.FullName)"
    }
    $mainClass = $entries | Where-Object { $_.FullName -eq "com/ai_mbse/magicdraw/bridge/AiMbseBridgePlugin.class" } | Select-Object -First 1
    if (-not $mainClass) {
        throw "Main plugin class is missing from JAR."
    }
}
finally {
    $entries[0].Archive.Dispose()
}

if ($Install) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    $installedJar = Join-Path $InstallDir "ai-mbse-magicdraw-bridge.jar"
    $installedXml = Join-Path $InstallDir "plugin.xml"
    if (Test-Path -LiteralPath $installedJar) {
        Copy-Item -LiteralPath $installedJar -Destination "$installedJar.bak-$stamp" -Force
    }
    if (Test-Path -LiteralPath $installedXml) {
        Copy-Item -LiteralPath $installedXml -Destination "$installedXml.bak-$stamp" -Force
    }
    Copy-Item -LiteralPath $JarPath -Destination $installedJar -Force
    Copy-Item -LiteralPath (Join-Path $PluginRoot "plugin.xml") -Destination $installedXml -Force
}

Write-Host "Bridge JAR built: $JarPath"
if ($Install) {
    Write-Host "Bridge plugin installed to: $InstallDir"
    Write-Host "Restart MagicDraw to reload the plugin."
}
