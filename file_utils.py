# -*- coding: utf-8 -*-
"""
file_utils.py
==============
公共工具：输入/输出目录管理，以及 GPX 文件的交互式选择。

目录约定（与代码文件同级）：
  input/   存放 .gpx 输入文件（把你的骑行记录放到这里）
  output/  存放生成的视频与图片

三个脚本（gpx_strava_style_animation.py / preview_map_styles.py /
export_route_map.py）都从这里取得目录，并通过 select_gpx() 交互式选择 GPX。
"""

import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(_BASE_DIR, "input")
OUTPUT_DIR = os.path.join(_BASE_DIR, "output")


def ensure_dirs():
    """确保 input/ 与 output/ 目录存在。"""
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def scan_gpx_files():
    """扫描 input/ 下所有 .gpx 文件，返回按文件名排序的绝对路径列表。"""
    if not os.path.isdir(INPUT_DIR):
        return []
    return sorted(
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".gpx")
    )


def select_gpx():
    """交互式选择一个 GPX 文件，返回其绝对路径。

    - 只有一个 .gpx 时直接采用；
    - 有多个时列出清单，让用户输入编号选择。
    """
    files = scan_gpx_files()
    if not files:
        print(f"在输入目录「{INPUT_DIR}」中找不到任何 .gpx 文件。")
        print("请先把 .gpx 文件放到该目录，再重新执行。")
        raise SystemExit(1)

    if len(files) == 1:
        chosen = files[0]
        print(f"检测到 1 个 GPX 文件：{os.path.basename(chosen)}")
        return chosen

    print("检测到以下 GPX 文件，请选择：")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {os.path.basename(f)}")

    while True:
        raw = input("输入编号 (直接按 Enter 默认 1): ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            chosen = files[int(raw) - 1]
            break
        print(f"输入无效「{raw}」，请输入 1 ~ {len(files)} 之间的编号。")

    print(f"已选择：{os.path.basename(chosen)}\n")
    return chosen


def gpx_stem(gpx_path):
    """返回 GPX 文件名（不含目录与 .gpx 扩展名），用于给输出文件加前缀。

    例如 'input/ride_20250727.gpx' -> 'ride_20250727'。
    """
    return os.path.splitext(os.path.basename(gpx_path))[0]
