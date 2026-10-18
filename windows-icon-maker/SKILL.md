---
name: windows-icon-maker
description: 把一张图片做成 Windows 图标（.ico）并替换桌面/开始菜单快捷方式的图标。当用户发来图片说「做成图标」「换成这个图标」「改快捷方式图标」「提取图标」，或者需要多尺寸 ICO、圆角图标、批量替换 .lnk 图标时使用。
---

# Windows 图标制作与快捷方式替换

把用户随手发来的一张图，变成桌面上真正能用的图标。

## 何时用

- 用户发图 + 「做成图标」「用它当图标」
- 「帮我把桌面那个快捷方式的图标换了」
- 需要 `.ico`（多尺寸、圆角、透明背景）
- 批量给一堆 `.lnk` 换同一个图标

## 环境

```powershell
# 带 Pillow 的 python（本机已验证）
D:\py2\python.exe
# 若无，则 D:\鲸鱼\DSH Desktop\resources\office-runtime\primary-runtime\dependencies\python\python.exe
```

图标统一存放目录：

```powershell
New-Item -ItemType Directory -Path "D:\Apps\icons" -Force | Out-Null
```

---

## 第 1 步：找到源图

用户通过聊天发的图，落在 DSH 附件目录：

```
C:\Users\<user>\AppData\Roaming\dsh-desktop\harness\attachments\v1\objects\<前2位>\<sha256>
```

文件名就是 sha256，没有扩展名 —— **不要靠扩展名判断格式，用 Pillow 打开**。路径通常在消息里的附件说明中直接给出（`Normalized copy` 那一行）。

## 第 2 步：裁正方形 + 圆角 + 导出多尺寸 ICO

```python
from PIL import Image, ImageOps, ImageDraw
import os

src = r"...attachments\v1\objects\44\44d6c5..."   # 用户发来的原图
out_dir = r"D:\Apps\icons"
os.makedirs(out_dir, exist_ok=True)

im = Image.open(src)
im = ImageOps.exif_transpose(im).convert("RGBA")   # 手机照片可能带 EXIF 方向
w, h = im.size

# 非正方形：居中裁成正方形
side = min(w, h)
left, top = (w - side) // 2, (h - side) // 2
im = im.crop((left, top, left + side, top + side))

# 圆角遮罩（半径约为边长的 20%~24%，接近 Win11 图标观感）
radius = int(side * 0.22)
mask = Image.new("L", (side, side), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, side - 1, side - 1], radius=radius, fill=255)
round_im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
round_im.paste(im, (0, 0), mask)

# 必须给全尺寸：任务栏、桌面大图标、资源管理器小图标各取所需
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

round_im.save(os.path.join(out_dir, "app.png"), "PNG")
round_im.save(os.path.join(out_dir, "app-round.ico"), format="ICO", sizes=SIZES)
im.save(os.path.join(out_dir, "app-square.ico"), format="ICO", sizes=SIZES)  # 方角备选
print("ok")
```

> 方角版和圆角版一起生成，让用户自己挑。深色背景的图尤其需要圆角，否则在浅色桌面上是一块死黑方块。

## 第 3 步：应用到快捷方式

```powershell
$lnk = "$env:USERPROFILE\Desktop\DSH Desktop.lnk"
$ws  = New-Object -ComObject WScript.Shell

# 先备份原始信息，方便还原
$sc = $ws.CreateShortcut($lnk)
[pscustomobject]@{
    Target  = $sc.TargetPath
    Args    = $sc.Arguments
    Icon    = $sc.IconLocation
    WorkDir = $sc.WorkingDirectory
} | ConvertTo-Json | Out-File "D:\Apps\icons\lnk-backup.json" -Encoding utf8

# 只改图标，不动启动目标
$sc = $ws.CreateShortcut($lnk)
$sc.IconLocation = "D:\Apps\icons\app-round.ico,0"
$sc.Save()
```

**`IconLocation` 的格式是 `路径,索引`** —— 那个 `,0` 不能省，否则部分场景下不生效。

## 第 4 步：刷新图标缓存

```powershell
ie4uinit.exe -show
```

没变化就按 `F5`，再不行重启 `explorer.exe`。

## 第 5 步：验收

```powershell
"图标: " + (New-Object -ComObject WScript.Shell).CreateShortcut($lnk).IconLocation
Add-Type -AssemblyName System.Drawing
$i = New-Object System.Drawing.Icon("D:\Apps\icons\app-round.ico")
"可载入: $($i.Width)x$($i.Height)"
$i.Dispose()
```

确认 ICO 的尺寸清单（**别用 System.Drawing 判断**）：

```python
from PIL import Image
print(sorted(Image.open(r"D:\Apps\icons\app-round.ico").info.get("sizes", [])))
# 期望 [(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)]
```

---

## 批量替换

```powershell
$ico = "D:\Apps\icons\app-round.ico,0"
$ws  = New-Object -ComObject WScript.Shell
foreach ($name in @("Git Bash", "Git CMD", "Visual Studio Code")) {
    $p = "$env:USERPROFILE\Desktop\$name.lnk"
    if (Test-Path -LiteralPath $p) {
        $s = $ws.CreateShortcut($p)
        $s.IconLocation = $ico
        $s.Save()
        "已换: $name"
    }
}
ie4uinit.exe -show
```

想还原时，把备份 json 里的 `Icon` 值写回去即可。

---

## 陷阱清单

| 现象 | 真因 | 处置 |
|---|---|---|
| 大图标糊 / 任务栏清晰但桌面糊 | ICO 只存了 32×32 | `sizes` 必须给到 256 |
| `System.Drawing.Icon` 只报 128×128 | 该 API 按需挑尺寸，不代表文件缺 256 | 用 Pillow 读 `info["sizes"]` 核对 |
| 图标在浅色桌面上一块黑 | 深色背景图直接方角输出 | 加圆角遮罩 + 透明四角 |
| 换了图标桌面没变 | 图标缓存没刷新 | `ie4uinit.exe -show`，再 F5 |
| 快捷方式打不开了 | 用 `IconLocation` 赋值时误建了新 shortcut 对象 | 先 `CreateShortcut($lnk)` 读、再读一次改，或确认没动 `TargetPath` |
| 头像被拉变形 | 直接 resize 到正方形 | 先居中裁正方形，再缩放 |
| 手机拍的照片图标上下颠倒 | EXIF 方向未处理 | `ImageOps.exif_transpose(im)` |
| 升级软件后图标回到默认 | 安装器重建了 `.lnk` | 重跑第 3 步，ICO 文件别删 |

## 不该做的

- **不要**把 `.ico` 放在会被清理的目录（`%TEMP%`、`C:\Users\<u>\AppData\Local\Temp`）—— 快捷方式只存路径，文件没了图标就空白。
- **不要**用在线转换站现造 ICO，本地 Pillow 一条命令就够，也避免把用户的图传出去。
- **不要**直接改程序 exe 的图标（需要改 PE 资源），换 `.lnk` 的 `IconLocation` 是等效且可逆的做法。

## 参考：一次实际产物

```
D:\Apps\icons\
├── dsh-avatar-round.ico    100 KB   圆角，7 档尺寸  ← 已应用到 DSH Desktop.lnk
├── dsh-avatar.ico           96 KB   方角备选
├── dsh-avatar-round.png    290 KB   透明底源图
├── dsh-avatar.png          293 KB
└── dsh-lnk-backup.json              原快捷方式信息
```
