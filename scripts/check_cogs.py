"""QA/QC các COG cuối trong public/cog/ (chạy lại độc lập với ETL).

Kiểm tra: CRS EPSG:9209, bố cục COG thật (LAYOUT=COG), nén DEFLATE + predictor đúng,
tile 512, đủ overview, kiểu dữ liệu và NoData, gốc lưới là bội số 30 m, giá trị trong
bảng lớp (cả ở overview), sinh khối trong 0..350, carbon = sinh khối × 0,47, biến động =
2021×10 + 2025, đủ tag metadata, dung lượng và sha256 khớp catalog.json.

Chạy:  .venv/bin/python scripts/check_cogs.py      (thoát mã 1 nếu có lỗi)
"""
from __future__ import annotations

import hashlib
import json
import sys

import numpy as np
import rasterio

import config as C

REQUIRED_TAGS = ["LAYER_CODE", "DATA_SOURCE", "ACQUISITION_DATE", "UPDATE_TIME",
                 "PROCESSING_VERSION", "QAQC_STATUS", "CRS_NAME", "ETL_STEPS"]
EXPECTED_OVERVIEWS = {10.0: 5, 20.0: 4, 30.0: 3}
errors: list[str] = []


def ok(cond: bool, layer: str, msg: str) -> None:
    if not cond:
        errors.append(f"{layer}: {msg}")


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    catalog = json.loads((C.COG_DIR / "catalog.json").read_text(encoding="utf-8"))
    arrays: dict[str, np.ndarray] = {}
    for layer in catalog["layers"]:
        lid = layer["id"]
        path = C.COG_DIR / f"{lid}.tif"
        with rasterio.open(path) as src:
            ims = src.tags(ns="IMAGE_STRUCTURE")
            res = src.res[0]
            pred = "3" if layer["kind"] == "continuous" else "2"
            ok(src.crs.to_epsg() == 9209, lid, f"CRS {src.crs}")
            ok(ims.get("LAYOUT") == "COG", lid, f"LAYOUT={ims.get('LAYOUT')}")
            ok(ims.get("COMPRESSION") == "DEFLATE", lid, f"COMPRESSION={ims.get('COMPRESSION')}")
            ok(ims.get("PREDICTOR") == pred, lid, f"PREDICTOR={ims.get('PREDICTOR')} (cần {pred})")
            ok(src.block_shapes == [(512, 512)], lid, f"block {src.block_shapes}")
            n_ovr = len(src.overviews(1))
            ok(n_ovr == EXPECTED_OVERVIEWS[res], lid, f"{n_ovr} overview (cần {EXPECTED_OVERVIEWS[res]})")
            ok(src.dtypes[0] == layer["dtype"], lid, f"dtype {src.dtypes[0]}")
            ok(src.nodata == layer["nodata"], lid, f"nodata {src.nodata}")
            ok(src.res == (layer["resolution"],) * 2, lid, f"độ phân giải {src.res}")
            t = src.transform
            ok(t.c % C.GRID_SNAP == 0 and t.f % C.GRID_SNAP == 0, lid, f"gốc lưới {t.c}, {t.f}")
            tags = src.tags()
            ok(all(k in tags for k in REQUIRED_TAGS), lid,
               f"thiếu tag {[k for k in REQUIRED_TAGS if k not in tags]}")
            arr = src.read(1)
            arrays[lid] = arr
            print(f"{lid:<22} {src.width}×{src.height} @{res:g} m  {ims.get('COMPRESSION')}"
                  f"/pred {ims.get('PREDICTOR')}  {n_ovr} ovr  {path.stat().st_size / 1e6:6.2f} MB")

            if layer["kind"] == "categorical":
                allowed = {c["value"] for c in layer["classes"]} | {layer["nodata"]}
                vals = set(np.unique(arr).tolist())
                ok(vals <= allowed, lid, f"giá trị ngoài bảng lớp: {sorted(vals - allowed)}")
                for i in range(n_ovr):
                    with rasterio.open(path, overview_level=i) as ov:
                        ov_vals = set(np.unique(ov.read(1)).tolist())
                    ok(ov_vals <= allowed, lid, f"overview {i}: giá trị lạ {sorted(ov_vals - allowed)}")
            else:
                v = arr[arr != layer["nodata"]]
                ok(v.size > 0 and v.min() >= 0, lid, "giá trị âm")
                if lid == "sinh_khoi_2025":
                    ok(v.max() <= C.BIOMASS_MAX, lid, f"max {v.max()} > {C.BIOMASS_MAX}")
                stats = src.tags(1)
                ok("STATISTICS_MEAN" in stats, lid, "thiếu STATISTICS_* của band")

        ok(path.stat().st_size == layer["bytes"], lid, "dung lượng khác catalog")
        ok(sha256(path) == layer["sha256"], lid, "sha256 khác catalog")

    # Quan hệ giữa các lớp
    h21, h25, chg = (arrays[k] for k in ("hien_trang_2021", "hien_trang_2025", "bien_dong_2021_2025"))
    inside = h21 != 0
    ok(np.array_equal(inside, h25 != 0), "hien_trang", "vùng NoData 2021 và 2025 khác nhau")
    expect = np.where(inside, h21.astype(np.uint16) * 10 + h25, 0)
    ok(np.array_equal(chg, expect), "bien_dong_2021_2025", "≠ 2021×10 + 2025")
    bio, car = arrays["sinh_khoi_2025"], arrays["carbon_2025"]
    vb = bio != -9999
    ok(np.array_equal(vb, car != -9999), "carbon_2025", "vùng NoData khác sinh khối")
    ok(np.array_equal(car[vb], bio[vb] * np.float32(C.CARBON_FRACTION)), "carbon_2025",
       "≠ float32(sinh khối × 0,47)")

    print()
    if errors:
        print(f"KHÔNG ĐẠT – {len(errors)} lỗi:")
        for e in errors:
            print("  -", e)
        return 1
    print("ĐẠT – tất cả COG hợp lệ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
