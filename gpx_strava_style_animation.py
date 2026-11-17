# -*- coding: utf-8 -*-
"""
gpx_strava_style_animation.py
==============================
把 GPX 骑行轨迹渲染成类似 Strava「动态回放」风格的动画视频。

功能：
  1. 真实地图底图（contextily，执行时互动菜单可选深色 / 全彩 / 浅灰白 / 卫星）
  2. 依速度渐层上色的轨迹线（快=红、慢=蓝）
  3. 平滑镜头跟随（依取样点序号推进 + 指数插值，不会跳帧）
  4. 右上角小地图（显示全程路线 + 当前进度点）
  5. 底部海拔剖面图（随时间推进）
  6. 即时 HUD（速度 / 距离 / 海拔）
  7. 结尾镜头平滑 zoom-out 框住全程路线 + 置中数据卡片（总距离、总爬升、均速、总时长）

前置依赖安装：
  pip install gpxpy matplotlib geopy contextily moviepy pillow numpy

使用方式：
  1. 把你的 GPX 文件放到 input/ 目录（可放多个）
  2. 依需求调整下方 CONFIG 区块的参数
  3. 执行：python gpx_strava_style_animation.py
  4. 执行后先选择要用的 GPX 文件，再现场选择地图底图风格
  5. 生成的视频输出到 output/ 目录

注意：
  - contextily 下载地图底图需要网络连接，请确保本机可连外网（可存取
    basemaps.cartocdn.com / server.arcgisonline.com 等图砖服务器）。
  - 若 GPX 内没有时间戳记，速度会退化为以等时间间隔估算。
  - 动画播放进度是依「轨迹点序号」对应动画时间（idx = t/VIDEO_DURATION * 总点数），
    不是依实际经过秒数内插；若 GPX 取样间隔很不均匀（例如红灯久停、信号漂移），
    画面移动速度可能会忽快忽慢。
  - 本版已针对 moviepy 2.x（`moviepy.editor` 模块已移除）与
    matplotlib 3.11 即将移除的 `cm.get_cmap` 做兼容性修正。
"""

import os

import gpxpy
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
import contextily as cx
from geopy.distance import geodesic
from moviepy import VideoClip  # moviepy >= 2.0：不再有 moviepy.editor 子模块

from map_styles import MAP_STYLE, MAP_STYLE_OPTIONS
from file_utils import OUTPUT_DIR, ensure_dirs, select_gpx, gpx_stem

# ===========================================================
# CONFIG 区块：依需求调整
# ===========================================================
VIEW_MARGIN = 800        # 主镜头视角半径（公尺），数字越小放大越多
CAMERA_SMOOTH = 0.15     # 镜头平滑系数 (0~1)：越小镜头越「黏」、跟得越慢但越丝滑；
                         # 越大镜头反应越快但容易感觉在抖动。建议 0.08~0.2 之间微调。
VIDEO_DURATION = 20      # 动画主体秒数（不含结尾）：这个数字越大，播放速度越「慢」
                         # （全程被拉得更长）；越小则整趟骑乘被压缩得越快。
ZOOM_OUT_DURATION = 2.5  # 骑乘结束后，镜头平滑拉远到「框住全程路线」所花的秒数
END_HOLD_DURATION = 4    # 镜头定格在全程路线画面、叠加数据卡片的停留秒数
END_PADDING_FRAC = 0.18  # 结尾拉远时，路线外围留白比例（0.18 = 外围多留 18% 空间）
FPS = 24                 # 每秒帧数：数字越高动作越滑顺，但渲染时间也等比增加。
                         # 因为已改成依真实时间内插座标，FPS 30~60 会比 24 明显更滑顺。

# 地图底图风格：执行程序时会出现互动菜单让你现场选，这里的值只是「没有互动输入时」的默认值。
#   1 = CartoDB.DarkMatter   深色，彩色轨迹对比最强
#   2 = CartoDB.Voyager      全彩，最接近 Relive / Google Maps 质感
#   3 = CartoDB.Positron     浅灰白，极简
#   4 = Esri.WorldImagery    真实卫星空拍图
# 不确定选哪个，可以先跑 preview_map_styles.py 产生四种底图的并排比较图再决定。

TRACK_CMAP = "plasma"    # 轨迹渐层配色：plasma / turbo / viridis / coolwarm 等


def choose_map_style():
    """执行程序时跳出的互动菜单，现场选择地图底图风格。"""
    print("\n请选择地图底图风格：")
    for key, (label, _) in MAP_STYLE_OPTIONS.items():
        print(f"  {key}. {label}")
    choice = input(f"输入编号 (直接按 Enter 默认 1): ").strip() or "1"
    if choice not in MAP_STYLE_OPTIONS:
        print(f"输入无效「{choice}」，改用默认 1。")
        choice = "1"
    label, provider = MAP_STYLE_OPTIONS[choice]
    print(f"已选择：{label}\n")
    return provider


# 中文字体设定：默认英文字体不含中文字，会显示成方框。
# 依序尝试常见的中文字体，找到第一个系统里有的就套用。
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
    "PingFang SC", "WenQuanYi Zen Hei", "Microsoft JhengHei",
    "Noto Sans CJK TC", "PingFang TC", "Heiti TC",
    "Arial Unicode MS", "DejaVu Sans",
]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False


# ===========================================================
# 0. moviepy 2.x 兼容：手动实现 fig -> numpy frame 的转换
#    （旧版 moviepy.video.io.bindings.mplfig_to_npimage 已被移除）
# ===========================================================
def mplfig_to_npimage(fig):
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())
    return buf[:, :, :3]  # 丢弃 alpha channel，返回 RGB


def latlon_to_mercator(lat, lon):
    """WGS84 经纬度 -> Web Mercator (EPSG:3857)，用于对齐地图瓦片。"""
    r_major = 6378137.0
    x = r_major * np.radians(lon)
    scale = x / lon
    y = 180.0 / np.pi * np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0)) * scale
    return x, y


# ===========================================================
# 渲染状态（模块级变量，由 setup_route 初始化，供各帧函数共用）
# ===========================================================
xs = ys = eles = speeds = distances = elevation_gain = None
total_seconds = None
TOTAL_POINTS = 0
segments = None
speed_norm = None
cmap = None
ROUTE_CENTER_X = ROUTE_CENTER_Y = FIT_MARGIN = 0.0
fig = ax_main = ax_mini = ax_elev = None
camera_x = camera_y = 0.0


def setup_route(gpx_filename):
    """解析 GPX，计算距离/速度/爬升，并初始化绘图对象与镜头状态。"""
    global xs, ys, eles, speeds, distances, elevation_gain
    global total_seconds, TOTAL_POINTS, segments, speed_norm, cmap
    global ROUTE_CENTER_X, ROUTE_CENTER_Y, FIT_MARGIN
    global fig, ax_main, ax_mini, ax_elev, camera_x, camera_y

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
        raise ValueError("GPX 轨迹点数量不足，无法产生动画。")

    lats = np.array([p["lat"] for p in points])
    lons = np.array([p["lon"] for p in points])
    eles = np.array([p["ele"] for p in points])
    xs, ys = latlon_to_mercator(lats, lons)

    # 全程路线的 bounding box，结尾 zoom-out 要用这个算出「框住全程」的镜头范围
    _route_half_w = (xs.max() - xs.min()) / 2
    _route_half_h = (ys.max() - ys.min()) / 2
    ROUTE_CENTER_X = (xs.max() + xs.min()) / 2
    ROUTE_CENTER_Y = (ys.max() + ys.min()) / 2
    # 用正方形窗口框住整条路线（取长边），并加上留白比例
    FIT_MARGIN = max(_route_half_w, _route_half_h) * (1 + END_PADDING_FRAC)

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

    # 速度平滑，避开 GPS 噪声 / 停等红灯时的 0 值跳动
    if len(speeds) >= 5:
        speeds = np.convolve(speeds, np.ones(5) / 5, mode="same")

    # 总时长（若有时间戳记）
    if points[0]["time"] and points[-1]["time"]:
        total_seconds = (points[-1]["time"] - points[0]["time"]).total_seconds()
    else:
        total_seconds = None

    TOTAL_POINTS = len(points)

    # 建立速度渐层轨迹的线段集合（LineCollection）
    segments_xy = np.array([xs, ys]).T.reshape(-1, 1, 2)
    segments = np.concatenate([segments_xy[:-1], segments_xy[1:]], axis=1)
    speed_norm = Normalize(vmin=np.percentile(speeds, 5), vmax=np.percentile(speeds, 95))
    cmap = matplotlib.colormaps[TRACK_CMAP]  # cm.get_cmap 在 3.11 会被移除，改用新 API

    # 绘图对象
    fig = plt.figure(figsize=(10, 10), dpi=100)
    ax_main = fig.add_axes([0, 0, 1, 1])              # 主地图，满版
    ax_mini = fig.add_axes([0.70, 0.72, 0.26, 0.26])  # 右上角小地图
    ax_elev = fig.add_axes([0.06, 0.04, 0.55, 0.14])  # 底部海拔剖面

    # 镜头平滑用的状态（跨帧累积）
    camera_x, camera_y = xs[0], ys[0]


def draw_gradient_track(ax, end_idx, linewidth=4, zorder=3):
    """画出到 end_idx 为止、依速度上色的渐层轨迹。"""
    if end_idx < 1:
        return
    lc = LineCollection(
        segments[:end_idx],
        cmap=cmap,
        norm=speed_norm,
        linewidth=linewidth,
        zorder=zorder,
        alpha=0.95,
    )
    lc.set_array(speeds[1:end_idx + 1])
    ax.add_collection(lc)


def update_scene(idx):
    global camera_x, camera_y

    # --- 镜头平滑跟随（指数插值，避免跳帧）---
    target_x, target_y = xs[idx], ys[idx]
    camera_x += (target_x - camera_x) * CAMERA_SMOOTH
    camera_y += (target_y - camera_y) * CAMERA_SMOOTH

    # --- 主地图 ---
    ax_main.clear()
    ax_main.axis("off")
    ax_main.set_xlim(camera_x - VIEW_MARGIN, camera_x + VIEW_MARGIN)
    ax_main.set_ylim(camera_y - VIEW_MARGIN, camera_y + VIEW_MARGIN)
    try:
        cx.add_basemap(ax_main, crs="EPSG:3857", source=MAP_STYLE)
    except Exception:
        pass  # 无网络时跳过底图，仍可看到轨迹

    draw_gradient_track(ax_main, idx, linewidth=5, zorder=3)
    ax_main.plot(
        target_x, target_y, "o", color="white", markersize=11,
        markeredgecolor="#FF5722", markeredgewidth=3, zorder=4,
    )

    # HUD 文字
    hud_text = (
        f"速度：{speeds[idx]:.1f} km/h\n"
        f"距离：{distances[idx]:.2f} km\n"
        f"海拔：{eles[idx]:.0f} m  (+{elevation_gain[idx]:.0f} m)"
    )
    ax_main.text(
        0.05, 0.90, hud_text, transform=ax_main.transAxes,
        color="white", fontsize=15, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="black", alpha=0.6, edgecolor="none"),
        zorder=5,
    )

    # --- 右上角小地图：整体路线 + 当前进度点 ---
    ax_mini.clear()
    ax_mini.axis("off")
    ax_mini.set_facecolor("none")
    pad = (xs.max() - xs.min()) * 0.1 + 1
    ax_mini.set_xlim(xs.min() - pad, xs.max() + pad)
    ax_mini.set_ylim(ys.min() - pad, ys.max() + pad)
    ax_mini.plot(xs, ys, color="white", linewidth=1.2, alpha=0.5, zorder=1)
    ax_mini.plot(xs[:idx + 1], ys[:idx + 1], color="#FF5722", linewidth=2, zorder=2)
    ax_mini.plot(target_x, target_y, "o", color="#FF5722", markersize=6, zorder=3)
    for spine in ax_mini.spines.values():
        spine.set_visible(False)

    # --- 底部海拔剖面 ---
    ax_elev.clear()
    ax_elev.set_facecolor("none")
    ax_elev.fill_between(distances[:idx + 1], eles[:idx + 1], color="#FF5722", alpha=0.35)
    ax_elev.plot(distances[:idx + 1], eles[:idx + 1], color="#FF5722", linewidth=1.5)
    ax_elev.set_xlim(distances.min(), distances.max())
    ax_elev.set_ylim(eles.min() - 5, eles.max() + 5)
    ax_elev.axis("off")


def ease_smoothstep(p):
    """0~1 的平滑缓动曲线，让镜头拉远的加减速看起来自然，不是等速生硬地移动。"""
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def render_end_scene(progress, card_alpha):
    """
    骑乘结束后的收尾画面：镜头从最后跟随位置，平滑拉远到框住全程路线，
    地图背景与完整彩色轨迹保留（不切换成纯黑卡片），
    再叠加一张置中的半透明数据卡片（总距离/总爬升/均速/总时长）。

    progress   : 0~1，镜头从「骑乘结束时的位置」过渡到「全程 fit 视角」的进度
    card_alpha : 0~1，数据卡片淡入的透明度
    """
    eased = ease_smoothstep(progress)

    # 镜头中心与视角半径：从骑乘结束时的相机位置，内插到全程路线的中心与 fit 半径
    view_x = camera_x + (ROUTE_CENTER_X - camera_x) * eased
    view_y = camera_y + (ROUTE_CENTER_Y - camera_y) * eased
    view_margin = VIEW_MARGIN + (FIT_MARGIN - VIEW_MARGIN) * eased

    # 收尾画面不需要右上角小地图与底部海拔剖面，全部隐藏，让主画面干净
    ax_mini.set_visible(False)
    ax_elev.set_visible(False)

    ax_main.clear()
    ax_main.axis("off")
    ax_main.set_xlim(view_x - view_margin, view_x + view_margin)
    ax_main.set_ylim(view_y - view_margin, view_y + view_margin)
    try:
        cx.add_basemap(ax_main, crs="EPSG:3857", source=MAP_STYLE)
    except Exception:
        pass

    # 画出完整彩色渐层轨迹
    draw_gradient_track(ax_main, TOTAL_POINTS - 1, linewidth=5, zorder=3)

    # 起点（绿）／终点（红）标记
    ax_main.plot(xs[0], ys[0], "o", color="#4CAF50", markersize=12,
                 markeredgecolor="white", markeredgewidth=2, zorder=4)
    ax_main.plot(xs[-1], ys[-1], "o", color="#FF5722", markersize=12,
                 markeredgecolor="white", markeredgewidth=2, zorder=4)

    if card_alpha > 0.01:
        avg_speed = distances[-1] / (total_seconds / 3600) if total_seconds else np.mean(speeds)
        duration_str = (
            f"{int(total_seconds // 3600)}h {int((total_seconds % 3600) // 60)}m"
            if total_seconds else "N/A"
        )
        summary_lines = [
            ("总距离", f"{distances[-1]:.2f} km"),
            ("总爬升", f"{elevation_gain[-1]:.0f} m"),
            ("平均速度", f"{avg_speed:.1f} km/h"),
            ("总时长", duration_str),
        ]

        # 置中大卡片：半透明深色底 + 白色标题 + 数据（两栏居中，不溢出）
        card = plt.Rectangle(
            (0.24, 0.30), 0.52, 0.42, transform=ax_main.transAxes,
            facecolor="black", edgecolor="none", alpha=0.55 * card_alpha, zorder=5,
        )
        ax_main.add_patch(card)

        # 标题（卡片内偏上，水平居中）
        ax_main.text(0.5, 0.62, "骑行总结", color="white", fontsize=26,
                     fontweight="bold", ha="center", va="center",
                     alpha=card_alpha, transform=ax_main.transAxes, zorder=6)

        # 数据行：label 右对齐到中轴左侧，value 左对齐到中轴右侧，
        # 让 value 左边缘对齐、整体水平居中，且所有行都落在卡片内。
        y = 0.54
        for label, value in summary_lines:
            ax_main.text(0.46, y, label, color="#DDDDDD", fontsize=18,
                         ha="right", va="center", alpha=card_alpha,
                         transform=ax_main.transAxes, zorder=6)
            ax_main.text(0.54, y, value, color="#FF7043", fontsize=18,
                         fontweight="bold", ha="left", va="center", alpha=card_alpha,
                         transform=ax_main.transAxes, zorder=6)
            y -= 0.05


# ===========================================================
# 4. 产生动画帧并导出 MP4
# ===========================================================
def make_frame(t):
    if t < VIDEO_DURATION:
        idx = int((t / VIDEO_DURATION) * (TOTAL_POINTS - 1))
        idx = min(idx, TOTAL_POINTS - 1)
        update_scene(idx)
    else:
        t2 = t - VIDEO_DURATION
        zoom_progress = t2 / ZOOM_OUT_DURATION if ZOOM_OUT_DURATION > 0 else 1.0
        # 镜头拉远到定位后，才开始让数据卡淡入（最后 1 秒淡入完成）
        card_alpha = ease_smoothstep((zoom_progress - 0.6) / 0.4)
        render_end_scene(zoom_progress, card_alpha)
    return mplfig_to_npimage(fig)


if __name__ == "__main__":
    ensure_dirs()
    gpx_path = select_gpx()          # 交互式选择 input/ 下的 GPX 文件
    setup_route(gpx_path)

    MAP_STYLE = choose_map_style()   # 执行时互动选择地图底图风格

    output_path = os.path.join(OUTPUT_DIR, f"{gpx_stem(gpx_path)}_ride_animation.mp4")
    print("🎥 开始渲染动画（含地图 / 渐层轨迹 / HUD / 结尾 zoom-out 总结）...")
    total_duration = VIDEO_DURATION + ZOOM_OUT_DURATION + END_HOLD_DURATION
    clip = VideoClip(make_frame, duration=total_duration)
    clip.write_videofile(output_path, fps=FPS)
    plt.close(fig)
    print(f"✅ 完成！已保存为 {output_path}")
