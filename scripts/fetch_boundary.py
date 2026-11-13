"""Tải ranh giới tỉnh Bắc Ninh (sau sáp nhập 2025) từ OpenStreetMap một lần.

- Lấy theo ID quan hệ OSM (R1902690). Tìm theo tên sẽ ra ranh giới Bắc Ninh cũ.
- Lưu bản gốc WGS 84 vào data/boundary_osm.geojson (dùng để cắt raster).
- Ghi bản VN-2000 giản lược 10 m vào public/data/boundary_9209.geojson (để hiển thị).

Chạy:  .venv/bin/python scripts/fetch_boundary.py [--refresh]
Dữ liệu ranh giới © OpenStreetMap contributors, giấy phép ODbL.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

from shapely.geometry import mapping
from shapely.ops import transform as shp_transform

import config as C


def download() -> dict:
    req = urllib.request.Request(C.NOMINATIM_URL, headers={"User-Agent": C.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 – URL cố định
        return json.loads(resp.read().decode("utf-8"))


def round_coords(obj, ndigits: int):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(v, ndigits) for v in obj]
        return [round_coords(v, ndigits) for v in obj]
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="tải lại dù đã có bản lưu")
    args = ap.parse_args()

    C.DATA.mkdir(parents=True, exist_ok=True)
    C.PUBLIC_DATA.mkdir(parents=True, exist_ok=True)

    if C.BOUNDARY_OSM.exists() and not args.refresh:
        print(f"Dùng bản đã lưu: {C.BOUNDARY_OSM}")
        fc = json.loads(C.BOUNDARY_OSM.read_text(encoding="utf-8"))
    else:
        print(f"Tải {C.NOMINATIM_URL}")
        fc = download()
        if not fc.get("features"):
            print("Nominatim không trả về đối tượng nào.", file=sys.stderr)
            return 1
        C.BOUNDARY_OSM.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    feat = fc["features"][0]
    props = feat.get("properties", {})
    geom = C.load_boundary_4326()
    print(f"Đối tượng: {props.get('display_name') or props.get('name')} "
          f"({props.get('osm_type')} {props.get('osm_id')}), kiểu hình học {geom.geom_type}")

    # --- Kiểm tra khung bao và diện tích
    ok = True
    minx, miny, maxx, maxy = geom.bounds
    print(f"Khung bao (lon/lat): {minx:.3f}, {miny:.3f} – {maxx:.3f}, {maxy:.3f}")
    for got, exp in zip((minx, miny, maxx, maxy), C.EXPECTED_BBOX):
        if abs(got - exp) > 0.02:
            ok = False
    geom_9209 = C.boundary_in(C.DST_CRS)
    area_km2 = geom_9209.area / 1e6
    diff = abs(area_km2 - C.EXPECTED_AREA_KM2) / C.EXPECTED_AREA_KM2
    print(f"Diện tích (EPSG:9209): {area_km2:,.1f} km² (kỳ vọng ~{C.EXPECTED_AREA_KM2:,.1f}, "
          f"lệch {diff:.2%})")
    if diff > 0.02:
        ok = False
    if not ok:
        print("Ranh giới không giống Bắc Ninh mới (khung bao hoặc diện tích lệch).", file=sys.stderr)
        return 1

    # --- Bản hiển thị: VN-2000, giản lược 10 m, làm tròn 0,01 m
    simple = geom_9209.simplify(10.0, preserve_topology=True)
    out = {
        "type": "FeatureCollection",
        "name": "ranh_gioi_tinh",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::9209"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "ten": props.get("name") or "Bắc Ninh",
                "nguon": f"OpenStreetMap {C.OSM_ID} (ODbL)",
                "dien_tich_km2": round(area_km2, 1),
            },
            "geometry": round_coords(mapping(simple), 2),
        }],
    }
    C.BOUNDARY_PUBLIC.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n_full = sum(len(p.exterior.coords) for p in getattr(geom_9209, "geoms", [geom_9209]))
    n_simple = sum(len(p.exterior.coords) for p in getattr(simple, "geoms", [simple]))
    print(f"Ghi {C.BOUNDARY_PUBLIC.relative_to(C.ROOT)}: {n_full:,} → {n_simple:,} đỉnh, "
          f"{C.BOUNDARY_PUBLIC.stat().st_size / 1024:,.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
