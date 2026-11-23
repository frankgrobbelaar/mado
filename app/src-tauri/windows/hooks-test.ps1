# Checks Mado's install hooks (hooks.nsh): an update replaces the engine whole, a stopped install
# puts the old one back, and a running engine is dealt with; and the uninstall hook takes away File
# Explorer's "Open in Mado" and Open with (only Mado's keys, kept through an update). Builds
# hooks-test.nsi with the NSIS that `pnpm build:installer` downloads, installs into
# app/src-tauri/target/hooks-test, and keeps the registry's part in a root of its own,
# HKCU\Software\Mado hooks test, compared with `reg query` before and after.
# Run it after changing hooks.nsh or upgrading Tauri: powershell -File windows/hooks-test.ps1
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$makensis = Join-Path $env:LOCALAPPDATA 'tauri\NSIS\makensis.exe'
if (-not (Test-Path $makensis)) { throw "No NSIS at ${makensis}; run pnpm build:installer once first." }
$work = Join-Path (Split-Path $here) 'target\hooks-test'
$inst = Join-Path $work 'inst'
$failed = 0

function Build([string]$name, [switch]$Stop, [switch]$Explorer, [switch]$Updating) {
    $out = Join-Path $work "$name.exe"
    $arguments = @('/V2', "/DHOOKS=$here\hooks.nsh", "/DOUT=$out", "/DDIR=$inst")
    if ($Stop) { $arguments += '/DSTOP' }
    if ($Explorer) { $arguments += '/DEXPLORER' }
    if ($Updating) { $arguments += '/DUPDATING' }
    $arguments += (Join-Path $here 'hooks-test.nsi')
    $said = & $makensis @arguments 2>&1
    if ($LASTEXITCODE -ne 0) { $said | Out-Host; throw "makensis couldn't build $name" }
    $out
}

function Old-Engine {
    if (Test-Path $inst) { Remove-Item $inst -Recurse -Force }
    foreach ($version in '0.1.0', '0.2.0') {
        $record = "$inst\engine\_internal\mado-$version.dist-info"
        New-Item -ItemType Directory -Force $record | Out-Null
        Set-Content "$record\METADATA" "Version: $version"
    }
    # A program to stand in for a running engine.
    Copy-Item "$env:WINDIR\System32\PING.EXE" "$inst\engine\mado-engine.exe"
}

function Install([string]$exe) { (Start-Process $exe -Wait -PassThru).ExitCode }

function Listing {
    if (-not (Test-Path $inst)) { return '' }
    (Get-ChildItem $inst -Recurse -Name | ForEach-Object { $_ -replace '\\', '/' } | Sort-Object) -join ' | '
}

function Expect([string]$case, [string]$got, [string]$want) {
    if ($got -eq $want) { "PASS $case" }
    else { "FAIL $case`n  got:  $got`n  want: $want"; $script:failed++ }
}

# The registry's part: a root of classes of the test's own, never the owner's.
$root = 'HKCU:\Software\Mado hooks test'
$classes = "$root\Classes"
$exe = 'C:\Users\owner\AppData\Local\Programs\Mado\mado.exe'

function Fresh-Root {
    if (Test-Path $root) { Remove-Item $root -Recurse -Force }
    New-Item $classes -Force | Out-Null
}

function Key([string]$path, [hashtable]$values = @{}) {
    $key = "$classes\$path"
    if (-not (Test-Path -LiteralPath $key)) { New-Item $key -Force | Out-Null }
    foreach ($name in $values.Keys) {
        New-ItemProperty -LiteralPath $key -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null
    }
}

# What other apps and Windows keep there already: a type's own default, other apps' Open with
# values, another app's verb, Windows' own verb on folders, and a type with only a default.
function Others {
    Key '.jpg' @{ '(default)' = 'jpegfile' }
    Key '.jpg\OpenWithProgids' @{ 'AppX43hnxtbyyps62jhe9sqpdzxn1790zetc' = '' }
    Key '.png' @{ '(default)' = 'pngfile' }
    Key 'SystemFileAssociations\.jpg\shell\edit\command' @{ '(default)' = '"C:\Paint\paint.exe" "%1"' }
    Key 'Directory\shell\find' @{ '(default)' = 'Search' }
}

# Mado's keys as the shell writes them (src/open_in_mado.rs), for a few types: an older Mado's
# .jxl among them.
function Mado-Keys {
    foreach ($type in '.jpg', '.png', '.heic', '.cr3', '.jxl') {
        Key "Applications\mado.exe\SupportedTypes" @{ $type = '' }
        Key "$type\OpenWithProgids" @{ 'Mado.Picture' = '' }
        Key "SystemFileAssociations\$type\shell\Mado.Open" @{ '(default)' = 'Open in Mado'; 'Icon' = "$exe,0"; 'MultiSelectModel' = 'Player' }
        Key "SystemFileAssociations\$type\shell\Mado.Open\command" @{ '(default)' = "`"$exe`" `"%1`"" }
    }
    Key 'Directory\shell\Mado.Open' @{ '(default)' = 'Open in Mado'; 'Icon' = "$exe,0"; 'MultiSelectModel' = 'Player' }
    Key 'Directory\shell\Mado.Open\command' @{ '(default)' = "`"$exe`" `"%1`"" }
    Key 'Applications\mado.exe' @{ 'FriendlyAppName' = 'Mado' }
    Key 'Applications\mado.exe\DefaultIcon' @{ '(default)' = "$exe,0" }
    Key 'Applications\mado.exe\shell\open\command' @{ '(default)' = "`"$exe`" `"%1`"" }
    Key 'Mado.Picture\DefaultIcon' @{ '(default)' = "$exe,0" }
    Key 'Mado.Picture\shell\open\command' @{ '(default)' = "`"$exe`" `"%1`"" }
}

# Everything under the root, as reg query lists it.
function Registry {
    ((reg query 'HKCU\Software\Mado hooks test' /s) | Where-Object { $_.Trim() }) -join "`n"
}

New-Item -ItemType Directory -Force $work | Out-Null
$install = Build 'install'
$stopping = Build 'stopping' -Stop
$uninstall = Build 'uninstall' -Explorer
$update = Build 'update' -Explorer -Updating
$new = 'engine | engine/_internal | engine/_internal/mado-0.3.0.dist-info | engine/_internal/mado-0.3.0.dist-info/METADATA | engine/new-engine.txt'
$old = 'engine | engine/_internal | engine/_internal/mado-0.1.0.dist-info | engine/_internal/mado-0.1.0.dist-info/METADATA | engine/_internal/mado-0.2.0.dist-info | engine/_internal/mado-0.2.0.dist-info/METADATA | engine/mado-engine.exe'

Old-Engine
$code = Install $install
Expect "an update replaces the engine whole (exit $code)" (Listing) $new

Remove-Item $inst -Recurse -Force
$code = Install $install
Expect "a first install (exit $code)" (Listing) $new

Old-Engine
New-Item -ItemType Directory -Force "$inst\engine-old\_internal" | Out-Null
Set-Content "$inst\engine-old\_internal\left.txt" 'left'
$code = Install $install
Expect "what an earlier install left goes first (exit $code)" (Listing) $new

Old-Engine
$code = Install $stopping
Expect "a stopped install puts the old engine back (exit $code)" (Listing) $old

Old-Engine
$running = Start-Process "$inst\engine\mado-engine.exe" -ArgumentList '-n', '30', '127.0.0.1' -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 500
$code = Install $install
Stop-Process -Id $running.Id -Force
$running.WaitForExit()
Expect "a running engine is set aside, keeping only what it holds (exit $code)" (Listing) "$new | engine-old | engine-old/mado-engine.exe"
$code = Install $install
Expect "the next install clears that (exit $code)" (Listing) $new

Old-Engine
$running = Start-Process "$inst\engine\mado-engine.exe" -ArgumentList '-n', '3', '127.0.0.1' -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 300
$code = Install $install
Expect "an engine stopping meanwhile is waited for (exit $code)" (Listing) $new

try {
    Fresh-Root
    Others
    $before = Registry
    Mado-Keys
    $code = Install $uninstall
    Expect "uninstalling takes away Mado's keys in File Explorer, and only them (exit $code)" (Registry) $before

    Fresh-Root
    Others
    Mado-Keys
    $written = Registry
    $code = Install $update
    Expect "an update keeps them (exit $code)" (Registry) $written

    Fresh-Root
    Others
    Key 'SystemFileAssociations\.tif' @{ 'Note' = 'kept' }
    Key 'SystemFileAssociations\.tif\shell'
    $before = Registry
    $code = Install $uninstall
    Expect "uninstalling before Mado wrote them changes nothing (exit $code)" (Registry) $before
}
finally {
    if (Test-Path $root) { Remove-Item $root -Recurse -Force }
}

Remove-Item $work -Recurse -Force
if ($failed) { throw "$failed failed" }
'All passed.'
