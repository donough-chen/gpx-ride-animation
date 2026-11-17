# -*- coding: utf-8 -*-
"""
preview_map_styles.py
======================
一次产生「同一个画面、四种候选底图」的并排比较图，
用来快速决定 gpx_strava_style_animation.py 要用哪个 MAP_STYLE，
不用把整支动画渲染 4 遍。

使用方式：
  1. 把 GPX 文件放到 input/ 目录
  2. 执行：python preview_map_styles.py
  3. 交互式选择 GPX 后，产生 output/map_style_comparison.png，四宫格分别是：
     DarkMatter（深色） / Voyager（全彩） / Positron（浅灰白） / WorldImagery（卫星）

注意：跟主程序一样，contextily 下载底图需要网络连接。
"""

import os

import gpxpy
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
import contextily as cx

from file_utils import OUTPUT_DIR, ensure_dirs, select_gpx, gpx_stem
from map_styles import STYLES

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
    "PingFang SC", "WenQuanYi Zen Hei", "Microsoft JhengHei",
    "Noto Sans CJK TC", "PingFang TC", "Heiti TC",
    "Arial Unicode MS", "DejaVu Sans",
]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False

# 确保目录存在，并交互式选择 input/ 下的 GPX 文件
ensure_dirs()
gpx_filename = select_gpx()
OUTPUT = os.path.join(OUTPUT_DIR, f"{gpx_stem(gpx_filename)}_map_style_comparison.png")

# ---- 解析 GPX，只需要经纬度 ----
with open(gpx_filename, "r", encoding="utf-8") as f:
    gpx = gpxpy.parse(f)

points = [pt for trk in gpx.tracks for seg in trk.segments for pt in seg.points]
lats = np.array([p.latitude for p in points])
lons = np.array([p.longitude for p in points])


def latlon_to_mercator(lat, lon):
    r_major = 6378137.0
    x = r_major * np.radians(lon)
    scale = x / lon
    y = 180.0 / np.pi * np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0)) * scale
    return x, y


xs, ys = latlon_to_mercator(lats, lons)

# ---- 取路线中段一小段范围当作比较用的取景（比整条路线放大一点，比较看得出底图细节） ----
mid = len(xs) // 2
window = 60  # 取中段前后各 60 个点
lo, hi = max(0, mid - window), min(len(xs), mid + window)
cx_, cy_ = xs[mid], ys[mid]
margin = max(200, (xs[lo:hi].max() - xs[lo:hi].min()) * 0.7)

CANDIDATES = [(label, provider) for (_short, label, provider) in STYLES.values()]

fig, axes = plt.subplots(2, 2, figsize=(12, 12), dpi=100)
axes = axes.flatten()

segments_xy = np.array([xs, ys]).T.reshape(-1, 1, 2)
segments = np.concatenate([segments_xy[:-1], segments_xy[1:]], axis=1)
norm = Normalize(vmin=0, vmax=len(segments))

for ax, (label, provider) in zip(axes, CANDIDATES):
    ax.set_xlim(cx_ - margin, cx_ + margin)
    ax.set_ylim(cy_ - margin, cy_ + margin)
    ax.axis("off")
    try:
        cx.add_basemap(ax, crs="EPSG:3857", source=provider)
        ok = True
    except Exception as e:
        ok = False
        ax.text(0.5, 0.5, f"底图下载失败\n(需要网络连接)", transform=ax.transAxes,
                 ha="center", va="center", fontsize=11, color="red")

    lc = LineCollection(segments, cmap="plasma", norm=norm, linewidth=4, alpha=0.95, zorder=3)
    lc.set_array(np.arange(len(segments)))
    ax.add_collection(lc)
    ax.set_title(label, fontsize=13, fontweight="bold")

plt.tight_layout()
plt.savefig(OUTPUT, facecolor="white")
print(f"✅ 完成！四种底图比较图已存成 {OUTPUT}，打开看看喜欢哪个，"
      f"再把选好的 provider 填回 gpx_strava_style_animation.py 的 MAP_STYLE。")
