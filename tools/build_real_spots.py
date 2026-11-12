"""把 raw/ 里的公开数据转成沙盘用的 heightmaps/*.png、textures/*.jpg 和 data/*.json。
用法（项目根目录）： python tools/build_real_spots.py     依赖：numpy、Pillow、scipy

数据来源
  卫星影像：Sentinel-2 cloudless 2025（EOX，10 m 分辨率），raw/sat/*_thumb.jpg 是缩小到约 12~29 m/像素的缩略图
  深水垫底：GEBCO_2020 全球网格（15 角秒 ≈ 460 m），raw/gebco2020_crops.json（仅马布使用）
  洋流：Open-Meteo Marine API 逐时表层流 2022-01 ~ 2026-10 的季节统计，raw/openmeteo_currents_2022_2026.json
地形怎么来的（重要：这是“由卫星影像推算”的地形，不是测深数据）
  1. 礁盘轮廓、岛屿位置：直接来自卫星影像，是真实的。
  2. 浅水深度：按影像亮度估算 —— 越亮（越青绿）越浅，映射到约 1~18 m。没有用实测深度校准，数值只是量级参考。
  3. 影像里看不见海底的地方：
       诗巴丹 —— 按“礁缘外即断崖”的假设，从礁缘向外很快降到 40 m（GEBCO 在这里位置明显不对，没有采用）；
       马布   —— 用 GEBCO 的陆架深度，并与礁缘平滑衔接。
  4. 深度封顶 DEPTH_CAP = 40 m（休闲潜水极限）：更深的地方一律按 40 m 画成平底。
"""
import json, os
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DEPTH_CAP = 40.0      # 休闲潜水极限深度（米）
LAND_TOP = -5.0       # 露出水面部分最多画到海拔 5 m
OUT = 512             # 输出高度图长边像素
UP = 32               # GEBCO 插值放大倍数
VISIBLE_MAX = 18.0    # 卫星影像里“勉强看得见海底”对应的估算深度（米）

SPOTS = {
    # bounds 必须与 raw/sat 缩略图的取图范围完全一致
    'sipadan': dict(name='诗巴丹 Sipadan（卫星影像推算）', wall=True,
                    bounds=dict(west=118.618, east=118.643, south=4.099, north=4.127)),
    'mabul':   dict(name='马布 Mabul（卫星影像 + GEBCO）', wall=False,
                    bounds=dict(west=118.600, east=118.662, south=4.214, north=4.280)),
}
BANDS = [
    {"type": "good",    "label": "0–18 m 深度带", "from": 0,  "to": 18,   "note": "0–18 m：开放水域（OW）深度范围。深度为估算值，实际以潜水电脑表为准。"},
    {"type": "caution", "label": "18–30 m 深度带", "from": 18, "to": 30,   "note": "18–30 m：进阶（AOW）深度范围。"},
    {"type": "danger",  "label": "30 m 以深", "from": 30, "to": 9999, "note": "30 m 以深。40 m 是休闲潜水极限，本图 40 m 以深不再显示起伏（此处实际可能深达数百米）。"},
]

gebco = json.load(open(os.path.join(ROOT, 'raw', 'gebco2020_crops.json'), encoding='utf-8'))
cur = json.load(open(os.path.join(ROOT, 'raw', 'openmeteo_currents_2022_2026.json'), encoding='utf-8'))
index = []

def gebco_depth(sid, b, size):
    """GEBCO 裁剪 → 与输出同尺寸的深度图（米，向下为正）"""
    g = gebco[sid]
    elev = np.array([[float(v) for v in row.split(',')] for row in g['z'].split(';')], dtype=np.float32)   # 行：南→北
    depth = np.clip(-elev[::-1], LAND_TOP, DEPTH_CAP * 2)      # 翻成北在上；插值前先粗裁，避免几百米深水把岸坡拉变形
    d = g['d']
    big = Image.fromarray(depth, 'F').resize((g['nlon'] * UP, g['nlat'] * UP), Image.BICUBIC)
    W0, N0 = g['lon0'] - d / 2, g['lat0'] + (g['nlat'] - 0.5) * d
    box = ((b['west'] - W0) / d * UP, (N0 - b['north']) / d * UP, (b['east'] - W0) / d * UP, (N0 - b['south']) / d * UP)
    return np.asarray(big.resize(size, Image.BICUBIC, box=box), dtype=np.float32)

for sid, sp in SPOTS.items():
    b = sp['bounds']
    w_m = (b['east'] - b['west']) * 111320 * np.cos(np.radians((b['south'] + b['north']) / 2))
    h_m = (b['north'] - b['south']) * 110540
    size = (OUT, round(OUT * h_m / w_m)) if w_m >= h_m else (round(OUT * w_m / h_m), OUT)
    mpp = w_m / size[0]                                        # 每像素多少米

    # ---- 1) 读卫星缩略图，放大并轻微模糊（去掉 JPEG 方块）----
    thumb = Image.open(os.path.join(ROOT, 'raw', 'sat', f'{sid}_s2_2025_thumb.jpg')).convert('RGB')
    sat = np.asarray(thumb.resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float32)
    R, G, B = sat[..., 0], sat[..., 1], sat[..., 2]

    # ---- 2) 分类：陆地（植被偏绿少蓝 / 沙滩偏亮偏红）、看得见海底的浅水、看不见海底的深水 ----
    land = ((B < 0.6 * G) & (G > 25)) | ((R > 0.8 * G) & (G > 120))
    land = ndimage.binary_fill_holes(ndimage.binary_opening(land, iterations=2))
    edge = np.concatenate([G[0], G[-1], G[:, 0], G[:, -1]])
    g_deep = float(np.median(edge))                            # 深水的绿色通道基准
    g_flat = float(np.percentile(G[~land], 99.5))              # 最浅礁坪的绿色通道基准
    r = np.clip((G - g_deep) / (g_flat - g_deep), 0, 1)        # 0 = 深水，1 = 最浅
    visible = (r > 0.12) & ~land
    visible = ndimage.binary_opening(visible, iterations=1)

    # ---- 3) 浅水：亮度 → 估算深度（未经实测校准）----
    shallow = 1.0 + (VISIBLE_MAX - 1.0) * (1 - np.clip((r - 0.12) / 0.88, 0, 1)) ** 1.4

    # ---- 4) 看不见海底的区域 ----
    dist = ndimage.distance_transform_edt(~(visible | land)) * mpp          # 离最近礁缘的距离（米）
    if sp['wall']:
        beyond = VISIBLE_MAX + (DEPTH_CAP + 4 - VISIBLE_MAX) * (1 - np.exp(-dist / 18.0)) # 断崖：约 40 m 内降到封顶深度
    else:
        shelf = np.maximum(gebco_depth(sid, b, size), VISIBLE_MAX - 3)       # 看不见海底 ⇒ 至少比可见极限略浅一点的量级
        beyond = VISIBLE_MAX + (shelf - VISIBLE_MAX) * (1 - np.exp(-dist / 160.0))
    depth = np.where(visible, shallow, beyond)
    depth = np.where(land, -2.0, depth)
    depth = ndimage.gaussian_filter(depth, 1.2)
    depth = np.where(land, np.minimum(depth, -0.6), np.maximum(depth, 0.4))  # 平滑后保持海岸线不动
    crop = np.clip(depth, LAND_TOP, DEPTH_CAP).astype(np.float32)            # ★ 深度封顶在休闲潜水极限
    gray = (DEPTH_CAP - crop) / (DEPTH_CAP - LAND_TOP) * 255                 # 白 = 浅，黑 = 深
    Image.fromarray(np.round(gray).astype(np.uint8), 'L').save(os.path.join(ROOT, 'heightmaps', sid + '.png'))

    # ---- 5) 本地离线贴图（低清缩略图；联网时页面会自动换成高清）----
    os.makedirs(os.path.join(ROOT, 'textures'), exist_ok=True)
    thumb.save(os.path.join(ROOT, 'textures', sid + '.jpg'), quality=88)
    ys, xs = np.nonzero(land)
    island = dict(lat=round(b['north'] - (ys.mean() + 0.5) / size[1] * (b['north'] - b['south']), 5),
                  lng=round(b['west'] + (xs.mean() + 0.5) / size[0] * (b['east'] - b['west']), 5)) if len(ys) else None

    c = cur[sid]
    def arrows(s):
        out = []
        for gy in range(4):
            for gx in range(4):
                out.append({"lng": round(b['west'] + (gx + 0.5) / 4 * (b['east'] - b['west']), 5),
                            "lat": round(b['south'] + (gy + 0.5) / 4 * (b['north'] - b['south']), 5),
                            "dir": s['dir'], "speed": s['mean']})
        return out
    season_note = lambda s, label: f"{label}：净流向 {s['dir']}°，逐时平均流速 {s['mean']} m/s，净漂移 {s['net']} m/s，逐时最大 {s['max']} m/s"
    cfg = {
        "name": sp['name'], "spotId": sid,
        "source": ("礁盘轮廓来自 Sentinel-2 卫星影像（2025）。浅水深度按影像亮度估算，未经实测校准；"
                   + ("礁缘外按断崖假设降到封顶深度。" if sp['wall'] else "深水部分用 GEBCO_2020 陆架深度衔接。")
                   + f"深度封顶 {DEPTH_CAP:.0f} m。洋流为 Open-Meteo 模型 2022-01~2026-10 季节平均，全图同一数值。点位未标注。"),
        "_comment": "bounds / depthRange / depthBands / depthCap / source 为扩展字段。depthBands：按深度自动着色的区域带。seasonCurrents 中 dir=净流向，speed=逐时平均流速(m/s)；dry=4–10月，rainy=11–3月。",
        "bounds": b, "depthRange": {"min": LAND_TOP, "max": DEPTH_CAP}, "depthCap": DEPTH_CAP,
        "markers": ([{"type": "view", "lat": island['lat'], "lng": island['lng'],
                      "note": "岛屿位置参考点（由卫星影像识别）。真实潜点位置尚未标注，请按自己的潜水日志或潜店资料补充 markers。"}] if island else []),
        "zones": [], "depthBands": BANDS,
        "seasonCurrents": {"dry": arrows(c['dry']), "rainy": arrows(c['rainy'])},
        "seasonCurrentStats": {"dry": season_note(c['dry'], '旱季 4–10 月'), "rainy": season_note(c['rainy'], '雨季 11–3 月')},
    }
    json.dump(cfg, open(os.path.join(ROOT, 'data', sid + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    index.append({"spotId": sid, "name": sp['name']})
    print(sid, 'heightmap', size, '%.1f m/px' % mpp, 'island', island, 'depth %.1f..%.1f' % (crop.min(), crop.max()),
          '| land %.1f%%  <18m %.0f%%  18-30 %.0f%%  30-40 %.0f%%  capped %.0f%%' % tuple(100 * np.mean(m) for m in
          (crop < 0, (crop >= 0) & (crop < 18), (crop >= 18) & (crop < 30), (crop >= 30) & (crop < DEPTH_CAP), crop >= DEPTH_CAP)))

# 保留两个合成演示潜点（用来看标记 / 手绘区域等功能）
for sid in ('demo-wall', 'demo-slope'):
    p = os.path.join(ROOT, 'data', sid + '.json')
    if os.path.exists(p):
        index.append({"spotId": sid, "name": json.load(open(p, encoding='utf-8'))['name']})
json.dump({"spots": index}, open(os.path.join(ROOT, 'data', 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
