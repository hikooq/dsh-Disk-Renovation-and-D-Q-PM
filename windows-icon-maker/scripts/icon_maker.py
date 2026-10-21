#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Windows 图标生成引擎（windows-icon-maker 技能的官方脚本）

为什么要有这个脚本：
    纯手工抄 Pillow 代码做图标，每次都要重新踩一遍相同的坑
    （源图太小还硬裁、圆角覆盖了原透明通道、ICO 尺寸表没给全、
     预览图直接改 ICO 的 size 导致 ValueError……）。
    把"分析 -> 决策 -> 生成 -> 自检"固化成脚本，agent 只负责调用和看报告。

子命令：
    analyze <src>                     只分析源图，告诉你该怎么处理，不产出文件
    make    <src> [选项]              生成 ICO（圆角/方角/透明背景）+ 报告
    preview <ico|png> [选项]          生成真实像素的尺寸对比图（浅底/深底）
    verify  <ico>                     自检 ICO 内含尺寸是否齐全

典型调用：
    python icon_maker.py make <图片> --name whale --mode both --preview
    python icon_maker.py make in.jpg --bg transparent --name logo
    python icon_maker.py analyze somefile

退出码：0 成功 / 2 参数或输入问题 / 3 生成结果异常（尺寸缺失）
"""

import argparse
import io
import json
import os
import sys
import traceback
from collections import Counter

# ---------------------------------------------------------------- 编码
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

try:
    from PIL import Image, ImageChops, ImageDraw, ImageOps
except ImportError:  # pragma: no cover
    sys.exit(
        "[X] 缺少 Pillow。先安装：\n"
        "    python -m pip install pillow\n"
        "    机器上有多个 Python 时，用带 Pillow 的那个解释器跑本脚本。"
    )

# ---------------------------------------------------------------- 常量
STANDARD_SIZES = [16, 24, 32, 48, 64, 128, 256]   # 一档都不能少
# 输出目录：优先环境变量 ICON_OUT_DIR，否则落到当前用户的 图片\icons。
# 不假设机器上有 D 盘，也不假设目录已存在（make 会自己建）。
DEFAULT_OUT = os.environ.get("ICON_OUT_DIR") or os.path.join(
    os.path.expanduser("~"), "Pictures", "icons"
)
ROUND_RATIO = 0.22                                 # Win11 观感的圆角比例
# Windows 真正会用到的小尺寸，低于这个值的档位糊了基本没人看见
TINY_SIZES = (16, 24)


# ================================================================ 打开
def open_any(path):
    """打开任意图片：无扩展名 / GIF / ICO / 带 EXIF 的手机照片都能吃。

    DSH 附件目录里的文件就是 sha256 裸名，没有扩展名，
    所以这里绝不依赖后缀判断格式，全部交给 Pillow 嗅探。
    """
    if not os.path.exists(path):
        raise FileNotFoundError("找不到源图：%s" % path)
    if os.path.isdir(path):
        raise IsADirectoryError("源图路径是个目录：%s" % path)

    raw = Image.open(path)

    # GIF / WebP 动图：取第一帧，图标不需要动
    if getattr(raw, "n_frames", 1) > 1:
        raw.seek(0)

    # 源本身就是 ICO：挑它里面最大的那一档，别拿 16px 去放大
    if raw.format == "ICO":
        cand = raw.info.get("sizes") or []
        if cand:
            try:
                raw.size = max(cand)      # Pillow 12 只允许设置 sizes 里的值
            except Exception:
                pass                      # 设不了就算了，用默认帧

    # 手机照片带方向标记，不转正会得到躺倒的图标
    im = ImageOps.exif_transpose(raw)
    return im.convert("RGBA")


# ================================================================ 分析
def analyze(im):
    """看源码前先体检，输出后续决策需要的全部事实。"""
    w, h = im.size
    side = min(w, h)

    # 1) 是否已有透明像素
    alpha_min = im.getchannel("A").getextrema()[0]
    has_alpha = alpha_min < 250

    # 2) 背景色：取四条边像素的众数。
    #    只看四角会误判 —— 头发/人物常常把下面两个角占满，
    #    四个角凑不齐同一种颜色，但图其实有明显底色。
    px = im.load()
    edge = []
    for x in range(w):
        edge.append(px[x, 0][:3])
        edge.append(px[x, h - 1][:3])
    for y in range(h):
        edge.append(px[0, y][:3])
        edge.append(px[w - 1, y][:3])
    solid_bg = None
    bg_ratio = 0.0
    if edge:
        mode_color, mode_cnt = Counter(edge).most_common(1)[0]
        bg_ratio = mode_cnt / float(len(edge))
        if bg_ratio >= 0.35:
            solid_bg = mode_color

    # 3) 风格判定：缩到 64x64 后数唯一色
    #    像素画的调色板很小，插画/照片则是成千上万种渐变
    thumb = im.convert("RGB").resize((64, 64), Image.NEAREST)
    ncolors = len(thumb.getcolors(64 * 64) or [])
    pixel_art = ncolors <= 128
    photo_like = ncolors > 2000

    # 4) 分辨率是否够撑起 256 档
    low_res = side < 256

    return {
        "width": w,
        "height": h,
        "square_side": side,
        "has_alpha": has_alpha,
        "corner_bg": ("#%02X%02X%02X" % solid_bg) if solid_bg else None,
        "corner_bg_ratio": round(bg_ratio, 3),
        "unique_colors_64": ncolors,
        "style": "pixel-art" if pixel_art else ("photo" if photo_like else "illustration"),
        "resample": "NEAREST" if pixel_art else "LANCZOS",
        "low_res": low_res,
    }


def advise(info):
    """把体检结论翻译成"接下来该怎么办"，这是原 SKILL.md 缺的那一块。"""
    tips = []
    if info["low_res"]:
        tips.append(
            "源图仅 %dpx，不足 256：**不要裁切**，任何裁切都会让可用像素更少、放大后更糊。"
            "直接整套缩放，并在交付时明确告知 16/24px 档不可用。" % info["square_side"]
        )
    if info["corner_bg"] and not info["has_alpha"]:
        tips.append(
            "检测到纯色背景 %s 且无透明通道：圆角后四角透明、但主体四周仍会带一圈背景色；"
            "想真正抠掉底色请加 --bg transparent。" % info["corner_bg"]
        )
    if info["style"] == "pixel-art":
        tips.append(
            "判定为像素画：缩放用 NEAREST 保留硬边，用 LANCZOS 会把像素网格糊成毛边。"
        )
    if info["style"] == "photo":
        tips.append("判定为照片/平滑图像：缩放用 LANCZOS，圆角必须加，否则浅色桌面上一块死方块。")
    if not tips:
        tips.append("常规图，按默认参数生成即可。")
    return tips


# ================================================================ 图像处理
def crop_square(im, margin=0.0, anchor="center"):
    """居中裁正方形。margin>0 时向内收，给图标留一点呼吸空间。"""
    w, h = im.size
    base = min(w, h)
    side = max(1, int(base * (1.0 - margin)))
    if anchor == "top":
        left, top = (w - side) // 2, 0
    elif anchor == "bottom":
        left, top = (w - side) // 2, h - side
    else:
        left, top = (w - side) // 2, (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def apply_rounded(im, ratio=ROUND_RATIO):
    """加圆角遮罩。

    注意必须用 multiply 把圆角乘进**原有的 alpha**，
    直接 paste(im, (0,0), mask) 会丢掉图片自带的透明区域。
    """
    side = im.size[0]
    r = max(1, int(side * ratio))
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, side - 1, side - 1], radius=r, fill=255
    )
    out = im.copy()
    out.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
    return out


def strip_background(im, tol=36):
    """把与四边连通的纯色背景抠成透明（flood fill，不是全局删色）。

    返回 (新图, 是否成功)。找不到安全哨兵色时原样返回，绝不乱改。
    """
    w, h = im.size
    rgb = im.convert("RGB")
    existing = set(rgb.getdata())

    sentinel = None
    for cand in ((255, 0, 255), (1, 2, 3), (254, 1, 253), (0, 255, 1)):
        if cand not in existing:
            sentinel = cand
            break
    if sentinel is None:
        return im, False

    work = rgb.copy()
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if work.getpixel(corner) != sentinel:
            try:
                ImageDraw.floodfill(work, corner, sentinel, thresh=tol)
            except Exception:
                return im, False

    pixels = work.getdata()
    alpha_bytes = bytes(0 if p == sentinel else 255 for p in pixels)
    mask = Image.frombytes("L", (w, h), alpha_bytes)

    out = im.copy()
    out.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
    return out, True


def build_frames(master, sizes, resample, rounded, round_ratio=ROUND_RATIO):
    """从 256 母版逐档生成。每档单独缩放 + 单独圆角，小尺寸的边角才干净。"""
    resample = getattr(Image, resample, Image.LANCZOS)
    frames = {}
    for s in sizes:
        f = master.resize((s, s), resample)
        if rounded:
            f = apply_rounded(f, round_ratio)
        frames[s] = f
    return frames


def save_ico(frames, path):
    """写多尺寸 ICO。

    优先用 append_images 把每档自己的图塞进去（保留逐档的圆角与重采样）；
    老版本 Pillow 没有这个参数，退回 sizes 由库自己缩。
    """
    sizes = sorted(frames)
    biggest = frames[sizes[-1]]
    rest = [frames[s] for s in sizes[:-1]]
    size_pairs = [(s, s) for s in sizes]
    try:
        biggest.save(path, format="ICO", sizes=size_pairs, append_images=rest)
    except (TypeError, ValueError):
        biggest.save(path, format="ICO", sizes=size_pairs)
    return path


# ================================================================ 预览
def make_preview(source, out_path, sizes=None, bg_dark=True):
    """按**真实像素**并排画出各档图标，浅底一行、深底一行。

    这是判断"小尺寸能不能看"的唯一靠谱办法 —— 光看 256 的 PNG 会误判。
    """
    sizes = sizes or STANDARD_SIZES
    frames = {}
    if isinstance(source, dict):
        frames = dict(source)
    else:
        img = Image.open(source)
        ico = getattr(img, "ico", None)          # ICO 专属：能按尺寸精确取帧
        avail = set(p[0] for p in (img.info.get("sizes") or []))
        for s in sizes:
            if avail and s not in avail:
                continue
            try:
                if ico is not None:
                    frames[s] = Image.open(io.BytesIO(ico.frame((s, s)))).convert("RGBA")
                else:
                    frames[s] = img.convert("RGBA").resize((s, s), Image.LANCZOS)
            except Exception:
                continue                          # 某一档取不到就跳过，不整体失败
        if not frames:
            frames[sizes[-1]] = img.convert("RGBA")

    pad, label_h = 20, 34
    biggest = max(frames)
    row_h = biggest + label_h
    width = pad * 2 + sum(frames) + 10 * (len(frames) - 1)

    canvas = Image.new("RGBA", (width, row_h * 2), (245, 245, 245, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, width, row_h], fill=(242, 242, 242, 255))
    d.rectangle([0, row_h, width, row_h * 2], fill=(38, 38, 38, 255))

    x = pad
    for s in sorted(frames):
        f = frames[s]
        canvas.paste(f, (x, pad + (biggest - f.size[1]) // 2), f)
        canvas.paste(f, (x, row_h + pad + (biggest - f.size[1]) // 2), f)
        d.text((x, biggest + 6), "%dpx" % s, fill=(80, 80, 80, 255))
        d.text((x, row_h + biggest + 6), "%dpx" % s, fill=(200, 200, 200, 255))
        x += f.size[0] + 10

    canvas.convert("RGB").save(out_path, "PNG")
    return out_path


# ================================================================ 自检
def verify_ico(path):
    """读回 ICO 的尺寸清单。System.Drawing 只报它挑中的一档，不能用来判断完整性。"""
    with Image.open(path) as im:
        sizes = sorted(im.info.get("sizes") or [])
    have = set(p[0] for p in sizes)
    missing = [s for s in STANDARD_SIZES if s not in have]
    return {
        "path": path,
        "size_bytes": os.path.getsize(path),
        "sizes": ["%dx%d" % p for p in sizes],
        "missing_standard": missing,
        "ok": len(missing) == 0,
    }


# ================================================================ make
def cmd_make(args):
    warnings = []
    im = open_any(args.src)
    info = analyze(im)

    out_dir = args.out or DEFAULT_OUT
    os.makedirs(out_dir, exist_ok=True)
    name = args.name or os.path.splitext(os.path.basename(args.src))[0] or "icon"

    # ---- 背景处理
    if args.bg == "transparent":
        im, ok = strip_background(im)
        if ok:
            info["has_alpha"] = True
            info["background_stripped"] = True
        else:
            warnings.append("找不到安全的哨兵色，抠背景被跳过，保留原背景。")

    # ---- 裁不裁：这是踩过坑的核心决策
    crop_mode = args.crop
    if crop_mode == "auto":
        crop_mode = "none" if info["low_res"] else "square"
    if crop_mode == "square":
        im = crop_square(im, margin=args.margin)
    # crop_mode == "none" 时原样保留（非正方形也行，后续居中补边）

    if crop_mode == "none" and im.size[0] != im.size[1]:
        # 非正方形又决定不裁：居中垫成正方形，绝不拉伸变形
        w, h = im.size
        side = max(w, h)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(im, ((side - w) // 2, (side - h) // 2), im)
        im = square
        warnings.append("源图非正方形且指定不裁切，已居中垫成正方形（不改变比例）。")

    side = min(im.size)
    if side < 256:
        warnings.append(
            "源图有效边长仅 %dpx，256 档是放大的。16/24px 档基本不可用，交付时要说明。" % side
        )

    # ---- 缩放到 256 母版
    master = im.resize((256, 256), getattr(Image, info["resample"]))

    # ---- 生成
    produced = []
    rounded = args.mode in ("round", "both")
    frames = build_frames(master, STANDARD_SIZES, info["resample"], rounded, args.round_ratio)
    ico_round = os.path.join(out_dir, name + "-round.ico")
    save_ico(frames, ico_round)
    produced.append(ico_round)
    preview_frames = frames

    if args.mode in ("square", "both"):
        flat = build_frames(master, STANDARD_SIZES, info["resample"], False, args.round_ratio)
        ico_square = os.path.join(out_dir, name + "-square.ico")
        save_ico(flat, ico_square)
        produced.append(ico_square)
        if args.mode == "square":
            preview_frames = flat

    png_path = os.path.join(out_dir, name + ".png")
    master.save(png_path, "PNG")
    produced.append(png_path)

    # ---- 预览
    preview_path = None
    if args.preview:
        preview_path = os.path.join(out_dir, name + "-sizes.png")
        make_preview(preview_frames, preview_path)
        produced.append(preview_path)

    # ---- 自检
    checks = []
    for p in produced:
        if p.lower().endswith(".ico"):
            checks.append(verify_ico(p))

    report = {
        # ok 只反映"生成是否合格"；warnings 是提示，不影响 ok
        "ok": all(c["ok"] for c in checks) if checks else True,
        "source": {
            "path": os.path.abspath(args.src),
            "info": info,
        },
        "strategy": {
            "crop": crop_mode,
            "mode": args.mode,
            "resample": info["resample"],
            "bg": args.bg,
            "round_ratio": args.round_ratio,
        },
        "produced": produced,
        "ico_checks": checks,
        "warnings": warnings,
        "advice": advise(info),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    bad = [c for c in checks if not c["ok"]]
    return 3 if bad else 0


# ================================================================ 入口
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Windows 图标生成引擎（windows-icon-maker 技能配套脚本）"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    a1 = sub.add_parser("analyze", help="只看源图，不产出文件")
    a1.add_argument("src")

    a2 = sub.add_parser("make", help="生成多尺寸 ICO")
    a2.add_argument("src")
    a2.add_argument("--out", default=None, help="输出目录，默认 %s" % DEFAULT_OUT)
    a2.add_argument("--name", default=None, help="产物文件名前缀")
    a2.add_argument("--mode", choices=["round", "square", "both"], default="both",
                    help="圆角/方角/两者都出（默认 both）")
    a2.add_argument("--bg", choices=["keep", "transparent"], default="keep",
                    help="是否把四边连通纯色背景抠成透明")
    a2.add_argument("--crop", choices=["auto", "square", "none"], default="auto",
                    help="auto：大图居中裁正方形，小于 256 的小图不裁")
    a2.add_argument("--margin", type=float, default=0.0,
                    help="裁切时向内收的比例，0~0.3，给图标留白")
    a2.add_argument("--round-ratio", type=float, default=ROUND_RATIO,
                    help="圆角半径占边长比例，默认 0.22")
    a2.add_argument("--preview", action="store_true", help="同时生成尺寸对比图")
    a2.add_argument("--json", action="store_true", help="输出 JSON（默认已经是 JSON）")

    a3 = sub.add_parser("preview", help="给已有 ICO 生成尺寸对比图")
    a3.add_argument("src")
    a3.add_argument("--out", default=None)

    a4 = sub.add_parser("verify", help="核对 ICO 内含尺寸")
    a4.add_argument("src")

    args = ap.parse_args(argv)

    try:
        if args.cmd == "analyze":
            im = open_any(args.src)
            info = analyze(im)
            print(json.dumps(
                {"source": args.src, "info": info, "advice": advise(info)},
                ensure_ascii=False, indent=2))
            return 0

        if args.cmd == "make":
            return cmd_make(args)

        if args.cmd == "preview":
            out = args.out or os.path.join(
                os.path.dirname(os.path.abspath(args.src)),
                os.path.splitext(os.path.basename(args.src))[0] + "-sizes.png")
            p = make_preview(args.src, out)
            print(json.dumps({"ok": True, "preview": p}, ensure_ascii=False, indent=2))
            return 0

        if args.cmd == "verify":
            r = verify_ico(args.src)
            print(json.dumps(r, ensure_ascii=False, indent=2))
            return 0 if r["ok"] else 3

    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "error": "%s: %s" % (type(e).__name__, e),
            "trace": traceback.format_exc(),
        }, ensure_ascii=False, indent=2))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
