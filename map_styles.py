# -*- coding: utf-8 -*-
"""
map_styles.py
==============
公共配置：CartoDB API key 与四种地图底图风格定义。

全项目的 CartoDB API key 与地图风格都集中在这里，
要更换 key 或增减地图风格，只需改这一个文件，以下三个脚本会自动套用：

  - gpx_strava_style_animation.py   （动画视频）
  - preview_map_styles.py           （四种底图并排比较）
  - export_route_map.py             （静态成品图）

使用方式：
  from map_styles import CARTO_API_KEY, STYLES, STYLE_ALIASES, MAP_STYLE_OPTIONS, MAP_STYLE
"""

import os

import contextily as cx
from xyzservices import TileProvider

def _load_carto_api_key():
    """读取 CartoDB API key：优先环境变量，其次项目根目录的 .env 文件。"""
    # 1. 环境变量优先
    key = os.environ.get("CARTO_API_KEY")
    if key:
        return key.strip()

    # 2. 项目根目录的 .env 文件
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "CARTO_API_KEY":
                    return v.strip().strip('"').strip("'")
    return None


# ===========================================================
# CartoDB API key
# ===========================================================
# CartoDB 图砖自 2025 起需要 API key 才能下载（申请：https://carto.com/basemaps/apikey/）。
# key 是私人密钥，不要写进代码。请把它写入项目根目录的 .env 文件（已被 .gitignore 忽略）：
#     CARTO_API_KEY=<你的key>
# 或直接设置环境变量 CARTO_API_KEY。三个 CartoDB 底图会自动带上这个 key。
# 使用「无子域名」的 basemaps.cartocdn.com 直连，避开 {s}.basemaps.cartocdn.com 的 SSL 问题。
CARTO_API_KEY = _load_carto_api_key()

if not CARTO_API_KEY:
    print("⚠ 未检测到 CartoDB API key，CartoDB 底图将无法下载。")
    print("  请在项目根目录创建 .env 文件，写入：CARTO_API_KEY=<你的key>")
    print("  （可复制 .env.example 改名为 .env，再填入真实 key；或设置环境变量 CARTO_API_KEY）")


def carto_style(variant, name):
    """建立已带上 CARTO_API_KEY 的 CartoDB 图砖来源（无子域名稳定 URL）。"""
    key_query = f"?key={CARTO_API_KEY}" if CARTO_API_KEY else ""
    return TileProvider({
        "name": name,
        "url": f"https://basemaps.cartocdn.com/{variant}/{{z}}/{{x}}/{{y}}.png{key_query}",
        "attribution": "(C) OpenStreetMap contributors (C) CARTO",
        "html_attribution": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
                            'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        "max_zoom": 20,
    })


# ===========================================================
# 四种地图底图风格
# ===========================================================
# 格式：key -> (short_name, 显示名称, provider)
#   short_name 用于 export_route_map.py 的输出文件名（route_map_<short_name>.png）
#   provider   可直接传给 contextily 的 source 参数
STYLES = {
    "1": ("dark", "CartoDB.DarkMatter（深色）", carto_style("dark_all", "CartoDB.DarkMatter")),
    "2": ("voyager", "CartoDB.Voyager（全彩）", carto_style("rastertiles/voyager", "CartoDB.Voyager")),
    "3": ("positron", "CartoDB.Positron（浅灰白）", carto_style("light_all", "CartoDB.Positron")),
    "4": ("satellite", "Esri.WorldImagery（卫星）", cx.providers.Esri.WorldImagery),
}

# 允许用编号或名字指定风格（给 export_route_map.py 的命令列参数用）
STYLE_ALIASES = {
    "1": "1", "2": "2", "3": "3", "4": "4",
    "dark": "1", "darkmatter": "1", "dark_all": "1",
    "voyager": "2",
    "positron": "3", "light": "3", "light_all": "3",
    "satellite": "4", "esri": "4", "imagery": "4", "worldimagery": "4",
}

# 动画脚本互动菜单用的「编号 -> (显示名称, provider)」对照
MAP_STYLE_OPTIONS = {key: (label, provider) for key, (_short, label, provider) in STYLES.items()}

# 默认底图（动画脚本在「没有互动输入」时套用的默认值）
MAP_STYLE = STYLES["1"][2]
