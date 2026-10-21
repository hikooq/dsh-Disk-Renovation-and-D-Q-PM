<#
.SYNOPSIS
    批量为 Windows 快捷方式(.lnk)换图标，并支持备份 / 还原 / 体检。
    配套技能：windows-icon-maker

.DESCRIPTION
    只改 .lnk 的 IconLocation，绝不触碰启动目标（TargetPath / Arguments / WorkingDirectory），
    并且在改动前自动把原始信息写成 JSON 备份，出问题一条命令还原。

    默认在【用户桌面 + 公共桌面 + 用户开始菜单 + 公共开始菜单】四处搜索，
    避免出现"桌面换了、开始菜单还是老图标"这种不一致。

.PARAMETER Icon
    要应用的 .ico 路径（可以不带 ",0"，脚本会自己补）。

.PARAMETER Name
    快捷方式名字（模糊匹配，不含 .lnk）。可传多个。

.PARAMETER LnkPath
    直接指定 .lnk 的完整路径，绕过名字搜索。

.PARAMETER DryRun
    只体检不动手：列出命中的快捷方式、当前图标、将要变成什么。

.PARAMETER Restore
    指向之前的备份 JSON，把 IconLocation 还原回去。

.PARAMETER List
    列出所有能找到的快捷方式及其当前图标（排查"两边不一致"用）。

.EXAMPLE
    # 先看一眼会命中哪些
    .\apply_icon.ps1 -Icon D:\Apps\icons\whale-round.ico -Name "DSH Desktop" -DryRun

.EXAMPLE
    # 真正替换（桌面 + 开始菜单同名的一起换）
    .\apply_icon.ps1 -Icon D:\Apps\icons\whale-round.ico -Name "DSH Desktop"

.EXAMPLE
    # 还原
    .\apply_icon.ps1 -Restore D:\Apps\icons\lnk-backup-20261021-192120.json

.EXAMPLE
    # 体检：我现在到底有几个快捷方式、各自用的什么图标
    .\apply_icon.ps1 -List
#>
[CmdletBinding(DefaultParameterSetName = 'Apply')]
param(
    [Parameter(ParameterSetName = 'Apply', Mandatory = $true, Position = 0)]
    [string]$Icon,

    [Parameter(ParameterSetName = 'Apply')]
    [string[]]$Name,

    [Parameter(ParameterSetName = 'Apply')]
    [string[]]$LnkPath,

    [Parameter(ParameterSetName = 'Apply')]
    [switch]$DryRun,

    [Parameter(ParameterSetName = 'Apply')]
    [switch]$NoRefresh,

    [Parameter(ParameterSetName = 'Restore', Mandatory = $true)]
    [string]$Restore,

    [Parameter(ParameterSetName = 'List')]
    [switch]$List,

    [string]$BackupDir = 'D:\Apps\icons'
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ws = New-Object -ComObject WScript.Shell

# ---------------------------------------------------------------- 工具函数
function Get-SearchRoots {
    $roots = @()
    foreach ($k in 'Desktop', 'CommonDesktopDirectory', 'Programs') {
        try {
            $p = [Environment]::GetFolderPath($k)
            if ($p) { $roots += $p }
        } catch { }
    }
    $roots += Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'
    $roots | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
}

function Find-Shortcuts {
    param([string[]]$NamePattern, [string[]]$Explicit)
    if ($Explicit) {
        return $Explicit | Where-Object { Test-Path -LiteralPath $_ } |
            ForEach-Object { Get-Item -LiteralPath $_ }
    }
    $all = @()
    foreach ($root in (Get-SearchRoots)) {
        $all += Get-ChildItem -LiteralPath $root -Filter '*.lnk' -Recurse `
            -ErrorAction SilentlyContinue -File
    }
    $all = $all | Sort-Object FullName -Unique
    if (-not $NamePattern) { return $all }
    $all | Where-Object {
        $base = $_.BaseName
        ($NamePattern | Where-Object { $base -like "*$_*" }).Count -gt 0
    }
}

function Read-LnkInfo {
    param([string]$Path)
    $sc = $ws.CreateShortcut($Path)
    [pscustomobject]@{
        Lnk     = $Path
        Name    = [IO.Path]::GetFileNameWithoutExtension($Path)
        Target  = $sc.TargetPath
        Args    = $sc.Arguments
        Icon    = $sc.IconLocation
        WorkDir = $sc.WorkingDirectory
    }
}

function Write-BackupFile {
    param($Records, [string]$Dir)
    if (-not (Test-Path -LiteralPath $Dir)) {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $path = Join-Path $Dir "lnk-backup-$stamp.json"
    $i = 1
    while (Test-Path -LiteralPath $path) {          # 绝不覆盖历史备份
        $path = Join-Path $Dir "lnk-backup-$stamp-$i.json"
        $i++
    }
    $Records | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $path -Encoding utf8
    return $path
}

function Invoke-IconRefresh {
    try {
        Start-Process -FilePath 'ie4uinit.exe' -ArgumentList '-show' -NoNewWindow -Wait -ErrorAction SilentlyContinue
    } catch { }
}

# ---------------------------------------------------------------- List 模式
if ($List) {
    $rows = @(Find-Shortcuts -NamePattern $null -Explicit $null | ForEach-Object {
            Read-LnkInfo -Path $_.FullName
        })
    $rows | ForEach-Object {
        # 注意：hashtable 字面量的值不能用 if 表达式（PowerShell 5.1 会语法错误），先算好
        $iconText = if ($_.Icon) { $_.Icon } else { '(默认/程序自带)' }
        [pscustomobject]@{
            Name   = $_.Name
            Icon   = $iconText
            Target = $_.Target
            Lnk    = $_.Lnk
        }
    } | Format-Table -AutoSize -Wrap
    "共 $($rows.Count) 个快捷方式"
    return
}

# ---------------------------------------------------------------- Restore 模式
if ($Restore) {
    if (-not (Test-Path -LiteralPath $Restore)) {
        throw "备份文件不存在：$Restore"
    }
    $records = Get-Content -LiteralPath $Restore -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $records) { throw "备份文件是空的：$Restore" }
    $restored = @()
    foreach ($r in @($records)) {
        if (-not (Test-Path -LiteralPath $r.Lnk)) {
            $restored += [pscustomobject]@{ Lnk = $r.Lnk; ok = $false; reason = '快捷方式已不存在' }
            continue
        }
        try {
            $sc = $ws.CreateShortcut($r.Lnk)
            $sc.IconLocation = [string]$r.Icon          # 空字符串 = 回到默认图标
            $sc.Save()
            $restored += [pscustomobject]@{ Lnk = $r.Lnk; ok = $true; icon = $sc.IconLocation }
        } catch {
            $restored += [pscustomobject]@{ Lnk = $r.Lnk; ok = $false; reason = $_.Exception.Message }
        }
    }
    if (-not $NoRefresh) { Invoke-IconRefresh }
    [pscustomobject]@{ mode = 'restore'; backup = $Restore; results = $restored } |
        ConvertTo-Json -Depth 5
    return
}

# ---------------------------------------------------------------- Apply 模式
if (-not (Test-Path -LiteralPath $Icon)) {
    throw "图标文件不存在：$Icon"
}
if ([IO.Path]::GetExtension($Icon).ToLower() -ne '.ico') {
    Write-Warning "传入的不是 .ico（$Icon）。Windows 的 IconLocation 只认 .ico / .exe / .dll。"
}

# IconLocation 的正确写法是 "路径,索引"；把 ,0 交给脚本补，免得漏掉
$iconValue = $Icon
if ($iconValue -notmatch ',\s*-?\d+$') { $iconValue = "$Icon,0" }

$targets = @(Find-Shortcuts -NamePattern $Name -Explicit $LnkPath)
if ($targets.Count -eq 0) {
    [pscustomobject]@{
        mode    = 'apply'
        ok      = $false
        reason  = '没有命中任何快捷方式'
        searched = @(Get-SearchRoots)
    } | ConvertTo-Json -Depth 5
    exit 2
}

$records = @($targets | ForEach-Object { Read-LnkInfo -Path $_.FullName })

# 只有真要动手时才写备份 —— 预演模式不该在磁盘上留垃圾
$backupPath = $null
if (-not $DryRun) {
    $backupPath = Write-BackupFile -Records $records -Dir $BackupDir
}

$changes = @()
foreach ($r in $records) {
    $before = $r.Icon
    $beforeText = if ($before) { $before } else { '(默认)' }
    if ($DryRun) {
        $changes += [pscustomobject]@{
            Name       = $r.Name
            Lnk        = $r.Lnk
            IconBefore = $beforeText
            IconAfter  = $iconValue
            applied    = $false
            dryRun     = $true
        }
        continue
    }
    try {
        $sc = $ws.CreateShortcut($r.Lnk)
        $sc.IconLocation = $iconValue
        $sc.Save()

        # 立刻回读，确认图标改了、而启动目标一个字都没动
        $check = Read-LnkInfo -Path $r.Lnk
        $targetIntact = ($check.Target -eq $r.Target)
        $changes += [pscustomobject]@{
            Name         = $r.Name
            Lnk          = $r.Lnk
            IconBefore   = $beforeText
            IconAfter    = $check.Icon
            targetIntact = $targetIntact
            applied      = ($check.Icon -eq $iconValue)
        }
        if (-not $targetIntact) {
            Write-Warning "启动目标发生变化：$($r.Lnk)"
        }
    } catch {
        $changes += [pscustomobject]@{
            Name    = $r.Name
            Lnk     = $r.Lnk
            applied = $false
            error   = $_.Exception.Message
        }
    }
}

if (-not $DryRun -and -not $NoRefresh) { Invoke-IconRefresh }

$hintText = if ($DryRun) {
    '这是预演，没有真的改。去掉 -DryRun 才会写入。'
} else {
    '若桌面没变：按 F5，或重启 explorer.exe。还原用 -Restore <备份json>。'
}

# 预演模式的 ok 表示"预演本身跑通了"，不代表已经替换成功
$okValue = if ($DryRun) {
    $true
} else {
    (@($changes | Where-Object { $_.applied }).Count -eq $changes.Count)
}

[pscustomobject]@{
    mode         = 'apply'
    ok           = $okValue
    icon         = $iconValue
    backup       = $backupPath
    dryRun       = [bool]$DryRun
    count        = $changes.Count
    changes      = $changes
    hint         = $hintText
} | ConvertTo-Json -Depth 6
