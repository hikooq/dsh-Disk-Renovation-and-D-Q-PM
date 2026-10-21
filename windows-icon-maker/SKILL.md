---
name: windows-icon-maker
description: 把一张图片做成 Windows 图标（.ico）并替换桌面/开始菜单快捷方式的图标。当用户发来图片说「做成图标」「换成这个图标」「改快捷方式图标」「提取图标」，或者需要多尺寸 ICO、圆角图标、抠底透明图标、批量替换 .lnk 图标、还原快捷方式图标时使用。附带可直接运行的脚本，不要手抄 Pillow 代码。
---

# Windows 图标制作与快捷方式替换

把用户随手发来的一张图，变成桌面上真正能用的图标。

**这个技能自带脚本。默认用脚本，不要手抄 Pillow 代码重造一遍**——手抄的每一次都会重新踩一遍下面「陷阱清单」里的坑。

## 铁律

1. **先跑 `analyze` 再动手**。源图多大、有没有透明、是不是像素画，决定了后面每一步参数。
2. **生成后自己先看预览图**（`--preview` 产物），确认小尺寸没糊成一团，再拿去交付。
3. **改 `.lnk` 前必须 `-DryRun` 预演**，看清会命中哪几个、改前改后各是什么。
4. **桌面和开始菜单要一起改**，只改一处会两边图标不一致。
5. **绝不改启动目标**（`TargetPath`/`Arguments`/`WorkingDirectory`），只改 `IconLocation`。

## 脚本位置

```
<skill根>\scripts\icon_maker.py      图像部分：分析 / 生成 / 预览 / 校验
<skill根>\scripts\apply_icon.ps1     快捷方式部分：应用 / 备份 / 还原 / 体检
```

`<skill根>` 就是本 `SKILL.md` 所在目录。装在 DSH 技能目录里时通常是
`%APPDATA%\dsh-desktop\harness\skills\windows-icon-maker`。

## 环境

需要一个带 Pillow 的 Python（3.8+）。先确认：

```powershell
python -c "import PIL; print(PIL.__version__)"
```

能打印版本号就直接用 `python`；报 `ModuleNotFoundError` 就装一下：

```powershell
python -m pip install pillow
```

机器上装了多个 Python 时，把下文所有 `python` 换成**装了 Pillow 的那个解释器的完整路径**。

图标默认输出到 `<OUT>` = `%USERPROFILE%\Pictures\icons`（不存在会自动建）。
要改默认值，设环境变量 `ICON_OUT_DIR`，或每次显式传 `--out <目录>`。

> `apply_icon.ps1` **必须用 UTF-8 with BOM 保存**。PowerShell 5.1 读无 BOM 的 UTF-8 会按 GBK 解码，中文全乱、直接语法错误。改动这个文件后如果报「Unexpected token」乱码，先补 BOM。

---

## 第 0 步：定位源图

用户通过聊天发的图落在 DSH 附件目录，**文件名是 sha256，没有扩展名**：

```
C:\Users\<user>\AppData\Roaming\dsh-desktop\harness\attachments\v1\objects\<前2位>\<sha256>
```

路径就在消息附件的 `Normalized copy` 那一行。不要靠扩展名判断格式，Pillow 会自己嗅探（脚本的 `open_any()` 处理了无扩展名、GIF 取首帧、ICO 取最大帧、EXIF 方向）。

## 第 1 步：体检

```powershell
python "<skill>\scripts\icon_maker.py" analyze "<源图路径>"
```

输出会直接告诉你该怎么做：

```json
{
  "info": {
    "width": 155, "height": 152, "square_side": 152,
    "has_alpha": false,
    "corner_bg": "#FFFFFF", "corner_bg_ratio": 0.573,
    "style": "illustration",
    "resample": "LANCZOS",
    "low_res": true
  },
  "advice": ["源图仅 152px，不足 256：**不要裁切**……"]
}
```

关键字段：

| 字段 | 含义 | 影响什么 |
|---|---|---|
| `square_side` | 可用边长 | `< 256` → 小图，禁止裁切 |
| `has_alpha` | 是否已有透明像素 | 决定要不要抠底 |
| `corner_bg` | 四边众数背景色 | 有值说明能抠底 |
| `style` | `pixel-art` / `illustration` / `photo` | 像素画用 NEAREST，其它用 LANCZOS |
| `low_res` | 是否够 256 | 是否在交付时警告 |

## 第 2 步：生成

```powershell
# 最常用：圆角+方角都出，附尺寸预览图
python "<skill>\scripts\icon_maker.py" make "<源图>" --name whale --preview

# 白底插画：把底色抠成透明
... make "<源图>" --name whale --bg transparent --preview

# 只想要圆角版
... make "<源图>" --name whale --mode round --preview
```

产物：

```
<OUT>\whale-round.ico     圆角版（主推）
<OUT>\whale-square.ico    方角备选
<OUT>\whale.png           256 透明底 PNG
<OUT>\whale-sizes.png     各尺寸真实像素对比图  ← 必须自己看
```

脚本自动做的事：

- **`square_side < 256` 时自动不裁切**，直接把整图缩放，并在 `warnings` 里写明"16/24px 档不可用"
- 非正方形又不裁切 → 居中垫成正方形，**绝不拉伸变形**
- 像素画用 NEAREST 保硬边，插画/照片用 LANCZOS
- 每档尺寸**单独**缩放 + 单独圆角，小尺寸边角才干净
- 圆角用 `multiply` 乘进原 alpha，不会丢掉图片自带的透明区域
- 生成完立刻回读 ICO 核尺寸，缺档返回退出码 3

## 第 3 步：自己看预览图

```powershell
# 已经生成过 --preview 就不用再跑
python "<skill>\scripts\icon_maker.py" preview "<OUT>\whale-round.ico"
```

**打开 `whale-sizes.png` 用 read_image 看**。浅底一行、深底一行，各档按真实像素并排。

判据：

- 256 / 128 清晰 → 及格
- 48 / 64 还能认出主体 → 可用
- 32 已经糊成一团 → 必须在交付时如实告诉用户
- **16px 基本没有意义**，但尺寸表里必须有（哪怕糊）

小图糊是素材本身的天花板，不是脚本的问题。**不要为了让小尺寸清晰去裁切、锐化、加深描边**——试过，只会更糟。

## 第 4 步：应用到快捷方式

### 4a 先预演

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<skill>\scripts\apply_icon.ps1" `
  -Icon "<OUT>\whale-round.ico" -Name "DSH Desktop" -DryRun
```

看 `changes` 里命中的 `Lnk` 路径对不对、修改前后的图标名对不对。`-Name` 是**模糊匹配**，给 `"DSH"` 会同时命中桌面和开始菜单的两份。

### 4b 再落盘

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<skill>\scripts\apply_icon.ps1" `
  -Icon "<OUT>\whale-round.ico" -Name "DSH Desktop"
```

脚本会：

- 在四处搜索（用户桌面 / 公共桌面 / 用户开始菜单 / 公共开始菜单）
- 自动把 `,0` 补到 `IconLocation` 后面
- **先备份再动手**，备份写成 `<OUT>\lnk-backup-<时间戳>.json`，**绝不覆盖历史备份**
- 改完立刻回读，确认 `TargetPath` 一个字都没变（`targetIntact` 字段）
- 跑 `ie4uinit.exe -show` 刷缓存

### 其他用法

```powershell
# 直接指定 lnk，不用名字搜
... apply_icon.ps1 -Icon "..." -LnkPath "%USERPROFILE%\Desktop\xxx.lnk"

# 体检：106 个快捷方式各自用的什么图标（排查"两边不一致"）
... apply_icon.ps1 -List

# 还原
... apply_icon.ps1 -Restore "<OUT>\lnk-backup-20261021-192120.json"
```

## 第 5 步：验收

```powershell
$ws = New-Object -ComObject WScript.Shell
"图标: " + $ws.CreateShortcut("%USERPROFILE%\Desktop\DSH Desktop.lnk").IconLocation
```

尺寸是否齐全**用 Pillow 判断，不要用 System.Drawing**：

```powershell
python "<skill>\scripts\icon_maker.py" verify "<OUT>\whale-round.ico"
# 期望 missing_standard 为空，sizes 含 16/24/32/48/64/128/256
```

桌面没变就让用户按 `F5`，还不行重启 `explorer.exe`。

---

## 决策表：什么情况用什么参数

| 情况 | 参数 | 理由 |
|---|---|---|
| 源图 ≥ 256 且非正方形 | 默认（`--crop auto` → square） | 裁掉多余边，主体填满 |
| 源图 < 256 | 默认（自动 `crop none`） | 裁了可用像素更少，**只会更糊** |
| 白底/纯色底插画 | `--bg transparent` | 深色桌面上不留一圈白框 |
| 像素画 | 脚本自动 NEAREST | LANCZOS 会把像素网格糊成毛边 |
| 深色背景图 | `--mode round`（默认就带） | 方角在浅色桌面上是一块死黑 |
| 想让图标显得小一点 | `--margin 0.1` | 裁切时向内收，四周留白 |
| 只要一个版本 | `--mode round` 或 `square` | 少产出两个文件 |

## 参数速查

```
icon_maker.py analyze <src>
icon_maker.py make    <src> [--out DIR] [--name NAME] [--mode round|square|both]
                            [--bg keep|transparent] [--crop auto|square|none]
                            [--margin 0~0.3] [--round-ratio 0.22] [--preview]
icon_maker.py preview <ico>
icon_maker.py verify  <ico>

apply_icon.ps1 -Icon <ico> (-Name <模糊名...> | -LnkPath <路径...>) [-DryRun] [-NoRefresh]
apply_icon.ps1 -Restore <备份json>
apply_icon.ps1 -List
```

退出码：`0` 成功 / `2` 参数或输入问题 / `3` ICO 尺寸缺失。

---

## 陷阱清单

### 图像侧

| 现象 | 真因 | 处置 |
|---|---|---|
| 大图标糊 / 任务栏清晰但桌面糊 | ICO 只存了 32×32 | `sizes` 必须给到 256 |
| `System.Drawing.Icon` 只报 32×32 | 该 API 按需挑一档，不代表文件缺 256 | 用 Pillow 读 `info["sizes"]` |
| 图标在浅色桌面上一块黑 | 深色背景图直接方角输出 | 加圆角遮罩 + 透明四角 |
| 头像被拉变形 | 直接 resize 到正方形 | 先裁正方形（或居中垫边），再缩放 |
| 手机照片图标上下颠倒 | EXIF 方向未处理 | `ImageOps.exif_transpose()` |
| 圆角做完图里原有的透明区变黑了 | `paste(im, mask)` 覆盖了原 alpha | 用 `ImageChops.multiply` 乘进 alpha |
| **小图裁完不如不裁** | 裁掉气泡/留白后可用像素只剩 80px | **<256 一律不裁**，完整版就是最优解 |
| 抠底后主体边缘缺一块 | 全局删色会误伤主体里的同色区 | 只用 flood fill 从四边连通区抠（脚本已如此） |
| 对 ICO 设 `im.size = (s,s)` 报 `ValueError: This is not one of the allowed sizes` | Pillow 12 的 IcoImagePlugin 只接受它自己的尺寸表 | 取帧用 `im.ico.frame((s,s))` |
| `sum(SIZES)` 报 `TypeError: unsupported operand type(s) for +: 'int' and 'tuple'` | SIZES 是元组列表 | `sum(s[0] for s in SIZES)` 或 `sum(frames)` 取 dict 的 key |

### 快捷方式侧

| 现象 | 真因 | 处置 |
|---|---|---|
| 换了图标桌面没变 | 图标缓存没刷新 | `ie4uinit.exe -show`，再 F5 |
| 只改了桌面，开始菜单还是老图标 | 只搜了 `%USERPROFILE%\Desktop` | 把 `Programs`、`CommonDesktopDirectory` 一起搜 |
| 换了图标后快捷方式打不开 | 误建了新 shortcut 对象，`TargetPath` 为空 | 只对 `CreateShortcut(已存在路径)` 的结果赋 `IconLocation`，改完回读 `TargetPath` |
| `IconLocation` 写成 `路径` 没写 `,索引` | 部分场景不生效 | 必须是 `路径,0` |
| 升级软件后图标回到默认 | 安装器重建了 `.lnk` | 重跑第 4 步，ICO 别删 |
| `.ps1` 报乱码 `Unexpected token` | 无 BOM 的 UTF-8 被按 GBK 读 | 存成 UTF-8 with BOM |
| `.ps1` 报 hashtable 语法错误 | PowerShell 5.1 **不允许**在 hashtable 字面量里写 `if` 表达式 | 先算成变量再塞进去 |

## 不该做的

- **不要**把 `.ico` 放在会被清理的目录（`%TEMP%`）—— 快捷方式只存路径，文件没了图标就空白。
- **不要**用在线转换站现造 ICO，本地 Pillow 一条命令就够，也避免把用户的图传出去。
- **不要**直接改程序 exe 的图标（要改 PE 资源），换 `.lnk` 的 `IconLocation` 等效且可逆。
- **不要**为了「小尺寸更清楚」而裁切源图 —— 已验证会反过来变得更糊。
- **不要**在没跑 `-DryRun` 的情况下批量改一堆快捷方式。
- **不要**手抄本技能里的 Pillow 代码另起一份 —— 直接用脚本，坑都已经填过了。

## 改这个技能时

脚本是**活脚本**，改之前先跑一遍这几条自测：

```powershell
$py = 'python'; $s = "<skill>\scripts\icon_maker.py"

$py $s analyze "<任意图>"
$py $s make    "<小图> " --out "$env:TEMP\ict" --name t --preview     # 走 low_res 分支
$py $s make    "<大图>"  --out "$env:TEMP\ict" --name b --preview     # 走 crop square 分支
$py $s make    "<白底图>" --out "$env:TEMP\ict" --name g --bg transparent
$py $s verify  "$env:TEMP\ict\t-round.ico"                            # missing_standard 应为空
```

```powershell
$p = "<skill>\scripts\apply_icon.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -List
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -Icon "..." -Name "DSH Desktop" -DryRun
```

改 `.ps1` 之后**记得补回 BOM**。改 `.py` 之后用 `-m py_compile` 过一遍。

## 参考：一次实际产物

```
<OUT>\
├── whale-thinking-round.ico    97 KB   圆角，7 档尺寸  ← 已应用于 DSH Desktop（桌面+开始菜单）
├── whale-thinking-square.ico   96 KB   方角备选
├── whale-thinking.png          57 KB   256 透明底
├── whale-thinking-sizes.png   187 KB   各尺寸对比图
├── dsh-lnk-backup-20261021-192120.json   替换前的原始信息
└── dsh-avatar-round.ico / .png           更早一次做的（同一套流程）
```

源图 155×152 像素画 → 判 `low_res` → 不裁切 → LANCZOS 整套放大 → 圆角 22%。
交付时已明确告知：**16/24px 档不可用，32px 起才能看**。
