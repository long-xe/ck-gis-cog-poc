"""So sánh phép chiếu WGS 84 → VN-2000 (EPSG:9209) giữa PROJ/GDAL và chuỗi proj4 ở trình duyệt.

Dữ liệu raster được GDAL chiếu theo phép mặc định của PROJ; bản đồ nền và tọa độ chuột
được proj4js chiếu ở trình duyệt. Hai bên phải khớp nhau (< 0,01 m), nếu không lớp COG
sẽ lệch so với bản đồ nền.

Chạy:  .venv/bin/python scripts/check_proj.py
"""
from __future__ import annotations

import math
import sys

import rasterio.warp
from pyproj import CRS, Transformer

import config as C

POINTS = C.PROJ_CHECK_POINTS
TOLERANCE_M = 0.01


def main() -> int:
    proj_default = C.transformer("EPSG:4326", C.DST_CRS)
    variants = {
        "PoC (proj4 đảo dấu xoay)": C.PROJ4_BROWSER,
        "App admin (config.json)": C.PROJ4_APP,
        "PROJ export không towgs84": CRS.from_epsg(9209).to_proj4(),
    }
    t_variants = {k: Transformer.from_crs("EPSG:4326", CRS.from_proj4(v), always_xy=True)
                  for k, v in variants.items()}

    worst = {k: 0.0 for k in variants}
    for lon, lat in POINTS:
        e0, n0 = proj_default.transform(lon, lat)
        (ge,), (gn,) = rasterio.warp.transform("EPSG:4326", C.DST_CRS, [lon], [lat])
        print(f"\n({lon:.2f}E, {lat:.2f}N)  PROJ: E={e0:.3f} N={n0:.3f}   "
              f"GDAL: lệch {math.hypot(ge - e0, gn - n0):.3f} m")
        for name, t in t_variants.items():
            e, n = t.transform(lon, lat)
            d = math.hypot(e - e0, n - n0)
            worst[name] = max(worst[name], d)
            print(f"   {name:<28} lệch {d:9.3f} m")

    # PROJ chỉ cho biết tên phép chuyển đổi sau khi đã transform ít nhất một lần.
    print(f"\nPhép chuyển đổi PROJ đã dùng: {proj_default.description}")
    print("Lệch lớn nhất:")
    for name, d in worst.items():
        print(f"   {name:<28} {d:9.3f} m")

    ok = worst["PoC (proj4 đảo dấu xoay)"] < TOLERANCE_M
    print("\nKẾT QUẢ:", "ĐẠT" if ok else "KHÔNG ĐẠT",
          f"(chuỗi của PoC phải lệch < {TOLERANCE_M} m so với PROJ)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
