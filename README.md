# Dive Seabed Sandbox 潜水潜点海底3D沙盘

## 启动
```
python -m http.server 8000      # 在本目录执行
```
浏览器打开 http://localhost:8000 （不要直接双击 index.html，file:// 下浏览器会拦截本地文件读取）。

## 目录
```
index.html                 单文件主程序
heightmaps/[spotId].png    高程灰度图：白 = 浅，黑 = 深，最大 1024×1024
data/[spotId].json         潜点配置（markers / zones / seasonCurrents）
data/index.json            潜点清单（可选；没有时用 index.html 里的 CONFIG.defaultSpots）
assets/icons/*.svg         entry / anchor / view / warning 图标
libs/                      Three.js r160 本地副本（可选；存在则优先使用，删除后自动走 CDN）
textures/[spotId].jpg      本地卫星影像贴图（可选）
raw/                       从公开数据源取回的原始数据（卫星缩略图、GEBCO 裁剪、洋流季节统计）
tools/build_real_spots.py  把 raw/ 转成 heightmaps 与 data 的脚本
```

## 新增一个潜点
1. 放入 `heightmaps/xxx.png` 和 `data/xxx.json`；
2. 在 `data/index.json` 的 `spots` 里加一行 `{"spotId":"xxx","name":"显示名"}`。

JSON 在约定结构之外有几个**可选**字段：
- `bounds`: `{west, east, south, north}` 高程图覆盖的经纬度范围。缺省时用所有点位的外包矩形外扩 15%。
- `depthRange`: `{min, max}` 白色与黑色分别对应的深度（米）。`min` 为负表示露出水面。缺省为 0 ~ 40。
- `depthBands`: `[{type, from, to, label, note}]` 按深度自动着色的区域带，可与手绘 `zones` 并存。
- `source`: 数据来源说明，显示在左上角。

## 在线图层
`index.html` 顶部的 `API_CONFIG` 是唯一需要改的地方：换地址改 `currentsUrl / tideUrl`，换数据格式改 `parseCurrents / parseTide`；`enabled:false` 可完全关闭联网。

## 真实数据潜点（sipadan / mabul）
- **礁盘轮廓、岛屿位置**：来自 Sentinel-2 卫星影像（2025 年合成图，10 m 分辨率），是真实的。
- **浅水深度**：按影像亮度估算（越亮越浅，约 1–18 m），没有用实测深度校准，只是量级参考。
- **看不见海底的深水**：诗巴丹按“礁缘外即断崖”的假设快速降到封顶深度；马布用 GEBCO_2020（约 460 m 网格）的陆架深度衔接。
- **深度封顶 40 m**（休闲潜水极限）：更深处统一画成 40 m 平底。
- **区域**：`depthBands` 按深度自动着色 —— 0–18 m 绿、18–30 m 黄、30 m 以深红。这是深度分带，不是安全评估。
- **季节洋流**：Open-Meteo 海洋模型 2022-01 ~ 2026-10 的逐时表层流统计。模型约 8 km 一个格点，全图箭头相同；旱季按 4–10 月、雨季按 11–3 月划分。
- 真实潜点位置（入水点、观景点等）没有标注，需要自己往 `markers` 里加。
- `demo-wall` / `demo-slope` 是程序生成的合成地形，只用来演示标记、手绘区域等功能。

## 写实模式与卫星贴图
- 「写实模式」完全由程序生成（沙地 / 礁石斑块、水体吸收、焦散、水面波纹），不依赖任何图片，断网可用。它只改变观感，不增加地形精度。
- 「卫星影像贴图」加载顺序：本地 `textures/[spotId].jpg` → 浏览器缓存里上次下载的高清图 → 在线下载（8 秒超时，失败不提示）。
- 自己加贴图：把与 `bounds` 范围完全一致、上北下南的图片存成 `textures/[spotId].jpg` 即可。
- 默认图源 Sentinel-2 cloudless（EOX）许可为 CC BY-NC-SA 4.0：非商用、需署名。换图源改 `index.html` 顶部的 `SATELLITE_CONFIG`。

## 潜水视角（水下第一人称）
- 入口：控制面板 →「潜水视角」→ 在地形上点一下选入水位置（点到陆地或太深的地方会自动挪到最近的合适位置）。
- 操作：拖动画面转头；左下方向键移动，右下按钮升降；键盘 W/A/S/D 移动、E/Q 升降、Esc 退出。
- 这个模式下地形按 1:1 真实比例显示，雾浓度滑块相当于能见度（约 12–60 m）。
- 海底形状来自估算数据，没有真实的珊瑚和礁石细节，只用来感受地形走势和深度。

## 手机
- 右上角 ☰ 按钮显示 / 隐藏控制面板，手机上默认收起。
- 点左上角标题可展开图例和数据来源说明；点一下标记可弹出备注卡片。

## 说明
本沙盘仅为潜点规划参考，不替代潜导、专业海图、潜水安全评估，不可作为航行与下潜安全依据。
