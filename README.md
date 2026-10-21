# DSH Skills

给 [DSH](https://github.com/deepseek-ai) 这类 AI 编码代理用的可复用技能包。每个目录是一个独立 skill，核心是 `SKILL.md`（YAML frontmatter + 操作手册）。

## 包含的技能

| 技能 | 用途 | 典型触发 |
|---|---|---|
| [`windows-disk-migration`](windows-disk-migration/SKILL.md) | Windows 磁盘空间治理与开发环境迁移 | 「C 盘又满了」「软件都装 D 盘」「把 Node/Python 搬到 D 盘」 |
| [`windows-icon-maker`](windows-icon-maker/SKILL.md) | 把图片做成 `.ico` 并替换快捷方式图标（**含可直接运行的脚本**） | 「把这张图做成图标」「换个快捷方式图标」 |

## 怎么用

### 方式一：装到 DSH 的本地技能目录

```powershell
$dst = "$env:APPDATA\dsh-desktop\harness\skills"
Copy-Item ".\windows-disk-migration" $dst -Recurse -Force
Copy-Item ".\windows-icon-maker"     $dst -Recurse -Force
```

放进去就生效，不用重启 —— DSH 会扫描该目录并把 `description` 注入给模型。

### 方式二：直接在对话里引用

```
按 <path>\windows-disk-migration\SKILL.md 的流程来
```

### 方式三：OpenViking 技能库（跨设备）

```bash
ov skills add ./windows-disk-migration -p viking://~/skills
```

## 两个技能讲了什么

### windows-disk-migration

把「以后都装 D 盘」从口头承诺变成配好的机器。核心是三条铁律：

1. 先测量再动手
2. 区分「程序」（`D:\Apps`）、「缓存」（`D:\Cache`）、「用户文件」（`D:\下载`/`D:\文档`）
3. 不碰系统组件

覆盖：磁盘体检（近两日增长扫描）、pnpm/npm/pip 缓存重定向、Git 绿色安装、Node.js MSI → zip 版迁移、需要管理员权限时的 `.bat` 绕行方案、桌面快捷方式、验收清单，以及一张「哪些能搬、哪些不能搬」的对照表。

### windows-icon-maker

把一张图变成桌面上真正能用的图标。`SKILL.md` 只写判断标准和坑，具体操作交给 `scripts/` 里的两个脚本，不用现场重抄 Pillow 代码。

**做图标**（`scripts/icon_maker.py`，纯 Python + Pillow，无第三方 CLI 依赖）：

```bash
python icon_maker.py analyze 图.png                  # 先看：尺寸/透明/背景色/是否像素风
python icon_maker.py make 图.png --preview           # 出全套：圆角+方角+透明底，7 档尺寸，附对比图
python icon_maker.py verify 图.ico                   # 复查：7 档尺寸缺没缺
```

脚本自己判断该不该裁、该不该抠白底、源图太小要不要警告，不用逐个试参数。源图没有扩展名、是 GIF、是 ICO 都能直接喂进去。

**换快捷方式图标**（`scripts/apply_icon.ps1`）：

```powershell
.\apply_icon.ps1 -List                                  # 列出能找到的所有快捷方式
.\apply_icon.ps1 -Icon icon.ico -Name DSH -DryRun       # 先演练，不落盘
.\apply_icon.ps1 -Icon icon.ico -Name DSH               # 真改，自动备份
.\apply_icon.ps1 -Restore -Name DSH                     # 反悔，还原
```

搜桌面 + 公共桌面 + 用户/系统开始菜单四处，自动补 `,0`，改完回读校验 `TargetPath` 没被动过。

关键点：

- ICO 必须存全尺寸（16/24/32/48/64/128/256），否则大图标糊；16/24px 档本来就看不清，交付时要说明
- **源图小于 256 时不要裁切** —— 实测裁掉气泡/留白后放大反而更糊，完整版才是最优解
- 背景色要按「四条边像素众数」判断，只看四角会在主体占满画面时误判为无背景
- 深色背景图要加圆角遮罩，否则浅色桌面上一块死黑；圆角要乘进原 alpha（`ImageChops.multiply`），不能 paste，否则透明区被吃掉
- `IconLocation` 格式是 `路径,索引`，那个 `,0` 不能省
- `System.Drawing.Icon` 报 128×128 不代表文件缺 256（它按需挑尺寸），核尺寸要用 Pillow 的 `info["sizes"]`
- `.ps1` 必须存成 UTF-8 **with BOM**，否则 PowerShell 5.1 按 GBK 读会乱码并报语法错

## 一些约定

- `SKILL.md` 的 frontmatter 只留 `name` 和 `description`；`description` 是唯一被语义检索索引的字段，要写清「做什么」和「什么时候用」，用用户会说的话。
- 能代码化的流程拆到 `scripts/` 下，`SKILL.md` 只留判断标准、参数语义和坑 —— 让 agent 直接调用脚本，而不是每次重抄一遍代码。
- 技能正文按「何时用 → 环境 → 分步操作 → 陷阱清单」组织，每一步都给可直接执行的命令，不写抽象建议。
- 涉及本机绝对路径的地方都标了 fallback，换机器时需要核对。
- 不把密钥、token、内部域名写进 SKILL.md。

## 许可

技能文本采用 MIT（见 [LICENSE](LICENSE)）。

其中的命令与经验来自实际排查过程，涉及第三方软件（Git、Node.js、Python 等）时，其许可与版权归各自所有者。
