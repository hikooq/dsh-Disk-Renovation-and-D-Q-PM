# DSH Skills

给 [DSH](https://github.com/deepseek-ai) 这类 AI 编码代理用的可复用技能包。每个目录是一个独立 skill，核心是 `SKILL.md`（YAML frontmatter + 操作手册）。

## 包含的技能

| 技能 | 用途 | 典型触发 |
|---|---|---|
| [`windows-disk-migration`](windows-disk-migration/SKILL.md) | Windows 磁盘空间治理与开发环境迁移 | 「C 盘又满了」「软件都装 D 盘」「把 Node/Python 搬到 D 盘」 |
| [`windows-icon-maker`](windows-icon-maker/SKILL.md) | 把图片做成 `.ico` 并替换快捷方式图标 | 「把这张图做成图标」「换个快捷方式图标」 |

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

把一张图变成桌面上真正能用的图标。关键点：

- ICO 必须存全尺寸（16/24/32/48/64/128/256），否则大图标糊
- 深色背景图要加圆角遮罩，否则浅色桌面上一块死黑
- `IconLocation` 格式是 `路径,索引`，那个 `,0` 不能省
- `System.Drawing.Icon` 报 128×128 不代表文件缺 256（它按需挑尺寸）

含完整 Pillow 脚本、`WScript.Shell` 替换快捷方式图标、批量替换循环、8 条踩坑记录。

## 一些约定

- `SKILL.md` 的 frontmatter 只留 `name` 和 `description`；`description` 是唯一被语义检索索引的字段，要写清「做什么」和「什么时候用」，用用户会说的话。
- 技能正文按「何时用 → 环境 → 分步操作 → 陷阱清单」组织，每一步都给可直接执行的命令，不写抽象建议。
- 涉及本机绝对路径的地方都标了 fallback，换机器时需要核对。
- 不把密钥、token、内部域名写进 SKILL.md。

## 许可

技能文本采用 MIT（见 [LICENSE](LICENSE)）。

其中的命令与经验来自实际排查过程，涉及第三方软件（Git、Node.js、Python 等）时，其许可与版权归各自所有者。
