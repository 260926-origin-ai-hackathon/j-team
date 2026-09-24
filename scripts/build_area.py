"""近大 東大阪キャンパス周辺の実データを集めて data/area.json を作る。

物件そのもの（家賃・間取りなど）はデモ用の架空データ。
周辺情報（スーパー・病院・道路・避難所・浸水想定・地震確率）は下記のオープンデータから実際に計算する。

- OpenStreetMap（Overpass API） © OpenStreetMap contributors, ODbL
- 国土地理院 重ねるハザードマップ（洪水浸水想定・土砂災害警戒区域・津波）
- 国土地理院 指定緊急避難場所データ（洪水）
- 防災科学技術研究所 J-SHIS 地震ハザードステーション（今後30年の震度6弱以上の確率）

使い方: python3 scripts/build_area.py   （取得結果は scripts/.cache/ に保存し、再実行時は再利用する）
"""

import io
import json
import math
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / ".cache"
OUT = ROOT / "data" / "area.json"
UA = {"User-Agent": "h-team-hackathon/0.1 (student project)"}
OVERPASS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
BBOX = "34.634,135.566,34.674,135.606"
Q_STATIONS = '[out:json][timeout:50];(node["railway"="station"](34.63,135.56,34.68,135.61););out tags;'
Q_POIS = ('[out:json][timeout:90];(nwr["shop"~"^(supermarket|convenience|chemist)$"](%s);'
          'nwr["amenity"~"^(clinic|hospital|doctors)$"](%s););out tags center qt;' % (BBOX, BBOX))
Q_ROADS = ('[out:json][timeout:120];(way["highway"~"^(trunk|primary|secondary|tertiary|unclassified|'
           'residential|living_street)$"](%s);way["railway"="rail"](%s););out tags geom qt;' % (BBOX, BBOX))

# キャンパスの基準点（OSM relation 13854100 の中心付近と、主な出入口）
CAMPUS = {"name": "近畿大学 東大阪キャンパス", "lat": 34.6514, "lon": 135.5902}
CAMPUS_GATES = [(34.6512, 135.5872), (34.6505, 135.5894), (34.6514, 135.5902), (34.6522, 135.5870)]

# 物件はデモ用の架空データ。位置だけ実在の住宅地に置く。
PROPERTIES = [
    dict(id="p1", name="メゾン小若江", lat=34.6498, lon=135.5846, rent=36000, fee=3000, deposit=0, key=1,
         layout="1K", size=22, age=18, floor=2, floors=3, autolock=False, net=True),
    dict(id="p2", name="レジデンス長瀬", lat=34.6486, lon=135.5790, rent=55000, fee=5000, deposit=1, key=1,
         layout="1K", size=25, age=6, floor=5, floors=8, autolock=True, net=True),
    dict(id="p3", name="コーポ八戸ノ里", lat=34.6618, lon=135.5878, rent=45000, fee=2000, deposit=1, key=0,
         layout="1DK", size=28, age=31, floor=1, floors=2, autolock=False, net=False),
    dict(id="p4", name="ハイツ河内小阪", lat=34.6622, lon=135.5818, rent=38000, fee=2000, deposit=0, key=0,
         layout="1K", size=20, age=35, floor=3, floors=4, autolock=False, net=False),
    dict(id="p5", name="ソレイユ弥刀", lat=34.6430, lon=135.5848, rent=40000, fee=3000, deposit=0, key=1,
         layout="1K", size=24, age=22, floor=2, floors=3, autolock=False, net=True),
    dict(id="p6", name="グランエール菱屋", lat=34.6560, lon=135.5972, rent=58000, fee=4000, deposit=1, key=1,
         layout="1K", size=26, age=3, floor=7, floors=10, autolock=True, net=True),
    dict(id="p7", name="プチメゾン小若江", lat=34.6468, lon=135.5905, rent=33000, fee=2000, deposit=0, key=0,
         layout="1R", size=18, age=40, floor=1, floors=2, autolock=False, net=False),
]

WALK_M_PER_MIN = 80  # 不動産の表示に関する公正競争規約の「徒歩1分=80m」
DETOUR = 1.3  # 直線距離を道なりに直す係数（目安）
MAP_MARGIN = 500  # 物件のいちばん外側から、地図に含める余白（m）
GRID = 50  # 浸水想定を塗るマスの大きさ（m）


# ---------- 取得 ----------

def http_get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def cached(name, fetch):
    path = CACHE / name
    if path.exists():
        return path.read_bytes()
    data = fetch()
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    time.sleep(0.3)
    return path.read_bytes()


def overpass(name, query):
    def fetch():
        last = None
        for _ in range(4):
            for url in OVERPASS:
                try:
                    body = urllib.parse.urlencode({"data": query}).encode()
                    req = urllib.request.Request(url, data=body, headers=UA)
                    with urllib.request.urlopen(req, timeout=180) as r:
                        text = r.read().decode("utf-8")
                    json.loads(text)
                    return text
                except Exception as e:  # 混雑時はHTMLのエラーが返る
                    last = e
            time.sleep(8)
        raise RuntimeError(f"Overpass failed: {last}")
    return json.loads(cached(name, fetch))


def tile_xy(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    r = math.radians(lat)
    y = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
    return x, y


def hazard_pixel(layer, lat, lon, z=17):
    """重ねるハザードマップのタイルから、その地点の色を読む。タイルが無い（404）なら None。"""
    x, y = tile_xy(lat, lon, z)
    tx, ty = int(x), int(y)
    name = f"hz_{layer}_{z}_{tx}_{ty}.png"
    url = f"https://disaportal.gsi.go.jp/data/raster/{layer}/{z}/{tx}/{ty}.png"

    def fetch():
        try:
            return http_get(url, binary=True)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b""
            raise
    data = cached(name, fetch)
    if not data:
        return None
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    px = im.getpixel((int((x - tx) * 256), int((y - ty) * 256)))
    return None if px[3] == 0 else px[:3]


# 洪水浸水想定（想定最大規模）の凡例色
FLOOD_LEGEND = [
    ((247, 245, 169), 1, "0.5m未満"),
    ((255, 216, 192), 2, "0.5〜3m"),
    ((255, 183, 183), 3, "3〜5m"),
    ((255, 145, 145), 4, "5〜10m"),
    ((242, 133, 201), 5, "10〜20m"),
    ((220, 122, 220), 6, "20m以上"),
]


def flood_level(rgb):
    if rgb is None:
        return 0, "想定なし"
    best = min(FLOOD_LEGEND, key=lambda c: sum((a - b) ** 2 for a, b in zip(c[0], rgb)))
    return best[1], best[2]


def quake_prob(lat, lon):
    url = ("https://www.j-shis.bosai.go.jp/map/api/pshm/Y2020/AVR/TTL_MTTL/meshinfo.geojson?"
           f"position={lon},{lat}&epsg=4326")
    data = json.loads(cached(f"jshis_{lat}_{lon}.json", lambda: http_get(url)))
    p = data["features"][0]["properties"]
    return round(float(p["T30_I60_PS"]) * 100), round(float(p["T30_I55_PS"]) * 100)


# ---------- 計算 ----------

def to_xy(lat, lon):
    """キャンパス中心からのメートル座標（東がx+、北がy+）。"""
    kx = 111320 * math.cos(math.radians(CAMPUS["lat"]))
    return (lon - CAMPUS["lon"]) * kx, (lat - CAMPUS["lat"]) * 110574


def from_xy(x, y):
    kx = 111320 * math.cos(math.radians(CAMPUS["lat"]))
    return CAMPUS["lat"] + y / 110574, CAMPUS["lon"] + x / kx


# 手で置いた7件に加えて、地図を埋めるための架空物件を自動で置く（乱数は固定）
NAME_HEAD = ["アーバン", "ヴィラ", "パレス", "シャトー", "フォレスト", "サンライズ", "リバティ", "カーサ",
             "エスポワール", "ルミエール", "セレーノ", "クレスト", "アルファ", "ベルデ", "ノース"]
NAME_TAIL = ["ハイツ", "コート", "レジデンス", "メゾン", "ハウス", "テラス"]
EXTRA_COUNT = 15
MIN_SPACING = 260


def generate_properties(roads, stations):
    rng = random.Random(20260925)
    placed = [to_xy(p["lat"], p["lon"]) for p in PROPERTIES]
    gates = [to_xy(*g) for g in CAMPUS_GATES]
    cands = []
    for r in roads:
        if r["kind"] not in ("residential", "unclassified"):
            continue
        x, y = r["pts"][len(r["pts"]) // 2]
        if -1900 < x < 1250 and -1600 < y < 2100 and min(dist((x, y), g) for g in gates) > 260:
            cands.append((x, y))
    rng.shuffle(cands)
    heads = NAME_HEAD[:]
    rng.shuffle(heads)
    out = []
    for c in cands:
        if len(out) >= EXTRA_COUNT:
            break
        if min(dist(c, q) for q in placed) < MIN_SPACING:
            continue
        placed.append(c)
        st = min(stations, key=lambda s: dist(c, s["xy"]))
        st_min = walk_min(dist(c, st["xy"]))
        size = rng.choice([18, 20, 21, 22, 23, 24, 25, 26, 28, 30])
        age = rng.randint(1, 42)
        floors = rng.choice([2, 2, 3, 3, 4, 5, 6, 8, 10])
        floor = rng.randint(1, floors)
        autolock = floors >= 4 and age < 25
        rent = 21000 + size * 750 - age * 300 + (4000 if st_min <= 5 else 0) + (5000 if autolock else 0)
        rent = max(28000, int(round(rent / 1000) * 1000))
        lat, lon = from_xy(*c)
        out.append(dict(
            id=f"g{len(out) + 1}", name=f"{heads[len(out) % len(heads)]}{st['name']}{rng.choice(NAME_TAIL)}",
            lat=round(lat, 6), lon=round(lon, 6), rent=rent, fee=rng.choice([2000, 3000, 3000, 4000, 5000]),
            deposit=rng.choice([0, 0, 1]), key=rng.choice([0, 1, 1]),
            layout="1R" if size <= 19 else "1DK" if size >= 28 else "1K", size=size, age=age,
            floor=floor, floors=floors, autolock=autolock, net=rng.random() < 0.5))
    return out


def hazard_grid(layer, cell, x0, y0, x1, y1, z=15, classify=None):
    """地図全体を cell m 四方に区切り、各マスの中心の色を読む。値のあるマスだけ返す。"""
    cells = []
    cols, rows = int((x1 - x0) // cell), int((y1 - y0) // cell)
    for j in range(rows):
        for i in range(cols):
            lat, lon = from_xy(x0 + (i + .5) * cell, y0 + (j + .5) * cell)
            px = hazard_pixel(layer, lat, lon, z)
            if px is None:
                continue
            v = classify(px) if classify else 1
            if v:
                cells.append([i, j, v])
    return {"cell": cell, "x0": round(x0), "y0": round(y0), "cols": cols, "rows": rows, "cells": cells}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def walk_min(m):
    return max(1, math.ceil(m * DETOUR / WALK_M_PER_MIN))


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def way_dist(p, pts):
    return min(seg_dist(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))


ROAD_RANK = {"trunk": 5, "primary": 5, "secondary": 4, "tertiary": 3,
             "unclassified": 2, "residential": 1, "living_street": 1}
ROAD_LABEL = {5: "幹線道路", 4: "主要な道路", 3: "やや広い道路", 2: "生活道路", 1: "生活道路（細い道）"}


def main():
    stations_raw = overpass("stations.json", Q_STATIONS)
    pois_raw = overpass("pois.json", Q_POIS)
    roads_raw = overpass("roads.json", Q_ROADS)
    # 指定緊急避難場所（洪水）。z10 のタイル1枚で周辺全体を覆う
    shelters_raw = json.loads(cached("shelter_flood_10_897_406.json", lambda: http_get(
        "https://cyberjapandata.gsi.go.jp/xyz/skhb01/10/897/406.geojson")))

    stations = []
    for e in stations_raw["elements"]:
        if e["type"] != "node":
            continue
        t = e["tags"]
        name = t.get("name", "")
        line = "JR" if name.startswith("JR") or "西日本旅客" in t.get("operator", "") else \
            "大阪メトロ" if "高速電気軌道" in t.get("operator", "") else "近鉄"
        stations.append({"name": name.replace("JR", "").strip(), "line": line,
                         "xy": to_xy(e["lat"], e["lon"])})

    pois = []
    for e in pois_raw["elements"]:
        t = e["tags"]
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None:
            continue
        name = t.get("name") or ""
        kind = t.get("shop") or t.get("amenity")
        if kind in ("clinic", "doctors", "hospital") and any(w in name for w in ("歯科", "整骨", "接骨", "鍼", "整体")):
            kind = "other"  # 歯科・整骨院などは「かかりつけの内科」の代わりにならないので除く
        elif kind == "hospital" and not name.endswith(("病院", "センター")):
            kind = "clinic"
        elif kind == "doctors":
            kind = "clinic"
        emergency = kind == "hospital" and ("救命" in name or "医療センター" in name or t.get("emergency") == "yes")
        pois.append({"kind": kind, "name": name, "xy": to_xy(lat, lon),
                     "hours": t.get("opening_hours", ""), "emergency": emergency})

    shelters = []
    for f in shelters_raw["features"]:
        lon, lat = f["geometry"]["coordinates"]
        xy = to_xy(lat, lon)
        if abs(xy[0]) < 3000 and abs(xy[1]) < 3000:
            shelters.append({"kind": "shelter", "name": f["properties"]["name"], "xy": xy})

    roads = []
    for e in roads_raw["elements"]:
        t = e["tags"]
        pts = [to_xy(g["lat"], g["lon"]) for g in e["geometry"]]
        kind = "rail" if t.get("railway") == "rail" else t["highway"]
        roads.append({"kind": kind, "name": t.get("name", ""), "pts": pts,
                      "rank": 0 if kind == "rail" else ROAD_RANK.get(kind, 1)})

    def nearest(p, kind, pred=None):
        cands = [q for q in (shelters if kind == "shelter" else pois)
                 if q["kind"] == kind and (pred is None or pred(q))]
        q = min(cands, key=lambda q: dist(p, q["xy"]))
        d = dist(p, q["xy"])
        return {"name": q["name"] or {"supermarket": "スーパー", "convenience": "コンビニ",
                                      "clinic": "診療所", "hospital": "病院", "chemist": "ドラッグストア"}.get(kind, ""),
                "m": round(d), "min": walk_min(d), "hours": q.get("hours", ""),
                "x": round(q["xy"][0]), "y": round(q["xy"][1])}

    all_props = PROPERTIES + generate_properties(roads, stations)
    props = []
    for pr in all_props:
        p = to_xy(pr["lat"], pr["lon"])
        campus_m = min(dist(p, to_xy(*g)) for g in CAMPUS_GATES)
        st = min(stations, key=lambda s: dist(p, s["xy"]))
        st_m = dist(p, st["xy"])

        near_roads = sorted(((way_dist(p, r["pts"]), r) for r in roads if r["kind"] != "rail"),
                            key=lambda t: t[0])
        front = near_roads[0][1]
        big = [r for d, r in near_roads if d <= 120 and r["rank"] >= 4]
        big_names = sorted({r["name"] or ROAD_LABEL[r["rank"]] for r in big})
        rail_d = min(way_dist(p, r["pts"]) for r in roads if r["kind"] == "rail")
        traffic = max(front["rank"], 4 if big else 0, 3 if any(d <= 60 and r["rank"] == 3 for d, r in near_roads) else 0)
        conv_300 = sum(1 for q in pois if q["kind"] == "convenience" and dist(p, q["xy"]) <= 300)

        fl_lv, fl_label = flood_level(hazard_pixel("01_flood_l2_shinsuishin_data", pr["lat"], pr["lon"]))
        landslide = any(hazard_pixel(l, pr["lat"], pr["lon"]) is not None for l in
                        ("05_dosekiryukeikaikuiki", "05_kyukeishakeikaikuiki", "05_jisuberikeikaikuiki"))
        tsunami = hazard_pixel("04_tsunami_newlegend_data", pr["lat"], pr["lon"]) is not None
        q60, q55 = quake_prob(pr["lat"], pr["lon"])

        props.append({
            **{k: pr[k] for k in ("id", "name", "rent", "fee", "deposit", "key", "layout", "size",
                                   "age", "floor", "floors", "autolock", "net")},
            "x": round(p[0]), "y": round(p[1]),
            "campus": {"m": round(campus_m), "min": walk_min(campus_m),
                       "bike": max(1, math.ceil(campus_m * DETOUR / 250))},
            "station": {"name": st["name"], "line": st["line"], "m": round(st_m), "min": walk_min(st_m),
                        "x": round(st["xy"][0]), "y": round(st["xy"][1])},
            "near": {
                "supermarket": nearest(p, "supermarket"),
                "convenience": nearest(p, "convenience"),
                "chemist": nearest(p, "chemist"),
                "clinic": nearest(p, "clinic"),
                "hospital": nearest(p, "hospital"),
                "emergency": nearest(p, "hospital", lambda q: q["emergency"]),
                "shelter": nearest(p, "shelter"),
            },
            "traffic": {"level": traffic, "front": ROAD_LABEL[front["rank"]], "frontName": front["name"],
                        "bigRoads": big_names, "railM": round(rail_d), "conv300": conv_300},
            "hazard": {"flood": fl_lv, "floodLabel": fl_label, "landslide": landslide, "tsunami": tsunami,
                       "quake60": q60, "quake55": q55},
        })

    # 地図用のジオメトリ（地図に出す範囲全体、1m単位に丸める）
    xs = [p["x"] for p in props] + [0]
    ys = [p["y"] for p in props] + [0]
    ext = (min(xs) - MAP_MARGIN, min(ys) - MAP_MARGIN, max(xs) + MAP_MARGIN, max(ys) + MAP_MARGIN)
    inside = lambda xy: ext[0] <= xy[0] <= ext[2] and ext[1] <= xy[1] <= ext[3]
    keep = [{"k": r["kind"], "r": r["rank"], "n": r["name"],
             "p": [c for xy in r["pts"] for c in (round(xy[0]), round(xy[1]))]}
            for r in roads if any(inside(xy) for xy in r["pts"])]
    map_pois = [{"k": q["kind"], "n": q["name"], "x": round(q["xy"][0]), "y": round(q["xy"][1]),
                 **({"e": 1} if q.get("emergency") else {})}
                for q in pois + shelters
                if q["kind"] in ("supermarket", "convenience", "clinic", "hospital", "chemist", "shelter")
                and inside(q["xy"])]
    flood = hazard_grid("01_flood_l2_shinsuishin_data", GRID, *ext, classify=lambda px: flood_level(px)[0])
    slide = hazard_grid("05_dosekiryukeikaikuiki", GRID, *ext)

    # 建物の1点だけでなく、すぐ近く（まわり1マス＝おおむね50m以内）の浸水想定も持たせる
    fcells = {(i, j): v for i, j, v in flood["cells"]}
    for p in props:
        i, j = int((p["x"] - flood["x0"]) // GRID), int((p["y"] - flood["y0"]) // GRID)
        near = max(fcells.get((i + a, j + b), 0) for a in (-1, 0, 1) for b in (-1, 0, 1))
        p["hazard"]["nearFlood"] = max(near, p["hazard"]["flood"])
        p["hazard"]["nearFloodLabel"] = "想定なし" if not p["hazard"]["nearFlood"] else FLOOD_LEGEND[p["hazard"]["nearFlood"] - 1][2]

    out = {
        "generatedAt": time.strftime("%Y-%m-%d"),
        "campus": {"name": CAMPUS["name"], "gates": [[round(c) for c in to_xy(*g)] for g in CAMPUS_GATES]},
        "stations": [{"name": s["name"], "line": s["line"], "x": round(s["xy"][0]), "y": round(s["xy"][1])}
                     for s in stations],
        "properties": props,
        "map": {"extent": [round(v) for v in ext], "ways": keep, "pois": map_pois},
        "hazard": {"flood": flood, "landslide": slide,
                   "floodLegend": [label for _, _, label in FLOOD_LEGEND]},
        "sources": [
            "© OpenStreetMap contributors (ODbL)",
            "国土地理院 重ねるハザードマップ（洪水浸水想定区域［想定最大規模］・土砂災害警戒区域・津波浸水想定）",
            "国土地理院 指定緊急避難場所データ（洪水）",
            "防災科学技術研究所 J-SHIS 地震ハザードステーション（確率論的地震動予測地図 2020年版）",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    for p in props:
        n = p["near"]
        print(p["name"], f"通学{p['campus']['min']}分", f"{p['station']['name']}{p['station']['min']}分",
              f"スーパー{n['supermarket']['min']}分({n['supermarket']['name']})",
              f"病院{n['hospital']['min']}分", f"救急{n['emergency']['name']}{n['emergency']['min']}分",
              f"避難{n['shelter']['name']}{n['shelter']['min']}分",
              f"道路{p['traffic']}", p["hazard"])


if __name__ == "__main__":
    main()
