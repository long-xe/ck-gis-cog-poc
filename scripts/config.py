"""Hằng số và hàm dùng chung cho các script sinh / kiểm tra COG giả lập.

Mọi dữ liệu ở đây là GIẢ LẬP cho PoC: bảng lớp hiện trạng, hệ số sinh khối,
tỷ lệ biến động… chỉ để có raster trông hợp lý, không phải số liệu thật.
"""
from __future__ import annotations

import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
WORK = DATA / "work"
PUBLIC = ROOT / "public"
COG_DIR = PUBLIC / "cog"
PUBLIC_DATA = PUBLIC / "data"

BOUNDARY_OSM = DATA / "boundary_osm.geojson"          # bản tải về (WGS 84, đầy đủ chi tiết)
BOUNDARY_PUBLIC = PUBLIC_DATA / "boundary_9209.geojson"  # bản hiển thị (VN-2000, giản lược 10 m)

# ----------------------------------------------------------------- Hệ tọa độ
SRC_CRS = "EPSG:32648"  # dữ liệu "thô" giả lập: WGS 84 / UTM 48N (như ảnh vệ tinh giao về)
DST_CRS = "EPSG:9209"   # sau ETL: VN-2000 / TM-3 105-30 (KTT 105°30′, k = 0,9999)
DST_CRS_NAME = "VN-2000 / TM-3 105-30"

_TMERC = "+proj=tmerc +lat_0=0 +lon_0=105.5 +k=0.9999 +x_0=500000 +y_0=0 +ellps=WGS84"
# Chuỗi dùng ở trình duyệt (proj4js). EPSG công bố 7 tham số theo quy ước coordinate-frame,
# còn +towgs84 của proj4 theo quy ước position-vector, nên 3 tham số xoay phải đảo dấu
# thì mới khớp PROJ / GDAL.
PROJ4_BROWSER = (
    _TMERC + " +towgs84=-191.90441429,-39.30318279,-111.45032835,"
    "0.00928836,-0.01975479,0.00427372,0.252906278 +units=m +no_defs"
)
# Chuỗi hiện có trong config.json của ứng dụng admin (giữ nguyên dấu như EPSG) – chỉ để so sánh.
PROJ4_APP = (
    _TMERC + " +towgs84=-191.90441429,-39.30318279,-111.45032835,"
    "-0.00928836,0.01975479,-0.00427372,0.252906278 +units=m +no_defs"
)
# Điểm kiểm tra phép chiếu (lon, lat) – trải khắp tỉnh mới. Dùng cho check_proj.py
# và self-test ở trình duyệt (qa_points.json).
PROJ_CHECK_POINTS = [
    (106.30, 21.20),
    (105.90, 21.00),
    (107.03, 21.60),
    (106.05, 21.18),  # khu vực Bắc Ninh cũ
    (106.70, 21.35),  # khu vực Lục Ngạn
]
# Vùng hợp lệ cho projection ở trình duyệt (OL cần extent cho lưới tile khi chiếu lại bản đồ nền).
WORLD_EXTENT_LONLAT = (102.0, 8.0, 110.0, 24.0)

# ----------------------------------------------------------------- Ranh giới tỉnh (OSM)
OSM_ID = "R1902690"  # Bắc Ninh sau sáp nhập 2025 (admin_level 4, ISO VN-56)
NOMINATIM_URL = (
    "https://nominatim.openstreetmap.org/lookup"
    f"?osm_ids={OSM_ID}&format=geojson&polygon_geojson=1"
)
USER_AGENT = "ck-gis-cog-poc/0.1 (one-off boundary fetch for a mapping PoC)"
EXPECTED_BBOX = (105.88, 20.96, 107.04, 21.63)  # lon/lat, sai số ±0,02°
EXPECTED_AREA_KM2 = 4718.6

# ----------------------------------------------------------------- Lưới
GRID_SNAP = 30.0       # gốc lưới là bội số 30 m → pixel 30 m trùng khít 3×3 pixel 10 m
CLASS_RES = 10.0       # raster phân loại (kiểu Sentinel-2)
CONT_RES = 30.0        # sinh khối / carbon
RAW_BUFFER_M = 2000.0  # dữ liệu thô phủ rộng hơn ranh giới 2 km
SEED = 20251

# ----------------------------------------------------------------- Bảng lớp hiện trạng (GIẢ LẬP)
FOREST_CLASSES = [
    # value, label, color, is_forest
    (1, "Rừng tự nhiên gỗ (thường xanh)", "#1b6b34", True),
    (2, "Rừng hỗn giao gỗ – tre nứa", "#5a9b3d", True),
    (3, "Rừng trồng", "#a9d46f", True),
    (4, "Đất có cây gỗ tái sinh", "#e3d26f", False),
    (5, "Đất trống, trảng cỏ cây bụi", "#f0a15a", False),
    (6, "Đất nông nghiệp, dân cư và khác", "#d8cfc2", False),
    (7, "Mặt nước", "#4f8fd6", False),
]
CLASS_VALUES = [c[0] for c in FOREST_CLASSES]
CLASS_LABEL = {c[0]: c[1] for c in FOREST_CLASSES}
FOREST_SET = {c[0] for c in FOREST_CLASSES if c[3]}

# Nhóm biến động (mã chuyển đổi = hiện trạng 2021 × 10 + hiện trạng 2025)
CHANGE_GROUPS = {
    "loss": ("Mất rừng", "#d7301f"),
    "gain": ("Tăng rừng", "#2b83ba"),
    "within": ("Thay đổi loại rừng", "#8e44ad"),
    "other": ("Thay đổi ngoài đất rừng", "#9e9e9e"),
}

# Sinh khối trung bình theo lớp (t/ha) – GIẢ LẬP
BIOMASS_MEAN = {1: 180.0, 2: 110.0, 3: 75.0, 4: 30.0, 5: 10.0, 6: 4.0, 7: 0.0}
BIOMASS_MAX = 350.0
CARBON_FRACTION = 0.47  # hệ số carbon mặc định của IPCC

BIOMASS_RAMP = [
    (0, "#fbf8d0"), (25, "#d9ef8b"), (60, "#a6d96a"), (100, "#66bd63"),
    (150, "#1a9850"), (220, "#006837"), (300, "#00341b"),
]

PROCESSING_VERSION = "poc-1.0"
COG_COMMON = dict(BLOCKSIZE=512, COMPRESS="DEFLATE", LEVEL=9,
                  OVERVIEWS="IGNORE_EXISTING", NUM_THREADS="ALL_CPUS")
COG_CATEGORICAL = dict(COG_COMMON, PREDICTOR="STANDARD", OVERVIEW_RESAMPLING="MODE")
COG_CONTINUOUS = dict(COG_COMMON, PREDICTOR="FLOATING_POINT", OVERVIEW_RESAMPLING="AVERAGE",
                      STATISTICS="YES")


# ----------------------------------------------------------------- Hàm dùng chung
def transformer(src: str, dst: str) -> Transformer:
    """Transformer của PROJ (chọn phép chuyển đổi mặc định – cùng phép mà GDAL dùng)."""
    return Transformer.from_crs(src, dst, always_xy=True)


def load_boundary_4326():
    """Đa giác ranh giới tỉnh (WGS 84) từ bản OSM đã tải."""
    if not BOUNDARY_OSM.exists():
        raise SystemExit(f"Chưa có {BOUNDARY_OSM}. Chạy scripts/fetch_boundary.py trước.")
    fc = json.loads(BOUNDARY_OSM.read_text(encoding="utf-8"))
    return shape(fc["features"][0]["geometry"])


def boundary_in(crs: str):
    """Ranh giới tỉnh chiếu sang `crs` bằng PROJ."""
    t = transformer("EPSG:4326", crs)
    return shp_transform(t.transform, load_boundary_4326())


def snapped_bounds(geom, snap: float = GRID_SNAP, buffer: float = 0.0):
    """Khung bao của `geom` (+ vùng đệm), nới ra ngoài cho tròn bội số `snap`."""
    import math

    minx, miny, maxx, maxy = geom.bounds
    return (
        math.floor((minx - buffer) / snap) * snap,
        math.floor((miny - buffer) / snap) * snap,
        math.ceil((maxx + buffer) / snap) * snap,
        math.ceil((maxy + buffer) / snap) * snap,
    )
