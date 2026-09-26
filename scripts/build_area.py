"""近大 東大阪キャンパス周辺の実データを集めて data/area.json を作る。

物件そのもの（家賃・間取りなど）はデモ用の架空データ。
周辺情報（スーパー・病院・道路・避難所・浸水想定・地震確率）は下記のオープンデータから実際に計算する。

- OpenStreetMap（Overpass API） © OpenStreetMap contributors, ODbL
- 国土地理院 重ねるハザードマップ（洪水浸水想定・土砂災害警戒区域・津波）
- 国土地理院 指定緊急避難場所データ（洪水）
- 防災科学技術研究所 J-SHIS 地震ハザードステーション（今後30年の震度6弱以上の確率）

使い方: python3 scripts/build_area.py   （取得結果は scripts/.cache/ に保存し、再実行時は再利用する）
"""

import csv
import hashlib
import heapq
import io
import json
import re
import math
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from acoustics_building import THIRD_OCTAVES, mass_law, rw, rw_ctr

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / ".cache"
OUT = ROOT / "data" / "area.json"
UA = {"User-Agent": "h-team-hackathon/0.1 (student project)"}
OVERPASS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
# 地図に出す範囲より1kmほど広く取る（端のマスでも「いちばん近い施設・道路」を正しく測るため）
BBOX = "34.624,135.554,34.694,135.621"
Q_STATIONS = '[out:json][timeout:50];(node["railway"="station"](34.63,135.56,34.68,135.61););out tags;'
Q_POIS = ('[out:json][timeout:90];(nwr["shop"~"^(supermarket|convenience|chemist)$"](%s);'
          'nwr["amenity"~"^(clinic|hospital|doctors)$"](%s););out tags center qt;' % (BBOX, BBOX))
Q_ROADS = ('[out:json][timeout:120];(way["highway"~"^(trunk|primary|secondary|tertiary|unclassified|'
           'residential|living_street)$"](%s);way["railway"="rail"](%s););out tags geom qt;' % (BBOX, BBOX))

# 歩く道のりを計算するための道路網（歩道・小道・階段も含む）。道路どうしのつながりが要るので node の id も取る
Q_WALK = ('[out:json][timeout:180];(way["highway"~"^(trunk|primary|secondary|tertiary|unclassified|residential|'
          'living_street|service|pedestrian|footway|path|steps|cycleway|track|trunk_link|primary_link|secondary_link|'
          'tertiary_link)$"](%s););out body geom qt;' % BBOX)
BIKE_M_PER_MIN = 250
Q_FOOD = ('[out:json][timeout:120];(nwr["amenity"~"^(restaurant|cafe|fast_food|food_court)$"](%s););'
          'out tags center qt;' % BBOX)
Q_BUS = ('[out:json][timeout:120];(node["highway"="bus_stop"](%s);nwr["public_transport"="platform"]["bus"="yes"](%s););'
         'out tags center qt;' % (BBOX, BBOX))
FOOD_RADIUS = 400  # 飲食店の多さを数える半径（m）
Q_POLICE = '[out:json][timeout:60];(nwr["amenity"="police"](%s););out tags center qt;' % BBOX

# 防犯：大阪府警察 犯罪オープンデータ（町丁目ごとの発生）を、Geolonia 住所データの町丁目の代表点に置く
CRIME_YEAR = 2025
CRIME_KINDS = {  # ファイル名 → 手口
    "zitensyatou": "自転車盗", "ootobaitou": "オートバイ盗", "hittakuri": "ひったくり", "syazyounerai": "車上ねらい",
    "buhinnerai": "部品ねらい", "zidouhanbaikinerai": "自動販売機ねらい", "zidousyatou": "自動車盗",
}
CRIME_CITIES = ["東大阪市", "八尾市", "大阪市生野区", "大阪市東成区", "大阪市平野区"]
CRIME_RADIUS = 500  # 物件のまわり何mの発生を数えるか
# ヒートマップで手口ごとに見るときのまとめ方（夜は手口に関係なく、18時〜翌6時に起きたもの）
CRIME_GROUPS = {
    "bike": ["自転車盗", "オートバイ盗"],
    "car": ["車上ねらい", "部品ねらい", "自動車盗"],
}  # ひったくりはこのエリアでは年に数件で、マスごとに比べられないので分けない

# キャンパスの基準点（OSM relation 13854100 の中心付近と、主な出入口）
CAMPUS = {"name": "近畿大学 東大阪キャンパス", "lat": 34.6514, "lon": 135.5902}
CAMPUS_GATES = [(34.6512, 135.5872), (34.6505, 135.5894), (34.6514, 135.5902), (34.6522, 135.5870)]

# 物件はデモ用の架空データ。位置だけ実在の住宅地に置く。
PROPERTIES = [
    dict(id="p1", name="メゾン小若江", lat=34.6498, lon=135.5846, rent=36000, fee=3000, deposit=0, key=1,
         layout="1K", size=22, age=18, floor=2, floors=3, autolock=False, net=True, structure="軽量鉄骨造"),
    dict(id="p2", name="レジデンス長瀬", lat=34.6486, lon=135.5790, rent=55000, fee=5000, deposit=1, key=1,
         layout="1K", size=25, age=6, floor=5, floors=8, autolock=True, net=True, structure="RC造"),
    dict(id="p3", name="コーポ八戸ノ里", lat=34.6618, lon=135.5878, rent=45000, fee=2000, deposit=1, key=0,
         layout="1DK", size=28, age=31, floor=1, floors=2, autolock=False, net=False, structure="木造"),
    dict(id="p4", name="ハイツ河内小阪", lat=34.6622, lon=135.5818, rent=38000, fee=2000, deposit=0, key=0,
         layout="1K", size=20, age=35, floor=3, floors=4, autolock=False, net=False, structure="RC造"),
    dict(id="p5", name="ソレイユ弥刀", lat=34.6430, lon=135.5848, rent=40000, fee=3000, deposit=0, key=1,
         layout="1K", size=24, age=22, floor=2, floors=3, autolock=False, net=True, structure="木造"),
    dict(id="p6", name="グランエール菱屋", lat=34.6560, lon=135.5972, rent=58000, fee=4000, deposit=1, key=1,
         layout="1K", size=26, age=3, floor=7, floors=10, autolock=True, net=True, structure="SRC造"),
    dict(id="p7", name="プチメゾン小若江", lat=34.6468, lon=135.5905, rent=33000, fee=2000, deposit=0, key=0,
         layout="1R", size=18, age=40, floor=1, floors=2, autolock=False, net=False, structure="木造"),
]

WALK_M_PER_MIN = 80  # 不動産の表示に関する公正競争規約の「徒歩1分=80m」
DETOUR = 1.3  # 直線距離を道なりに直す係数（目安）
MAP_MARGIN = 500  # 物件のいちばん外側から、地図に含める余白（m）
GRID = 50  # 浸水想定を塗るマスの大きさ（m）
NOISE_CELL = 80  # 騒音を計算するマスの大きさ（m）。画面のヒートマップと同じ


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
    cands.sort(key=lambda c: (round(c[0]), round(c[1])))  # Overpass の返す順番に左右されないように
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
        structure = (rng.choice(["RC造", "RC造", "SRC造"]) if floors >= 6 else
                     rng.choice(["RC造", "鉄骨造"]) if floors >= 4 else
                     rng.choice(["木造", "木造", "軽量鉄骨造"]))
        rent = 21000 + size * 750 - age * 300 + (4000 if st_min <= 5 else 0) + (5000 if autolock else 0)
        rent = max(28000, int(round(rent / 1000) * 1000))
        lat, lon = from_xy(*c)
        out.append(dict(
            id=f"g{len(out) + 1}", name=f"{heads[len(out) % len(heads)]}{st['name']}{rng.choice(NAME_TAIL)}",
            lat=round(lat, 6), lon=round(lon, 6), rent=rent, fee=rng.choice([2000, 3000, 3000, 4000, 5000]),
            deposit=rng.choice([0, 0, 1]), key=rng.choice([0, 1, 1]),
            layout="1R" if size <= 19 else "1DK" if size >= 28 else "1K", size=size, age=age,
            floor=floor, floors=floors, autolock=autolock, net=rng.random() < 0.5, structure=structure))
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


# ---------- 防犯 ----------

KANJI_DIGITS = "〇一二三四五六七八九"


def kanji_number(n):
    n = int(n)
    if n < 10:
        return KANJI_DIGITS[n]
    if n < 20:
        return "十" + (KANJI_DIGITS[n - 10] if n > 10 else "")
    return KANJI_DIGITS[n // 10] + "十" + (KANJI_DIGITS[n % 10] if n % 10 else "")


def normalize_town(t):
    """府警のデータ（南堀江１丁目）を、Geolonia 住所データの表記（南堀江一丁目）にそろえる。"""
    t = t.translate(str.maketrans("０１２３４５６７８９", "0123456789")).replace("ケ", "ヶ")
    return re.sub(r"(\d+)丁目", lambda m: kanji_number(m.group(1)) + "丁目", t)


def load_crimes():
    """町丁目ごとに、手口別の件数と夜（18時〜翌6時）の件数を数え、代表点のメートル座標をつける。"""
    towns = {}
    for city in CRIME_CITIES:
        url = "https://geolonia.github.io/japanese-addresses/api/ja/" + urllib.parse.quote("大阪府") + "/" + urllib.parse.quote(city) + ".json"
        for a in json.loads(cached(f"addr_{city}.json", lambda: http_get(url))):
            if a.get("lat") is not None and a.get("lng") is not None:  # 代表点のない町丁目がまれにある
                towns[(city, a["town"].replace("ケ", "ヶ"))] = to_xy(a["lat"], a["lng"])
    counts, matched, total = {}, 0, 0
    for key, kind in CRIME_KINDS.items():
        name = f"crime/osaka_{CRIME_YEAR}{key}.csv"
        url = f"https://www.police.pref.osaka.lg.jp/material/files/group/2/osaka_{CRIME_YEAR}{key}.csv"
        text = cached(name, lambda: urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()).decode("cp932")
        for r in csv.DictReader(io.StringIO(text)):
            city = r["市区町村（発生地）"]
            if city not in CRIME_CITIES:
                continue
            total += 1
            tk = (city, normalize_town(r["町丁目（発生地）"]))
            if tk not in towns:
                continue
            matched += 1
            c = counts.setdefault(tk, {"xy": towns[tk], "kinds": {}, "night": 0})
            c["kinds"][kind] = c["kinds"].get(kind, 0) + 1
            hour = int(r["発生時（始期）"] or 12) if (r["発生時（始期）"] or "").isdigit() else 12
            if hour >= 18 or hour < 6:
                c["night"] += 1
    print(f"crime: {matched}/{total} 件を町丁目の位置に置いた")
    return counts


def crime_near(p, counts):
    """物件から CRIME_RADIUS 以内に代表点がある町丁目の件数を足す。"""
    kinds, night, towns = {}, 0, 0
    for c in counts.values():
        if dist(p, c["xy"]) <= CRIME_RADIUS:
            towns += 1
            night += c["night"]
            for k, v in c["kinds"].items():
                kinds[k] = kinds.get(k, 0) + v
    total = sum(kinds.values())
    return {"total": total, "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])), "night": night, "towns": towns}


def crime_grid(counts, ext, cell):
    """マスごとに、物件と同じ数え方（代表点が CRIME_RADIUS 以内の町丁目の件数の合計）で年間の件数を出す。"""
    cols, rows = math.ceil((ext[2] - ext[0]) / cell), math.ceil((ext[3] - ext[1]) / cell)
    gx = np.array([ext[0] + (i + .5) * cell for j in range(rows) for i in range(cols)])
    gy = np.array([ext[1] + (j + .5) * cell for j in range(rows) for i in range(cols)])
    cx = np.array([c["xy"][0] for c in counts.values()])
    cy = np.array([c["xy"][1] for c in counts.values()])
    inside = ((gx[:, None] - cx[None, :]) ** 2 + (gy[:, None] - cy[None, :]) ** 2) <= CRIME_RADIUS ** 2

    def near(weight):
        w = np.array([weight(c) for c in counts.values()], dtype=float)
        return [int(v) for v in np.sum(np.where(inside, w[None, :], 0), axis=1)]

    groups = {g: near(lambda c, ks=ks: sum(c["kinds"].get(k, 0) for k in ks)) for g, ks in CRIME_GROUPS.items()}
    groups["night"] = near(lambda c: c["night"])
    return {"cell": cell, "x0": round(ext[0]), "y0": round(ext[1]), "cols": cols, "rows": rows,
            "near": near(lambda c: sum(c["kinds"].values())), "groups": groups,
            "groupKinds": CRIME_GROUPS}


# ---------- 騒音（道路・線路からの屋外の音と、構造ごとの遮音） ----------

# 道路の種類ごとに「道路の端から10mでの昼間の等価騒音レベル（dB）」を仮定する。
# 目安にしたのは騒音の環境基準（幹線道路に近い空間は昼70dB、住宅地は昼55dB）。実測ではない。
NOISE_AT_10M = {"trunk": 70, "primary": 70, "secondary": 66, "tertiary": 60,
                "unclassified": 48, "residential": 44, "living_street": 41, "rail": 65}
BACKGROUND_DB = 40
SOURCE_STEP = 20  # 道路を20mごとの点に分けて、点ごとの音を足し合わせる


def noise_sources(roads):
    """道路・線路を、一定間隔の点音源（x, y, 1mあたりの音響パワーの目安）の並びにする。"""
    xs, ys, lw = [], [], []
    for r in roads:
        l10 = NOISE_AT_10M.get(r["kind"])
        if l10 is None:
            continue
        pts = r["pts"]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            seg = math.hypot(bx - ax, by - ay)
            n = max(1, int(seg // SOURCE_STEP))
            for k in range(n):
                t = (k + .5) / n
                xs.append(ax + (bx - ax) * t)
                ys.append(ay + (by - ay) * t)
                # 無限に長い直線道路で10m地点が l10 になるよう、1mあたりのパワーレベルを l10+13 とする
                lw.append(l10 + 13 + 10 * math.log10(seg / n))
    return np.array(xs), np.array(ys), np.array(lw)


def outdoor_db(px, py, src):
    """地点 (px, py) の屋外の騒音レベル（dB、昼間の目安）。
    点音源ごとに半自由空間の距離減衰を計算し、20mより先は建物による遮へいを最大15dBまで見込む。
    （NoiseModelling などの騒音地図と同じ「音源を点に分けてエネルギーで足す」考え方を、ごく簡単にしたもの）"""
    xs, ys, lw = src
    px, py = np.atleast_1d(px).astype(float), np.atleast_1d(py).astype(float)
    out = np.empty(len(px))
    for a in range(0, len(px), 64):
        dx = px[a:a + 64, None] - xs[None, :]
        dy = py[a:a + 64, None] - ys[None, :]
        r = np.maximum(np.hypot(dx, dy), 5.0)
        shield = np.clip((r - 20) / 20, 0, 15)
        lp = lw[None, :] - 20 * np.log10(r) - 8 - shield
        e = np.sum(np.where(r < 800, 10 ** (lp / 10), 0), axis=1) + 10 ** (BACKGROUND_DB / 10)
        out[a:a + 64] = 10 * np.log10(e)
    return out


# 構造ごとの壁の組み立て（一般的な例）。層ごとに（密度 kg/m3, 厚さ m）。
# 隣の部屋との壁（界壁）と、外壁。窓はどの構造もアルミサッシの単板ガラス5mmとする。
ASSEMBLIES = {
    "木造": {"party": [(800, 0.025)], "party_label": "石膏ボード12.5mm×2（柱の両側）",
           "outer": [(800, 0.0125), (1300, 0.016)], "outer_label": "石膏ボード＋窯業系サイディング", "flank": 5},
    "軽量鉄骨造": {"party": [(800, 0.05)], "party_label": "石膏ボード12.5mm×4",
              "outer": [(800, 0.0125), (500, 0.05)], "outer_label": "石膏ボード＋ALC50mm", "flank": 5},
    "鉄骨造": {"party": [(500, 0.10), (800, 0.025)], "party_label": "ALC100mm＋石膏ボード×2",
            "outer": [(500, 0.10), (800, 0.0125)], "outer_label": "ALC100mm＋石膏ボード", "flank": 6},
    "RC造": {"party": [(2300, 0.18)], "party_label": "鉄筋コンクリート180mm",
            "outer": [(2300, 0.15)], "outer_label": "鉄筋コンクリート150mm", "flank": 10},
    "SRC造": {"party": [(2300, 0.20)], "party_label": "鉄筋コンクリート200mm",
             "outer": [(2300, 0.15)], "outer_label": "鉄筋コンクリート150mm", "flank": 10},
}
WINDOW = [(2500, 0.005)]
WINDOW_LEAK = 3  # サッシのすき間から漏れる分
WINDOW_RATIO = 0.3  # 外に面した壁のうち窓の割合


def wall_tl(layers):
    """層を重ねた壁を1枚の重さとみなし、質量則で1/3オクターブごとの透過損失を出す（乱入射で5dB引く）。"""
    m = sum(rho * t for rho, t in layers)
    return mass_law(THIRD_OCTAVES, m, 1.0) - 5, m


def structure_acoustics(structure):
    a = ASSEMBLIES[structure]
    party_tl, party_m = wall_tl(a["party"])
    outer_tl, outer_m = wall_tl(a["outer"])
    win_tl, _ = wall_tl(WINDOW)
    party_rw = int(rw(party_tl.copy()))
    # 隣との遮音の目安（D値）：壁の Rw から、床や天井を回り込む分を引いて5刻みに丸める
    d_value = int((party_rw - a["flank"]) // 5 * 5)
    outer_rwctr = float(rw_ctr(outer_tl))
    win_rwctr = float(rw_ctr(win_tl)) - WINDOW_LEAK
    facade = -10 * math.log10(WINDOW_RATIO * 10 ** (-win_rwctr / 10) + (1 - WINDOW_RATIO) * 10 ** (-outer_rwctr / 10))
    return {"partyLabel": a["party_label"], "partyMass": round(party_m), "partyRw": party_rw, "dValue": d_value,
            "outerLabel": a["outer_label"], "outerRwCtr": round(outer_rwctr), "windowRwCtr": round(win_rwctr),
            "facade": round(facade)}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def walk_min(m):
    """直線距離から徒歩の分数を見積もる（架空物件の家賃づけにだけ使う）。"""
    return max(1, math.ceil(m * DETOUR / WALK_M_PER_MIN))


# 窓（バルコニー）の向き。架空データなので、既存の物件が変わらないよう乱数は使わず、物件の id から決める
FACINGS = ["南", "南", "南", "東", "東", "西", "西", "北"]


def facing_of(pid):
    return FACINGS[int(hashlib.md5(pid.encode()).hexdigest(), 16) % len(FACINGS)]


def road_min(m, per_min=WALK_M_PER_MIN):
    """道のり（m）から分数を出す。"""
    return max(1, math.ceil(m / per_min))


# ---------- 道のり（道路網をたどった距離） ----------

class WalkGraph:
    """OpenStreetMap の道路を、交差点・曲がり角を点、そのあいだを辺にしたグラフ。"""

    def __init__(self, raw):
        self.xy, adj = {}, {}
        for e in raw["elements"]:
            ids, geo = e.get("nodes") or [], e.get("geometry") or []
            if len(ids) != len(geo) or len(ids) < 2:
                continue
            for nid, g in zip(ids, geo):
                if nid not in self.xy:
                    self.xy[nid] = to_xy(g["lat"], g["lon"])
            for a, b in zip(ids, ids[1:]):
                w = dist(self.xy[a], self.xy[b])
                adj.setdefault(a, []).append((b, w))
                adj.setdefault(b, []).append((a, w))
        self.adj = adj
        self.ids = np.array(list(self.xy.keys()))
        self.nx = np.array([self.xy[i][0] for i in self.ids])
        self.ny = np.array([self.xy[i][1] for i in self.ids])

    def snap(self, xs, ys):
        """各地点にいちばん近い道路上の点と、そこまでの直線距離。"""
        xs, ys = np.atleast_1d(xs).astype(float), np.atleast_1d(ys).astype(float)
        out_i, out_d = np.empty(len(xs), dtype=np.int64), np.empty(len(xs))
        for a in range(0, len(xs), 256):
            d2 = (xs[a:a + 256, None] - self.nx[None, :]) ** 2 + (ys[a:a + 256, None] - self.ny[None, :]) ** 2
            k = np.argmin(d2, axis=1)
            out_i[a:a + 256] = self.ids[k]
            out_d[a:a + 256] = np.sqrt(d2[np.arange(len(k)), k])
        return out_i, out_d

    def from_sources(self, places):
        """places（xy のリスト）のどれかにいちばん近い道のりと、そのどれか（番号）を、すべての点について出す。"""
        nodes, snapd = self.snap([p[0] for p in places], [p[1] for p in places])
        best, label, heap = {}, {}, []
        for k, (n, d0) in enumerate(zip(nodes.tolist(), snapd.tolist())):
            if d0 < best.get(n, math.inf):
                best[n], label[n] = d0, k
                heapq.heappush(heap, (d0, n))
        while heap:
            d, n = heapq.heappop(heap)
            if d > best[n]:
                continue
            for m, w in self.adj.get(n, ()):
                nd = d + w
                if nd < best.get(m, math.inf):
                    best[m], label[m] = nd, label[n]
                    heapq.heappush(heap, (nd, m))
        return best, label

    def lookup(self, field, xs, ys):
        """地点から最寄りの道路の点へ出て、そこからの道のりを足す。"""
        best, label = field
        nodes, snapd = self.snap(xs, ys)
        return [(best.get(n, math.inf) + d, label.get(n)) for n, d in zip(nodes.tolist(), snapd.tolist())]


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
    pois_raw = overpass("pois_wide.json", Q_POIS)
    roads_raw = overpass("roads_wide.json", Q_ROADS)
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
        elif kind == "supermarket" and "ペット" in name:
            kind = "other"  # OpenStreetMap でスーパーとして登録されているペットショップ
        emergency = kind == "hospital" and ("救命" in name or "医療センター" in name or t.get("emergency") == "yes")
        pois.append({"kind": kind, "name": name, "xy": to_xy(lat, lon),
                     "hours": t.get("opening_hours", ""), "emergency": emergency})

    # 飲食店（レストラン・カフェ・ファストフード）とバス停
    for fname, query, kind in (("food.json", Q_FOOD, "restaurant"), ("bus.json", Q_BUS, "bus_stop")):
        for e in overpass(fname, query)["elements"]:
            lat = e.get("lat") or e.get("center", {}).get("lat")
            lon = e.get("lon") or e.get("center", {}).get("lon")
            if lat is None:
                continue
            pois.append({"kind": kind, "name": e["tags"].get("name", ""), "xy": to_xy(lat, lon), "hours": "",
                         "emergency": False, "sub": e["tags"].get("amenity", "")})

    for e in overpass("police.json", Q_POLICE)["elements"]:
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None:
            continue
        name = e["tags"].get("name", "")
        pois.append({"kind": "police", "name": name or "交番", "xy": to_xy(lat, lon), "hours": "", "emergency": False,
                     "station": name.endswith("警察署")})

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

    # 施設の種類ごとに、道路網のすべての点から「いちばん近い施設までの道のり」を計算しておく
    graph = WalkGraph(overpass("walk_graph.json", Q_WALK))
    print(f"walk graph: {len(graph.xy)} 点, {sum(len(v) for v in graph.adj.values()) // 2} 本")
    groups = {}

    def candidates(kind, pred=None):
        return [q for q in (shelters if kind == "shelter" else pois) if q["kind"] == kind and (pred is None or pred(q))]

    def field_for(key, kind, pred=None):
        if key not in groups:
            cands = candidates(kind, pred)
            groups[key] = (cands, graph.from_sources([q["xy"] for q in cands]))
        return groups[key]

    def nearest(p, kind, pred=None, key=None):
        cands, field = field_for(key or kind, kind, pred)
        (d, k), = graph.lookup(field, [p[0]], [p[1]])
        if k is None or not math.isfinite(d):  # 道路網につながらないときは直線で代用
            k = min(range(len(cands)), key=lambda i: dist(p, cands[i]["xy"]))
            d = dist(p, cands[k]["xy"]) * DETOUR
        q = cands[k]
        return {"name": q["name"] or {"supermarket": "スーパー", "convenience": "コンビニ",
                                      "clinic": "診療所", "hospital": "病院", "chemist": "ドラッグストア"}.get(kind, ""),
                "m": round(d), "min": road_min(d), "hours": q.get("hours", ""),
                "x": round(q["xy"][0]), "y": round(q["xy"][1])}

    gate_field = graph.from_sources([to_xy(*g) for g in CAMPUS_GATES])
    station_field = graph.from_sources([s["xy"] for s in stations])

    all_props = PROPERTIES + generate_properties(roads, stations)
    props = []
    for pr in all_props:
        p = to_xy(pr["lat"], pr["lon"])
        (campus_m, _), = graph.lookup(gate_field, [p[0]], [p[1]])
        (st_m, st_k), = graph.lookup(station_field, [p[0]], [p[1]])
        st = stations[st_k]

        near_roads = sorted(((way_dist(p, r["pts"]), r) for r in roads if r["kind"] != "rail"),
                            key=lambda t: t[0])
        front = near_roads[0][1]
        big = [r for d, r in near_roads if d <= 120 and r["rank"] >= 4]
        big_names = sorted({r["name"] or ROAD_LABEL[r["rank"]] for r in big})
        rail_d = min(way_dist(p, r["pts"]) for r in roads if r["kind"] == "rail")
        traffic = max(front["rank"], 4 if big else 0, 3 if any(d <= 60 and r["rank"] == 3 for d, r in near_roads) else 0)
        conv_300 = sum(1 for q in pois if q["kind"] == "convenience" and dist(p, q["xy"]) <= 300)
        food_near = sum(1 for q in pois if q["kind"] == "restaurant" and dist(p, q["xy"]) <= FOOD_RADIUS)

        fl_lv, fl_label = flood_level(hazard_pixel("01_flood_l2_shinsuishin_data", pr["lat"], pr["lon"]))
        landslide = any(hazard_pixel(l, pr["lat"], pr["lon"]) is not None for l in
                        ("05_dosekiryukeikaikuiki", "05_kyukeishakeikaikuiki", "05_jisuberikeikaikuiki"))
        tsunami = hazard_pixel("04_tsunami_newlegend_data", pr["lat"], pr["lon"]) is not None
        q60, q55 = quake_prob(pr["lat"], pr["lon"])

        props.append({
            **{k: pr[k] for k in ("id", "name", "rent", "fee", "deposit", "key", "layout", "size",
                                   "age", "floor", "floors", "autolock", "net", "structure")},
            "facing": facing_of(pr["id"]), "balcony": pr["floor"] >= 2,
            "x": round(p[0]), "y": round(p[1]),
            "campus": {"m": round(campus_m), "min": road_min(campus_m), "bike": road_min(campus_m, BIKE_M_PER_MIN)},
            "station": {"name": st["name"], "line": st["line"], "m": round(st_m), "min": road_min(st_m),
                        "x": round(st["xy"][0]), "y": round(st["xy"][1])},
            "near": {
                "supermarket": nearest(p, "supermarket"),
                "convenience": nearest(p, "convenience"),
                "chemist": nearest(p, "chemist"),
                "clinic": nearest(p, "clinic"),
                "hospital": nearest(p, "hospital"),
                "emergency": nearest(p, "hospital", lambda q: q["emergency"], key="emergency"),
                "shelter": nearest(p, "shelter"),
                "police": nearest(p, "police"),
                "restaurant": nearest(p, "restaurant"),
                "bus_stop": nearest(p, "bus_stop"),
            },
            "traffic": {"level": traffic, "front": ROAD_LABEL[front["rank"]], "frontName": front["name"],
                        "bigRoads": big_names, "railM": round(rail_d), "conv300": conv_300, "food400": food_near},
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
                if q["kind"] in ("supermarket", "convenience", "clinic", "hospital", "chemist", "shelter", "police",
                                 "restaurant", "bus_stop")
                and inside(q["xy"])]
    flood = hazard_grid("01_flood_l2_shinsuishin_data", GRID, *ext, classify=lambda px: flood_level(px)[0])
    slide = hazard_grid("05_dosekiryukeikaikuiki", GRID, *ext)

    # 防犯：物件のまわりの発生件数と、マスごとの密度（ヒートマップ用）
    crimes = load_crimes()
    for p in props:
        p["crime"] = crime_near((p["x"], p["y"]), crimes)
    crime_towns = [{"x": round(c["xy"][0]), "y": round(c["xy"][1]), "n": sum(c["kinds"].values()),
                    "bike": c["kinds"].get("自転車盗", 0), "night": c["night"]}
                   for c in crimes.values()
                   if ext[0] - 300 <= c["xy"][0] <= ext[2] + 300 and ext[1] - 300 <= c["xy"][1] <= ext[3] + 300]

    # 騒音：物件ごとの屋外の音、部屋の中に入ってくる音、隣との遮音。マスごとの屋外の音（ヒートマップ用）
    src = noise_sources(roads)
    outs = outdoor_db([p["x"] for p in props], [p["y"] for p in props], src)
    for p, db in zip(props, outs):
        ac = structure_acoustics(p["structure"])
        indoor = max(20, db - ac["facade"])
        p["noise"] = {"outdoor": round(float(db)), "indoor": round(float(indoor)), **ac}
        p["traffic"]["level"] = 1 if db < 50 else 2 if db < 55 else 3 if db < 60 else 4 if db < 65 else 5
    cols, rows = math.ceil((ext[2] - ext[0]) / NOISE_CELL), math.ceil((ext[3] - ext[1]) / NOISE_CELL)
    gx = [ext[0] + (i + .5) * NOISE_CELL for j in range(rows) for i in range(cols)]
    gy = [ext[1] + (j + .5) * NOISE_CELL for j in range(rows) for i in range(cols)]
    noise_grid = {"cell": NOISE_CELL, "x0": round(ext[0]), "y0": round(ext[1]), "cols": cols, "rows": rows,
                  "db": [int(round(v)) for v in outdoor_db(gx, gy, src)]}

    # ヒートマップ用：マスの中心から、施設の種類ごとのいちばん近い道のり（m）
    wx = [ext[0] + (i + .5) * NOISE_CELL for j in range(rows) for i in range(cols)]
    wy = [ext[1] + (j + .5) * NOISE_CELL for j in range(rows) for i in range(cols)]
    cap = lambda v: int(min(9999, round(v))) if math.isfinite(v) else 9999
    walk_grid = {"cell": NOISE_CELL, "x0": round(ext[0]), "y0": round(ext[1]), "cols": cols, "rows": rows}
    for key, kind in (("supermarket", "supermarket"), ("convenience", "convenience"), ("clinic", "clinic"), ("hospital", "hospital")):
        walk_grid[key] = [cap(d) for d, _ in graph.lookup(field_for(key, kind)[1], wx, wy)]
    walk_grid["campus"] = [cap(d) for d, _ in graph.lookup(gate_field, wx, wy)]
    for key in ("restaurant", "bus_stop"):
        walk_grid[key] = [cap(d) for d, _ in graph.lookup(field_for(key, key)[1], wx, wy)]
    # マスの中心から FOOD_RADIUS 以内の飲食店の数（多さ）
    fx = np.array([q["xy"][0] for q in pois if q["kind"] == "restaurant"])
    fy = np.array([q["xy"][1] for q in pois if q["kind"] == "restaurant"])
    gx, gy = np.array(wx), np.array(wy)
    walk_grid["food400"] = [int(v) for v in np.sum((gx[:, None] - fx[None, :]) ** 2 + (gy[:, None] - fy[None, :]) ** 2 <= FOOD_RADIUS ** 2, axis=1)]

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
        "noise": noise_grid,
        "walk": walk_grid,
        "crime": {"year": CRIME_YEAR, "radius": CRIME_RADIUS, "towns": crime_towns,
                  "grid": crime_grid(crimes, ext, NOISE_CELL)},
        "sources": [
            "© OpenStreetMap contributors (ODbL)",
            "国土地理院 重ねるハザードマップ（洪水浸水想定区域［想定最大規模］・土砂災害警戒区域・津波浸水想定）",
            "国土地理院 指定緊急避難場所データ（洪水）",
            "防災科学技術研究所 J-SHIS 地震ハザードステーション（確率論的地震動予測地図 2020年版）",
            "騒音・遮音：道路の種類ごとの仮定値からの推定と、python-acoustics（BSD-3）の質量則・ISO 717-1 評価による計算",
            f"「犯罪発生情報（{CRIME_YEAR}年）」（大阪府警察 犯罪オープンデータ https://www.police.pref.osaka.lg.jp/seikatsu/9290.html）を加工して作成",
            "町丁目の位置：Geolonia 住所データ（CC BY 4.0） https://github.com/geolonia/japanese-addresses",
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
