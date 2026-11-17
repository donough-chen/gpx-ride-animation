# GPX 骑乘动态回放产生器

声明：根据 https://github.com/shao0927/gpx-ride-animation 重构的修改版，感谢原作者。

把 GPX 骑行纪录转成类似 Strava / Relive 的动态回放视频：地图镜头跟随、依速度上色的渐层轨迹、即时 HUD、结尾镜头拉远看全程路线并叠上数据卡。

## 效果

- 真实地图底图（执行时互动菜单：深色 / 全彩 / 浅灰白 / 卫星四选一）
- 轨迹依速度渐层上色（快 = 红、慢 = 蓝紫）
- 镜头平滑跟随骑士位置，不会跳帧
- 右上角小地图：全程路线 + 目前进度
- 底部海拔剖面图
- 结尾镜头平滑拉远，框住全程路线，叠加总距离 / 总爬升 / 均速 / 总时长

## 安装

```bash
pip install -r requirements.txt
```

需要能连网（下载地图底图用）。

> **CartoDB 底图需要 API key**：CartoDB（DarkMatter / Voyager / Positron）自 2025 年起
> 下载图砖必须带 API key。请到 <https://carto.com/basemaps/apikey/> 免费申请，再把 key 写入
> 项目根目录的 `.env` 文件（`CARTO_API_KEY=<你的key>`），或设置环境变量 `CARTO_API_KEY`。
> `.env` 已被 `.gitignore` 忽略、不会提交到仓库；可复制 `.env.example` 再改名为 `.env` 填 key。
> 卫星底图（Esri.WorldImagery）不需要 key，可正常使用。

## 目录结构

```
gpx-ride-animation/
├── input/                          # 放 .gpx 输入文件（可放多个）
├── output/                         # 生成的视频与图片都放这里
├── gpx_strava_style_animation.py   # 生成视频
├── export_route_map.py             # 生成静态成品图
├── preview_map_styles.py           # 四种底图并排比较
├── map_styles.py                   # 底图风格 + API key（公共配置）
└── file_utils.py                   # 输入/输出目录 + GPX 交互式选择（公共工具）
```

## 使用方式

1. 把你的 `.gpx` 文件放到 `input/` 目录（可放多个，执行时选一个）
2. 执行：

```bash
python gpx_strava_style_animation.py
```

执行后会先列出 `input/` 下的 GPX 文件让你选择（只有一个时自动采用），
再跳出地图底图风格菜单让你现场选：

```
请选择地图底图风格：
  1. CartoDB.DarkMatter（深色）
  2. CartoDB.Voyager（全彩）
  3. CartoDB.Positron（浅灰白）
  4. Esri.WorldImagery（卫星）
输入编号 (直接按 Enter 默认 1):
```

生成的视频输出到 `output/<gpx文件名>_ride_animation.mp4`（不同 GPX 各自独立，不会互相覆盖）。

不确定选哪个底图风格？先跑：

```bash
python preview_map_styles.py
```

会产生 `output/<gpx文件名>_map_style_comparison.png`，四种底图同一画面并排比较。

## 生成不同地图风格的成品图（静态图）

想要一张像 Strava 分享图的**静态成品图**（框住全程路线 + 底图 + 速度渐层轨迹 + 起终点 + 数据卡），
且可指定地图风格，用 `export_route_map.py`：

```bash
python export_route_map.py --all              # 一次生成四种风格
python export_route_map.py voyager            # 只生成全彩风格
python export_route_map.py 1 --dpi 300        # 深色风格、更高解析度
python export_route_map.py satellite --output my_ride   # 自定义文件名 → output/<gpx文件名>_my_ride_satellite.png
python export_route_map.py --gpx <路径> dark  # 指定 GPX 路径（省略则交互式选择 input/ 下的）
```

风格参数可用编号或名称：`1/dark`（深色）、`2/voyager`（全彩）、`3/positron`（浅灰白）、`4/satellite`（卫星）。
GPX 默认交互式从 `input/` 选择；输出到 `output/`，默认 2000×2000 的 `output/<gpx文件名>_route_map_<风格>.png`。

## 可调整的参数

都在 `gpx_strava_style_animation.py` 开头的 CONFIG 区块：

| 参数                | 说明                                                   |
| ------------------- | ------------------------------------------------------ |
| `VIEW_MARGIN`       | 主镜头视角半径（公尺），数字越小放大越多               |
| `CAMERA_SMOOTH`     | 镜头平滑系数 (0~1)，越小越黏、越大反应越快但易抖动     |
| `VIDEO_DURATION`    | 动画主体秒数，数字越大播放越慢                         |
| `ZOOM_OUT_DURATION` | 结尾镜头拉远所花的秒数                                 |
| `END_HOLD_DURATION` | 结尾定格 + 数据卡停留秒数                              |
| `FPS`               | 每秒帧数，越高越滑顺但渲染越久                         |
| `TRACK_CMAP`        | 轨迹渐层配色（plasma / turbo / viridis / coolwarm...） |

## 已知限制

- 地图底图下载需要网络连接，若失败会自动跳过底图（轨迹仍会正常画出）
- 动画进度是依「轨迹点序号」对应时间，若 GPX 取样间隔很不均匀（长时间停等），画面移动速度可能忽快忽慢
- 已针对 moviepy 2.x（`moviepy.editor` 已移除）与 matplotlib 3.11 即将移除的 `cm.get_cmap` 做兼容性修正

## 环境

- Python 3.10+
- 见 `requirements.txt`
