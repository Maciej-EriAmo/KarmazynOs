# Faza 2: buduje holo_hsl.ko na jądrze virt (to samo, które wstaje na płycie).
# Wynik: out/hsl-build/holo_hsl.ko hsl-check init-hsl
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Cache = Join-Path $env:LOCALAPPDATA "KarmazynOs"
New-Item -ItemType Directory -Force -Path $Cache | Out-Null
$vmlinuz = Join-Path $Cache "vmlinuz-virt-6.18.57"
$kApk = Join-Path $Cache "linux-virt.apk"
$bbApk = Join-Path $Cache "busybox-static.apk"
$bbUrl = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/main/x86_64/busybox-static-1.37.0-r31.apk"
if (-not (Test-Path $kApk) -or (Get-Item $kApk).Length -lt 1000000) {
  Write-Host "GET linux-virt"
  curl.exe -fL --retry 2 -o $kApk "https://dl-cdn.alpinelinux.org/alpine/latest-stable/main/x86_64/linux-virt-6.18.57-r0.apk"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
python -c @"
import tarfile
from pathlib import Path
t = tarfile.open(r'$kApk', 'r:gz')
m = t.getmember('boot/vmlinuz-virt')
Path(r'$vmlinuz').write_bytes(t.extractfile(m).read())
print('vmlinuz', Path(r'$vmlinuz').stat().st_size)
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path $bbApk)) {
  curl.exe -fL --retry 2 -o $bbApk $bbUrl
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$work = Join-Path $Repo "out\hsl-guest"
$share = Join-Path $Repo "out\hsl-build"
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work, "$work\bin", "$work\src", "$work\etc", "$work\proc", "$work\sys", "$work\dev", "$work\new", "$work\host", $share | Out-Null
python -c @"
import tarfile
from pathlib import Path
apk = Path(r'$bbApk')
dest = Path(r'$work') / 'bin' / 'busybox'
tf = tarfile.open(apk, 'r:gz')
member = next(m for m in tf.getmembers() if m.name.replace('\\','/').endswith('bin/busybox.static') and m.isfile())
data = tf.extractfile(member).read()
dest.write_bytes(data)
print('busybox', len(data))
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -c @"
import gzip, tarfile
from pathlib import Path
apk = Path(r'$kApk')
dest = Path(r'$work') / 'e1000.ko'
tf = tarfile.open(apk, 'r:gz')
member = next(m for m in tf.getmembers() if m.name.replace('\\','/').endswith('drivers/net/ethernet/intel/e1000/e1000.ko.gz'))
data = gzip.decompress(tf.extractfile(member).read())
if data[:4] != bytes([127, 69, 76, 70]):
    raise SystemExit('e1000 not elf')
dest.write_bytes(data)
print('e1000', len(data))
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$rootTar = Join-Path $Cache "alpine-minirootfs-3.24.2-x86_64.tar.gz"
$rootUrl = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/alpine-minirootfs-3.24.2-x86_64.tar.gz"
if (-not (Test-Path $rootTar) -or (Get-Item $rootTar).Length -lt 1000000) {
  Write-Host "GET minirootfs"
  curl.exe -fL --retry 2 -o $rootTar $rootUrl
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Copy-Item $rootTar (Join-Path $work "minirootfs.tar.gz")
Copy-Item (Join-Path $Repo "boot\linux\outer-init.sh") (Join-Path $work "init")
Copy-Item (Join-Path $Repo "boot\linux\udhcpc.sh") (Join-Path $work "udhcpc.sh")
Copy-Item (Join-Path $Repo "holo\holo_hsl.c") (Join-Path $work "src\holo_hsl.c")
Copy-Item (Join-Path $Repo "holo\Makefile") (Join-Path $work "src\Makefile")
Copy-Item (Join-Path $Repo "boot\linux\hsl-check.c") (Join-Path $work "src\hsl-check.c")
Copy-Item (Join-Path $Repo "boot\linux\init.c") (Join-Path $work "src\init.c")
Copy-Item (Join-Path $Repo "boot\linux\build-init.sh") (Join-Path $work "src\build-init.sh")
$cpio = Join-Path $Repo "out\hsl-guest.cpio"
python (Join-Path $Repo "scripts\pack_tree_cpio.py") $work $cpio
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$qemu = $env:QEMU_BIN
if (-not $qemu) { $qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe" }
if (-not (Test-Path $qemu)) { Write-Host "Brak qemu"; exit 2 }
$log = Join-Path $env:TEMP "karmazyn_hsl_build.log"
$err = Join-Path $env:TEMP "karmazyn_hsl_build.err"
if (Test-Path $log) { Remove-Item $log -Force }
$qargs = "-machine pc,accel=tcg -m 5120 -kernel `"$vmlinuz`" -initrd `"$cpio`" -append `"console=ttyS0,115200 rdinit=/init`" -netdev user,id=n0 -device e1000,netdev=n0 -display none -vga none -no-reboot -serial `"file:$log`""
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $qemu
$psi.Arguments = $qargs
$psi.UseShellExecute = $false
$psi.RedirectStandardError = $true
$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
[void]$proc.Start()
$errTask = $proc.StandardError.ReadToEndAsync()
$deadline = (Get-Date).AddMinutes(25)
$ok = $false
while ((Get-Date) -lt $deadline) {
  if ($proc.HasExited) { break }
  if (Test-Path (Join-Path $share "holo_hsl.ko")) { $ok = $true; break }
  Start-Sleep -Seconds 5
}
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
Start-Sleep -Seconds 1
function Read-Shared([string]$path) {
  if (-not (Test-Path $path)) { return "" }
  $fs = [IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
  $sr = New-Object IO.StreamReader($fs)
  $t = $sr.ReadToEnd()
  $sr.Close()
  return $t
}
$text = Read-Shared $log
if ($text -notmatch "HSL_BUILD_OK" -and -not $ok) {
  Write-Host $text.Substring([Math]::Max(0, $text.Length - 4000))
  Write-Host "HSL BUILD FAIL"
  exit 1
}
if (-not (Test-Path (Join-Path $share "holo_hsl.ko"))) {
  python -c @"
import base64, pathlib
text = pathlib.Path(r'$log').read_bytes().decode('latin1', 'replace').replace('\r', '')
out = pathlib.Path(r'$share')
lines = text.split('\n')
found = {}
i = 0
while i < len(lines):
    line = lines[i].strip()
    if line.startswith('BEGIN '):
        name = line[6:].strip()
        i += 1
        buf = []
        end = 'END ' + name
        while i < len(lines) and lines[i].strip() != end:
            s = lines[i].strip()
            if s and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in s):
                buf.append(s)
            i += 1
        data = base64.b64decode(''.join(buf))
        if data[:4] != bytes([127, 69, 76, 70]):
            raise SystemExit('not elf ' + name)
        (out / name).write_bytes(data)
        found[name] = len(data)
        print(name, len(data))
    i += 1
for name in ('holo_hsl.ko', 'hsl-check', 'init-hsl'):
    if name not in found:
        raise SystemExit('brak ' + name)
"@
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Get-ChildItem $share | Select-Object Name, Length
Write-Host "HSL MODULE OK"
