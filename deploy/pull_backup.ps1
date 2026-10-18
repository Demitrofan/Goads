# Забирает свежую копию базы с сервера к себе (раз в неделю, задача Windows «GOA rent - копия базы»).
# Хранит 8 последних копий в _backups\ (папка не в git).
$ErrorActionPreference = 'Stop'
$dir = Join-Path $PSScriptRoot '..\_backups'
New-Item -ItemType Directory -Force $dir | Out-Null
$name = 'db_rielt-' + (Get-Date -Format 'yyyy-MM-dd') + '.db.gz'
$dest = Join-Path $dir $name
& scp -q -o BatchMode=yes 'goads:/srv/goads/backups/latest.db.gz' $dest
if ($LASTEXITCODE -ne 0) { throw "scp failed: $LASTEXITCODE" }
if ((Get-Item $dest).Length -lt 1MB) { throw "backup too small: $dest" }
Get-ChildItem $dir -Filter 'db_rielt-*.db.gz' | Sort-Object Name -Descending |
    Select-Object -Skip 8 | Remove-Item -Force
Add-Content (Join-Path $dir 'pull.log') ("{0} ok {1}" -f (Get-Date -Format s), $name)
