---
name: windows-disk-migration
description: Windows 磁盘空间治理与开发环境迁移。当用户抱怨 C 盘掉空间、要求「软件/下载/缓存全部装 D 盘」、要迁移 Git/Node/Python 等工具链、需要给命令行工具建桌面入口，或要求做磁盘体检找增长点时使用。包含可直接执行的命令、需要管理员权限时的绕行方案，以及一批踩过的坑。
---

# Windows 磁盘空间治理与开发环境迁移

把「以后都装 D 盘」从一句口头承诺，变成一台真正配好的机器。

## 何时用

- 用户说「C 盘又满了」「怎么掉了 5 个 G」
- 用户说「所有下载/软件/缓存都放 D 盘」
- 要迁移 Git、Node.js、Python、包管理器缓存
- 要给 git-bash / cmd 之类建桌面快捷方式
- 需要在不重装系统的前提下腾出空间

## 三条铁律

1. **先测量，再动手。** 没有数据就不知道搬什么划算。
2. **区分「程序」和「数据」。** 程序装在 `D:\Apps`，数据/缓存在 `D:\Cache`，用户文件在 `D:\下载`/`D:\文档`。
3. **不碰系统组件。** Windows 目录、驱动、Office、系统级 Microsoft 组件一律不迁移，收益远小于风险。

---

## 第 0 步：体检

```powershell
# 磁盘余量
Get-PSDrive C,D | Select-Object Name,
  @{n='已用GB';e={[math]::Round($_.Used/1GB,1)}},
  @{n='剩余GB';e={[math]::Round($_.Free/1GB,1)}},
  @{n='总计GB';e={[math]::Round(($_.Used+$_.Free)/1GB,1)}}
```

找**近两天增长最快**的目录（比总量排行更能定位「刚掉的空间」）：

```powershell
$cut = (Get-Date).AddDays(-2)
$roots = @("$env:APPDATA","$env:LOCALAPPDATA","C:\ProgramData")
foreach ($r in $roots) {
  Get-ChildItem -LiteralPath $r -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $sum = (Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTime -gt $cut } | Measure-Object Length -Sum).Sum
    if ($sum -gt 300MB) { [pscustomobject]@{ 路径 = $_.FullName; 近两日GB = [math]::Round($sum/1GB,2) } }
  }
} | Sort-Object 近两日GB -Descending
```

> 扫描整个 `C:\` 会跑很久。先从 `AppData` 和 `ProgramData` 入手，这两处通常是增长点。

查系统级大文件（休眠文件、页面文件）：

```powershell
foreach ($f in @("C:\hiberfil.sys","C:\pagefile.sys","C:\swapfile.sys")) {
  if (Test-Path -LiteralPath $f) { (Get-Item -LiteralPath $f -Force).Length / 1GB }
}
```

## 第 1 步：确认已迁移项，避免重复劳动

```powershell
$usf = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
Get-ItemProperty $usf | Select-Object "{374DE290-123F-4565-9164-39C4925E467B}", "Personal", "Desktop"
# {374DE290-...} 就是「下载」，Personal 是「文档」
```

检查工具链落在哪：

```powershell
foreach ($c in @("node","npm","pnpm","python","pip","git")) {
  $p = Get-Command $c -ErrorAction SilentlyContinue
  if ($p) { "$c -> $($p.Source)" } else { "$c 未安装" }
}
```

## 第 2 步：建目录骨架（统一结构，后面都在这里）

```powershell
$dirs = @("D:\Apps", "D:\Cache\pnpm-store", "D:\Cache\npm", "D:\Cache\pip", "D:\Temp")
foreach ($d in $dirs) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
```

| 目录 | 放什么 |
|---|---|
| `D:\Apps` | 程序本体（Node.js、绿色软件） |
| `D:\Cache` | 包管理器缓存，删了能重建 |
| `D:\Temp` | 临时文件 |
| `D:\下载` / `D:\文档` | 用户文件（用系统重定向） |

## 第 3 步：包管理器缓存重定向（收益最大、风险最低）

```powershell
pnpm config set store-dir "D:\Cache\pnpm-store"
```

npm 这里有个坑：**PowerShell 直接调 `npm` 会命中 `npm.ps1`，被执行策略拦住**（`因为在此系统上禁止运行脚本`）。必须用 `npm.cmd`：

```powershell
& "C:\Program Files\nodejs\npm.cmd" config set cache "D:\Cache\npm"
# 或直接写 C:\Users\<user>\.npmrc：
# cache=D:\Cache\npm
```

pip：

```powershell
python -m pip config set global.cache-dir "D:\Cache\pip"
# 落在 %APPDATA%\pip\pip.ini
```

> pnpm store 迁走后，旧 store 可以直接删。项目里的 `node_modules` 是实体副本，不依赖 store；只是以后离线重装依赖要重新下载。
> 删除前确认体积：`pnpm store path` 给出当前路径。

## 第 4 步：迁移程序本体

### Git（绿色安装，最省事）

winget 走不通时（直连 GitHub 超时，报 `0x80072efd`），用清华镜像：

```
https://mirrors.tuna.tsinghua.edu.cn/github-release/git-for-windows/git/LatestRelease/Git-<ver>-64-bit.exe
```

静默安装到指定目录：

```
Git-2.56.0.2-64-bit.exe /VERYSILENT /NORESTART /NOCANCEL /SP- /DIR=D:\Git /COMPONENTS=icons,ext\reg\shellhere,assoc,assoc_sh
```

装完验证 PATH 已由安装器写好，并检查注册表 `Uninstall\Git_is1` 的 `InstallLocation` 指向新路径。

卸载旧版本时如果残留 `unins000.exe` 删不掉（`Access is denied`），说明需要提权 —— 见第 6 步。

### Node.js（官方 MSI 版是个麻烦）

MSI 版**不能靠移动目录完成迁移**，硬搬会让「应用和功能」里的卸载失效、升级失败。

正确做法是**换成官方 zip 绿色版**：

```powershell
# 1) 下载对应版本的 zip（版本要和已装的一致，避免行为差异）
Invoke-WebRequest "https://nodejs.org/dist/v26.12.0/node-v26.12.0-win-x64.zip" -OutFile D:\Temp\node.zip

# 2) 解压并剥掉内层目录
Expand-Archive D:\Temp\node.zip -DestinationPath D:\Apps\_x -Force
Move-Item "D:\Apps\_x\node-v26.12.0-win-x64" "D:\Apps\nodejs"
Remove-Item "D:\Apps\_x" -Recurse -Force

# 3) 验证
& D:\Apps\nodejs\node.exe --version
& D:\Apps\nodejs\npm.cmd  --version
```

剩下的（改 PATH + 卸载 MSI）需要管理员，见第 6 步。

> 检查是否 MSI 安装：`Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" | Where-Object { $_.DisplayName -match "Node" }`，若 `UninstallString` 里是 `MsiExec.exe` 就是 MSI。
> Node 只有 100 多 MB，如果用户只关心大头，可以放着不动。

### Python

绿色版（embeddable / 独立发行版）直接解压到 `D:\py` 即可，无需安装器。
`pip config set` 写入的是用户级 ini，不随解释器路径变化。

## 第 5 步：用户目录与系统设置

已迁移过的确认方法见第 1 步。要改下载目录，**不要手改注册表 GUID**，用右键属性：`下载` 文件夹 → 属性 → 位置 → 移动。系统会自动同步注册表。

系统默认安装位置：

```powershell
Start-Process "ms-settings:savelocations"
```

打开「系统 → 存储 → 高级存储设置 → 新内容的保存位置」。

> **必须说清楚的限制**：这个设置**只对 Microsoft Store / MSIX 应用有效**。传统 exe 安装器（Office、游戏客户端、多数开发工具）照样默认 `C:\Program Files`，要在安装向导里手动把路径改成 `D:\Apps\...`。
> **不要**去改注册表 `ProgramFilesDir` —— 那是老办法，会导致大量应用找不到依赖、卸载器报错，修复代价远高于收益。

## 第 6 步：需要管理员权限时（本环境的现实约束）

AI 进程通常**不是管理员**，而且跑在非交互会话里，`Start-Process -Verb RunAs` 的 UAC 弹窗根本弹不出来 —— 实测会返回 `-1073741510`（`STATUS_CONTROL_C_EXIT`），日志为空、什么都没改。

**可靠做法：生成一个自检权限的 .bat 放桌面，让用户右键「以管理员身份运行」。**

```bat
@echo off
chcp 65001 >nul
net session >nul 2>&1
if errorlevel 1 (
  echo [错误] 当前不是管理员，请右键「以管理员身份运行」
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Temp\do-it.ps1"
pause
```

配套的 ps1 要做的事（示例：Node 迁移）：

```powershell
# 改 Machine PATH：替换旧路径，顺带清理失效条目
$old = "C:\Program Files\nodejs\"; $new = "D:\Apps\nodejs\"
$out = @()
foreach ($p in ([Environment]::GetEnvironmentVariable("Path","Machine") -split ";" | Where-Object { $_ })) {
  if ($p -ieq $old -or $p -ieq $old.TrimEnd('\')) { if ($out -notcontains $new) { $out += $new } }
  else { $out += $p }
}
if ($out -notcontains $new) { $out += $new }
[Environment]::SetEnvironmentVariable("Path", ($out -join ";"), "Machine")

# 卸载 MSI
Start-Process msiexec.exe -ArgumentList "/x", "{AE0B9215-...}", "/qn", "/norestart" -Wait

# 清理残留
Remove-Item "C:\Program Files\nodejs" -Recurse -Force -ErrorAction SilentlyContinue
```

> 改完 PATH **必须重开终端**才生效。已打开的 DSH / 编辑器仍持有旧环境变量。

## 第 7 步：桌面入口

```powershell
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$env:USERPROFILE\Desktop\Git Bash.lnk")
$sc.TargetPath       = "D:\Git\git-bash.exe"
$sc.WorkingDirectory = "D:\web-clone-replica"   # 打开就停在项目里
$sc.IconLocation     = "D:\Git\git-bash.exe,0"
$sc.Save()
```

再配一份 `启动方式.txt` 写清 PATH 延迟生效这件事，比口头交代管用。

## 第 8 步：验收

```powershell
# 重定向是否真的生效
pnpm config get store-dir
npm  config get cache
pip  config list
# 目录是否都在 D 盘
foreach ($p in @("D:\Apps","D:\Cache","D:\下载","D:\文档")) { "$p -> $(Test-Path -LiteralPath $p)" }
# 磁盘前后对比
Get-PSDrive C,D | ForEach-Object { "$($_.Name): 剩余 $([math]::Round($_.Free/1GB,1)) GB" }
```

最后扫一遍有没有留下临时产物：

```powershell
Get-ChildItem "$env:USERPROFILE\Desktop","$env:LOCALAPPDATA\Temp" -File -Force |
  Where-Object { $_.Name -like "_*" } | Select-Object FullName
```

---

## 陷阱清单

| 现象 | 真因 | 处置 |
|---|---|---|
| `npm` 报「禁止运行脚本」 | 命中了 `npm.ps1` | 用 `npm.cmd` 全名调用 |
| `Start-Process -Verb RunAs` 静默失败，退出码 `-1073741510` | 非交互会话弹不出 UAC | 生成桌面 .bat 让用户右键运行 |
| 卸载后 `unins000.exe` 删不掉 | 上一版安装器残留，需提权 | 提权删除，不要用 `takeown` 硬刚 |
| 改完 PATH 仍报命令找不到 | 当前进程持有旧环境变量 | 重开终端；临时用全路径 |
| MSI 版软件直接移动目录 | 「应用和功能」失效、升级失败 | 卸载后改用 zip 绿色版 |
| winget / 直连 GitHub 超时 | 网络受限 | 用清华/中科大镜像 |
| 系统「默认安装盘」不管用 | 只对 Store 应用生效 | 安装向导里手动改路径 |

## 不该碰的东西

| 对象 | 体积参考 | 原因 |
|---|---|---|
| Microsoft / Edge 组件 | 6 GB+ | 系统组件，搬了会坏 |
| NVIDIA 驱动 | 5 GB+ | 驱动，重装麻烦且收益低 |
| Microsoft Office | 4 GB+ | 需卸载重装，激活有风险 |
| 厂商预装工具（Lenovo 等） | 3 GB+ | 依赖链复杂 |
| `C:\Windows`（WinSxS 等） | — | 系统目录 |

真正值得搬的永远是：**包管理器缓存、独立命令行工具、绿色软件、用户文件**。

## 参考：一台已治理机器的最终形态

```
D:\Apps\nodejs        Node.js 绿色版
D:\Cache\pnpm-store   pnpm 仓库
D:\Cache\npm          npm 缓存
D:\Cache\pip          pip 缓存
D:\Git                Git
D:\py2                Python
D:\Temp               临时目录
D:\下载  D:\文档        用户文件（系统重定向）
```

C 盘只剩下系统、驱动、Office 这类搬不动的部分。
