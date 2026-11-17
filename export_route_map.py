# -*- coding: utf-8 -*-
"""
export_route_map.py
====================
一键生成「不同地图风格」的骑行轨迹成品图（静态高清 PNG）。

跟 gpx_strava_style_animation.py 的「结尾总结画面」类似，但做成独立命令：
  - 框住全程路线 + 真实地图底图
  - 依速度渐层上色的轨迹（快 = 红/黄、慢 = 蓝紫）
  - 起点（绿）/ 终点（红）标记
  - 右下角半透明数据卡（总距离 / 总爬升 / 平均速度 / 总时长）
  - 左上角日期标题

四种地图风格：
  1 / dark        CartoDB.DarkMatter（深色）
  2 / voyager     CartoDB.Voyager（全彩，最接近 Relive / Google Maps）
  3 / positron    CartoDB.Positron（浅灰白，极简）
  4 / satellite   Esri.WorldImagery（真实卫星）

使用方式（在项目目录下执行；GPX 默认交互式从 input/ 目录选择）：
  python export_route_map.py --all                # 一次生成四种风格
  python export_route_map.py voyager              # 只生成全彩风格
  python export_route_map.py 1 --dpi 300          # 生成深色风格、更高解析度
  python export_route_map.py satellite --output my_ride   # 自订文件名（产生 output/my_ride_satellite.png）
  python export_route_map.py --gpx <路径> voyager # 指定 GPX 文件路径（省略则交互式选择）

注意：CartoDB 三个底图需要 API key，key 已写在 map_styles.py 的 CARTO_API_KEY。
"""

import argparse
import os

import gpxpy
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
import contextily as cx
from geopy.distance import geodesic

from file_utils import OUTPUT_DIR, ensure_dirs, select_gpx, gpx_stem

# ===========================================================
# 基本设定
# ===========================================================
GPX_FILENAME = None                    # 默认交互式选择（可用 --gpx 覆盖）
OUTPUT_BASE = "route_map"              # 输出文件名的基础名称（可用 --output 覆盖）
TRACK_CMAP = "plasma"                # 轨迹渐层配色：plasma / turbo / viridis / coolwarm 等
END_PADDING_FRAC = 0.18              # 框住全程时，路线外围的留白比例
SPEED_SMOOTH_WINDOW = 5              # 速度平滑窗口（点数），用于压低 GPS 噪声

# CartoDB API key 与四种地图底图风格已抽到 map_styles.py（改一处全项目生效）。
from map_styles import STYLES, STYLE_ALIASES

# 中文字体设定
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
    "PingFang SC", "WenQuanYi Zen Hei", "Microsoft JhengHei",
    "Noto Sans CJK TC", "PingFang TC", "Heiti TC",
    "Arial Unicode MS", "DejaVu Sans",
]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False


# ===========================================================
# 工具函数
# ===========================================================
def latlon_to_mercator(lat, lon):
    """WGS84 经纬度 -> Web Mercator (EPSG:3857)，用于对齐地图瓦片。"""
    r_major = 6378137.0
    x = r_major * np.radians(lon)
    scale = x / lon
    y = 180.0 / np.pi * np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0)) * scale
    return x, y


def load_route(gpx_filename):
    """解析 GPX，返回 (points, lats, lons, eles, xs, ys, distances, speeds, elevation_gain, total_seconds)。"""
    with open(gpx_filename, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append({
                    "lat": pt.latitude,
                    "lon": pt.longitude,
                    "ele": pt.elevation if pt.elevation else 0.0,
                    "time": pt.time,
                })

    if len(points) < 2:
        raise ValueError("GPX 轨迹点数量不足，无法产生成品图。")

    lats = np.array([p["lat"] for p in points])
    lons = np.array([p["lon"] for p in points])
    eles = np.array([p["ele"] for p in points])
    xs, ys = latlon_to_mercator(lats, lons)

    distances = [0.0]
    speeds = [0.0]
    elevation_gain = [0.0]
    for i in range(1, len(points)):
        p1 = (points[i - 1]["lat"], points[i - 1]["lon"])
        p2 = (points[i]["lat"], points[i]["lon"])
        dist_m = geodesic(p1, p2).meters
        distances.append(distances[-1] + dist_m / 1000.0)

        if points[i]["time"] and points[i - 1]["time"]:
            dt = (points[i]["time"] - points[i - 1]["time"]).total_seconds()
            speed_kph = (dist_m / dt) * 3.6 if dt > 0 else 0.0
        else:
            speed_kph = 0.0
        speeds.append(speed_kph)

        ele_diff = eles[i] - eles[i - 1]
        elevation_gain.append(elevation_gain[-1] + (ele_diff if ele_diff > 0 else 0.0))

    speeds = np.array(speeds)
    distances = np.array(distances)
    elevation_gain = np.array(elevation_gain)

    # 速度平滑
    if len(speeds) >= SPEED_SMOOTH_WINDOW:
        speeds = np.convolve(speeds, np.ones(SPEED_SMOOTH_WINDOW) / SPEED_SMOOTH_WINDOW, mode="same")

    total_seconds = None
    if points[0]["time"] and points[-1]["time"]:
        total_seconds = (points[-1]["time"] - points[0]["time"]).total_seconds()

    return points, xs, ys, eles, distances, speeds, elevation_gain, total_seconds


def format_duration(total_seconds):
    if not total_seconds:
        return "N/A"
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    return f"{h}h {m}m"


# ===========================================================
# 成品图绘制
# ===========================================================
def render_route_map(gpx_filename, provider, output_path, dpi=200, track_cmap=TRACK_CMAP):
    points, xs, ys, eles, distances, speeds, elevation_gain, total_seconds = load_route(gpx_filename)

    # 框住全程的范围（正方形取长边 + 留白）
    half_w = (xs.max() - xs.min()) / 2
    half_h = (ys.max() - ys.min()) / 2
    cx0 = (xs.max() + xs.min()) / 2
    cy0 = (ys.max() + ys.min()) / 2
    margin = max(half_w, half_h) * (1 + END_PADDING_FRAC)

    # 速度渐层线段
    segments_xy = np.array([xs, ys]).T.reshape(-1, 1, 2)
    segments = np.concatenate([segments_xy[:-1], segments_xy[1:]], axis=1)
    speed_norm = Normalize(vmin=np.percentile(speeds, 5), vmax=np.percentile(speeds, 95))
    cmap = matplotlib.colormaps[track_cmap]

    fig = plt.figure(figsize=(10, 10), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(cx0 - margin, cx0 + margin)
    ax.set_ylim(cy0 - margin, cy0 + margin)

    # 地图底图
    try:
        cx.add_basemap(ax, crs="EPSG:3857", source=provider)
    except Exception as e:
        print(f"  ⚠ 底图下载失败（{type(e).__name__}），仍会画出轨迹。")

    # 白色底衬线（让彩色轨迹在复杂底图上更醒目）
    ax.add_collection(LineCollection(
        segments, colors="white", linewidth=10, alpha=0.45, zorder=2, capstyle="round",
    ))
    # 依速度渐层的彩色轨迹
    lc = LineCollection(
        segments, cmap=cmap, norm=speed_norm, linewidth=6, zorder=3,
        capstyle="round", alpha=0.95,
    )
    lc.set_array(speeds[1:])
    ax.add_collection(lc)

    # 起点（绿）/ 终点（红）
    ax.plot(xs[0], ys[0], "o", color="#4CAF50", markersize=16,
            markeredgecolor="white", markeredgewidth=2.5, zorder=4)
    ax.plot(xs[-1], ys[-1], "o", color="#FF5722", markersize=16,
            markeredgecolor="white", markeredgewidth=2.5, zorder=4)

    # 左上角日期标题
    if points[0]["time"]:
        date_str = points[0]["time"].strftime("%Y-%m-%d")
        title = f"骑行 · {date_str}"
    else:
        title = "骑行"
    ax.text(0.04, 0.96, title, transform=ax.transAxes, color="white",
            fontsize=24, fontweight="bold", va="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="black", alpha=0.6, edgecolor="none"),
            zorder=6)

    # 右下角数据卡
    avg_speed = distances[-1] / (total_seconds / 3600) if total_seconds else float(np.mean(speeds))
    summary = [
        ("总距离", f"{distances[-1]:.2f} km"),
        ("总爬升", f"{elevation_gain[-1]:.0f} m"),
        ("平均速度", f"{avg_speed:.1f} km/h"),
        ("总时长", format_duration(total_seconds)),
    ]
    card = plt.Rectangle((0.66, 0.03), 0.30, 0.26, transform=ax.transAxes,
                         facecolor="black", edgecolor="none", alpha=0.6, zorder=5)
    ax.add_patch(card)
    y = 0.24
    for label, value in summary:
        ax.text(0.68, y, label, transform=ax.transAxes, color="#DDDDDD",
                fontsize=15, va="center", zorder=6)
        ax.text(0.94, y, value, transform=ax.transAxes, color="#FF7043",
                fontsize=15, fontweight="bold", ha="right", va="center", zorder=6)
        y -= 0.062

    fig.savefig(output_path, facecolor="white", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return output_path


# ===========================================================
# 命令列解析
# ===========================================================
def build_parser():
    parser = argparse.ArgumentParser(
        description="生成不同地图风格的骑行轨迹成品图。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "风格可选编号或名称：\n"
            "  1 / dark        深色\n"
            "  2 / voyager     全彩\n"
            "  3 / positron    浅灰白\n"
            "  4 / satellite   卫星\n\n"
            "范例：\n"
            "  python export_route_map.py --all\n"
            "  python export_route_map.py voyager\n"
            "  python export_route_map.py 1 --dpi 300\n"
        ),
    )
    parser.add_argument(
        "style", nargs="?", default=None,
        help="地图风格（编号或名称，如 voyager / 2 / dark / satellite）。省略且未加 --all 时，默认全彩 voyager。",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="一次生成全部四种风格。",
    )
    parser.add_argument(
        "--gpx", default=None,
        help="GPX 文件路径。省略时交互式选择 input/ 目录下的 .gpx 文件。",
    )
    parser.add_argument(
        "--output", default=OUTPUT_BASE,
        help=f"输出文件名基础名称（默认 {OUTPUT_BASE}），实际文件名为 <output>_<风格>.png。",
    )
    parser.add_argument(
        "--dpi", type=int, default=200,
        help="输出解析度 DPI（默认 200，成品为 2000x2000；调到 300 更清晰但文件较大）。",
    )
    return parser


def resolve_style_keys(args):
    """决定要生成哪些风格，返回 [(short_name, label, provider), ...]。"""
    if args.all:
        return [(short, label, prov) for short, label, prov in STYLES.values()]

    key = (args.style or "voyager").strip().lower()
    key = STYLE_ALIASES.get(key, key)
    if key not in STYLES:
        raise SystemExit(
            f"无法识别的风格「{args.style}」。可用：{' / '.join(sorted(STYLE_ALIASES))}。"
        )
    short, label, prov = STYLES[key]
    return [(short, label, prov)]


def main():
    args = build_parser().parse_args()
    ensure_dirs()

    gpx_path = args.gpx if args.gpx else select_gpx()
    selected = resolve_style_keys(args)

    print(f"GPX 文件：{gpx_path}")
    print(f"准备生成 {len(selected)} 张成品图，输出到 {OUTPUT_DIR} ...\n")

    prefix = gpx_stem(gpx_path)
    for short, label, prov in selected:
        out_path = os.path.join(OUTPUT_DIR, f"{prefix}_{args.output}_{short}.png")
        print(f"  生成 [{label}] -> {out_path} ...")
        render_route_map(gpx_path, prov, out_path, dpi=args.dpi)
        print(f"    ✅ 完成")

    print(f"\n✅ 全部完成，共 {len(selected)} 张成品图。")


if __name__ == "__main__":
    main()
