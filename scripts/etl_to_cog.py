"""ETL giả lập: raster thô (UTM 48N) → COG VN-2000 (EPSG:9209) cắt theo ranh giới tỉnh.

Extract   : đọc data/raw/*.tif (make_raw_mocks.py)
Transform : chiếu sang EPSG:9209 trên lưới gốc là bội số 30 m (phân loại: nearest,
            sinh khối: bilinear) → cắt theo ranh giới OSM → tạo lớp phái sinh
            (biến động = 2021×10 + 2025; carbon = sinh khối × 0,47) → QA mảng
Load      : GTiff trung gian có tag metadata → rasterio.shutil.copy(driver="COG")
            → public/cog/<id>.tif, catalog.json (mô tả lớp), qa_points.json (điểm kiểm tra)

Chạy:  .venv/bin/python scripts/etl_to_cog.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
import time

import numpy as np
import rasterio
import rasterio.shutil
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

import config as C

THREADS = 4
PIXEL_HA = {10.0: 0.01, 20.0: 0.04, 30.0: 0.09}


def log(msg: str, t0: list[float] = [time.perf_counter()]) -> None:  # noqa: B006
    print(f"[{time.perf_counter() - t0[0]:6.1f}s] {msg}", flush=True)


class Grid:
    def __init__(self, bounds, res: float):
        minx, miny, maxx, maxy = bounds
        self.res = res
        self.width = int(math.ceil((maxx - minx) / res - 1e-9))
        self.height = int(math.ceil((maxy - miny) / res - 1e-9))
        self.transform = Affine(res, 0, minx, 0, -res, maxy)
        self.bounds = (minx, maxy - self.height * res, minx + self.width * res, maxy)

    @property
    def shape(self):
        return (self.height, self.width)


def warp(src_path, grid: Grid, resampling, dtype, nodata) -> np.ndarray:
    out = np.full(grid.shape, nodata, dtype)
    with rasterio.open(src_path) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=grid.transform, dst_crs=C.DST_CRS,
                  src_nodata=src.nodata, dst_nodata=nodata, resampling=resampling,
                  num_threads=THREADS)
    return out


def write_cog(layer_id: str, arr: np.ndarray, grid: Grid, nodata, opts: dict, tags: dict,
              band_desc: str, unit: str):
    C.WORK.mkdir(parents=True, exist_ok=True)
    C.COG_DIR.mkdir(parents=True, exist_ok=True)
    work = C.WORK / f"{layer_id}.tif"
    out = C.COG_DIR / f"{layer_id}.tif"
    profile = dict(driver="GTiff", width=grid.width, height=grid.height, count=1,
                   dtype=arr.dtype.name, crs=C.DST_CRS, transform=grid.transform, nodata=nodata,
                   tiled=True, blockxsize=512, blockysize=512, compress="deflate",
                   predictor=3 if arr.dtype.kind == "f" else 2, BIGTIFF="IF_SAFER")
    # Tag phải ghi ở tệp trung gian: driver COG chỉ tạo tệp bằng cách sao chép (CreateCopy);
    # mở COG ở chế độ r+ để sửa tag sẽ làm hỏng bố cục COG.
    with rasterio.open(work, "w", **profile) as dst:
        dst.write(arr, 1)
        dst.update_tags(**tags)
        dst.update_tags(1, UNIT=unit)
        dst.set_band_description(1, band_desc)
    rasterio.shutil.copy(work, out, driver="COG", **opts)
    work.unlink()
    log(f"COG {out.relative_to(C.ROOT)}  {grid.width}×{grid.height}  {out.stat().st_size / 1e6:,.2f} MB")
    return out


def file_info(path) -> dict:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": h.hexdigest()}


def make_tags(code: str, name_ascii: str, acq: str, steps: str) -> dict:
    return {
        "LAYER_CODE": code,
        "LAYER_NAME": name_ascii,
        "DATA_SOURCE": "MOCK - du lieu gia lap cho PoC, khong phai so lieu that",
        "ACQUISITION_DATE": acq,
        "UPDATE_TIME": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "PROCESSING_VERSION": C.PROCESSING_VERSION,
        "QAQC_STATUS": "PASSED",
        "CRS_NAME": C.DST_CRS_NAME,
        "ETL_STEPS": steps,
    }


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"QA KHÔNG ĐẠT: {msg}")


def pick_points(rng, mask: np.ndarray, arr: np.ndarray | None, grid: Grid, n_rand=30, n_edge=10,
                n_class_edge=10, n_out=5) -> list[tuple[int, int, str]]:
    """Chọn pixel kiểm tra: ngẫu nhiên trong tỉnh, mép ranh giới, mép lớp, ngoài tỉnh."""
    h, w = mask.shape

    def take(sel: np.ndarray, n: int, kind: str):
        # Lấy mẫu ngẫu nhiên rồi lọc (tránh np.nonzero trên ~88 triệu pixel)
        picked: dict[tuple[int, int], None] = {}
        for _ in range(100):
            r = rng.integers(0, h, 500_000)
            c = rng.integers(0, w, 500_000)
            ok = sel[r, c]
            for rr, cc in zip(r[ok].tolist(), c[ok].tolist()):
                picked.setdefault((rr, cc))
                if len(picked) >= n:
                    return [(rr, cc, kind) for rr, cc in picked]
        return [(rr, cc, kind) for rr, cc in picked]

    edge = mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0)
                    & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))
    pts = take(mask, n_rand, "ngau_nhien") + take(edge, n_edge, "mep_ranh_gioi")
    del edge
    if arr is not None:
        cedge = mask & np.roll(mask, 1, 1) & (arr != np.roll(arr, 1, 1))
        pts += take(cedge, n_class_edge, "mep_lop")
        del cedge
    else:
        pts += take(mask, n_class_edge, "ngau_nhien")
    outside = ~mask
    outside[0, :] = outside[-1, :] = outside[:, 0] = outside[:, -1] = False
    pts += take(outside, n_out, "ngoai_tinh")
    return pts


def sample_points(path, grid: Grid, pts) -> list[dict]:
    """Giá trị kỳ vọng đọc lại từ COG cuối bằng src.sample (tâm pixel)."""
    coords = [(grid.transform.c + (c + 0.5) * grid.res, grid.transform.f - (r + 0.5) * grid.res)
              for r, c, _ in pts]
    out = []
    with rasterio.open(path) as src:
        nod = src.nodata
        for (r, c, kind), xy, val in zip(pts, coords, src.sample(coords, indexes=1)):
            v = val[0].item()
            out.append({"x": round(xy[0], 3), "y": round(xy[1], 3), "row": r, "col": c,
                        "kind": kind, "expected": None if v == nod else v})
    return out


def main() -> int:
    manifest = json.loads((C.RAW / "manifest.json").read_text(encoding="utf-8"))
    class_res = float(manifest["class_res"])
    cont_res = float(manifest["cont_res"])
    rng = np.random.default_rng(C.SEED + 1)

    # ------------------------------------------------------------ Lưới đích VN-2000
    geom = C.boundary_in(C.DST_CRS)
    bounds = C.snapped_bounds(geom, snap=C.GRID_SNAP)
    g_cls, g_cont = Grid(bounds, class_res), Grid(bounds, cont_res)
    log(f"Lưới {C.DST_CRS}: {bounds[0]:.0f}, {bounds[1]:.0f} – {bounds[2]:.0f}, {bounds[3]:.0f}  "
        f"| {class_res:g} m: {g_cls.width}×{g_cls.height}  | {cont_res:g} m: {g_cont.width}×{g_cont.height}")
    m_cls = geometry_mask([geom], g_cls.shape, g_cls.transform, invert=True)
    m_cont = geometry_mask([geom], g_cont.shape, g_cont.transform, invert=True)
    ha_cls, ha_cont = PIXEL_HA[class_res], PIXEL_HA[cont_res]

    catalog_layers: list[dict] = []
    qa: dict[str, list] = {}
    class_entries = [{"value": v, "label": lbl, "color": col, "forest": is_f}
                     for v, lbl, col, is_f in C.FOREST_CLASSES]
    steps_cls = (f"extract:{C.SRC_CRS} {class_res:g}m raw; transform:reproject {C.DST_CRS} nearest "
                 f"{class_res:g}m grid origin multiple of 30m, clip boundary OSM {C.OSM_ID}; "
                 "load:COG DEFLATE predictor 2, tiles 512, overviews MODE")

    # ------------------------------------------------------------ Hiện trạng 2021, 2025
    classes = {}
    for year in (2021, 2025):
        lid = f"hien_trang_{year}"
        arr = warp(C.RAW / f"{lid}.tif", g_cls, Resampling.nearest, np.uint8, 0)
        arr[~m_cls] = 0
        vals = np.unique(arr[m_cls])
        check(set(vals.tolist()) <= set(C.CLASS_VALUES), f"{lid}: giá trị lạ {vals}")
        check(not (arr[m_cls] == 0).any(), f"{lid}: có pixel NoData trong ranh giới")
        counts = np.bincount(arr[m_cls], minlength=8)
        path = write_cog(lid, arr, g_cls, 0, C.COG_CATEGORICAL,
                         make_tags(f"HT_{year}", f"Hien trang rung {year}", f"{year}-12-31", steps_cls),
                         f"Hien trang rung {year}", "class")
        classes[year] = arr
        catalog_layers.append({
            "id": lid, "name": f"Hiện trạng rừng {year}", "group": "Hiện trạng rừng", "year": year,
            "kind": "categorical", "url": f"cog/{lid}.tif", "dtype": "uint8", "nodata": 0,
            "resolution": class_res, "width": g_cls.width, "height": g_cls.height, "unit": "",
            "classes": [dict(e, area_ha=round(float(counts[e["value"]]) * ha_cls, 2))
                        for e in class_entries],
            **file_info(path),
        })

    # ------------------------------------------------------------ Biến động 2021 → 2025
    h21, h25 = classes[2021], classes[2025]
    change = np.zeros(g_cls.shape, np.uint8)
    np.add(h21 * np.uint8(10), h25, out=change, where=m_cls)
    check(int(change[m_cls].min()) >= 11 and int(change.max()) <= 77, "biến động: mã ngoài 11..77")
    tm_counts = np.bincount(change[m_cls], minlength=78)
    steps_chg = ("derive: pixel-wise change code = class2021*10 + class2025 on the same "
                 f"{class_res:g}m grid; load:COG DEFLATE predictor 2, tiles 512, overviews MODE")
    path = write_cog("bien_dong_2021_2025", change, g_cls, 0, C.COG_CATEGORICAL,
                     make_tags("BD_2021_2025", "Bien dong hien trang 2021-2025", "2025-12-31", steps_chg),
                     "Ma chuyen doi hien trang 2021*10+2025", "transition code")
    del change
    trans = []
    for a in C.CLASS_VALUES:
        for b in C.CLASS_VALUES:
            fa, fb = a in C.FOREST_SET, b in C.FOREST_SET
            if a == b:
                group, color, label = None, None, f"Không đổi – {C.CLASS_LABEL[a]}"
            else:
                group = "loss" if fa and not fb else "gain" if fb and not fa else \
                    "within" if fa and fb else "other"
                color, label = C.CHANGE_GROUPS[group][1], f"{C.CLASS_LABEL[a]} → {C.CLASS_LABEL[b]}"
            trans.append({"value": a * 10 + b, "label": label, "color": color, "group": group,
                          "area_ha": round(float(tm_counts[a * 10 + b]) * ha_cls, 2)})
    legend = []
    for key, (label, color) in C.CHANGE_GROUPS.items():
        area = sum(t["area_ha"] for t in trans if t["group"] == key)
        legend.append({"label": label, "color": color, "area_ha": round(area, 2)})
    catalog_layers.append({
        "id": "bien_dong_2021_2025", "name": "Biến động hiện trạng 2021 → 2025",
        "group": "Biến động", "year": 2025, "kind": "categorical",
        "url": "cog/bien_dong_2021_2025.tif", "dtype": "uint8", "nodata": 0,
        "resolution": class_res, "width": g_cls.width, "height": g_cls.height, "unit": "",
        "classes": trans, "legend": legend, **file_info(path),
    })

    # ------------------------------------------------------------ Sinh khối, carbon 2025 (30 m)
    bio = warp(C.RAW / "sinh_khoi_2025.tif", g_cont, Resampling.bilinear, np.float32, -9999.0)
    bio[~m_cont] = -9999.0
    valid = m_cont
    check(not (bio[valid] == -9999.0).any(), "sinh khối: có NoData trong ranh giới")
    bio[valid] = np.round(bio[valid], 1)
    check(float(bio[valid].min()) >= 0 and float(bio[valid].max()) <= C.BIOMASS_MAX,
          "sinh khối: ngoài khoảng 0..350")
    carbon = np.full(g_cont.shape, -9999.0, np.float32)
    carbon[valid] = bio[valid] * np.float32(C.CARBON_FRACTION)
    steps_bio = (f"extract:{C.SRC_CRS} {cont_res:g}m raw; transform:reproject {C.DST_CRS} bilinear "
                 f"{cont_res:g}m, round 0.1 t/ha, clip boundary OSM {C.OSM_ID}; "
                 "load:COG DEFLATE predictor 3, tiles 512, overviews AVERAGE")
    cont_specs = [
        ("sinh_khoi_2025", bio, "SK_2025", "Sinh khoi 2025", "Sinh khối 2025", "t/ha", 1, 1.0,
         steps_bio, "Sinh khối trên mặt đất (t/ha)"),
        ("carbon_2025", carbon, "CB_2025", "Tru luong carbon 2025", "Trữ lượng carbon 2025",
         "tC/ha", 2, C.CARBON_FRACTION,
         f"derive: carbon = biomass * {C.CARBON_FRACTION} (IPCC default carbon fraction); "
         "load:COG DEFLATE predictor 3, tiles 512, overviews AVERAGE", "Trữ lượng carbon (tC/ha)"),
    ]
    for lid, arr, code, name_ascii, name, unit, decimals, scale, steps, legend_title in cont_specs:
        path = write_cog(lid, arr, g_cont, -9999.0, C.COG_CONTINUOUS,
                         make_tags(code, name_ascii, "2025-12-31", steps), name_ascii, unit)
        v = arr[valid].astype(np.float64)
        catalog_layers.append({
            "id": lid, "name": name, "group": "Sinh khối & carbon", "year": 2025,
            "kind": "continuous", "url": f"cog/{lid}.tif", "dtype": "float32", "nodata": -9999,
            "resolution": cont_res, "width": g_cont.width, "height": g_cont.height,
            "unit": unit, "decimals": decimals, "legendTitle": legend_title,
            "ramp": [{"value": round(s * scale, 2), "color": c} for s, c in C.BIOMASS_RAMP],
            "stats": {"min": round(v.min(), 3), "max": round(v.max(), 3), "mean": round(v.mean(), 3),
                      "total": round(v.sum() * ha_cont, 1), "totalUnit": unit.split("/")[0]},
            **file_info(path),
        })
    del bio, carbon

    # ------------------------------------------------------------ Điểm kiểm tra (self-test)
    pts_cls = pick_points(rng, m_cls, h21, g_cls)
    pts_chg = pick_points(rng, m_cls, h25, g_cls)
    pts_cont = pick_points(rng, m_cont, None, g_cont)
    for lid, pts, grid in [("hien_trang_2021", pts_cls, g_cls), ("hien_trang_2025", pts_cls, g_cls),
                           ("bien_dong_2021_2025", pts_chg, g_cls),
                           ("sinh_khoi_2025", pts_cont, g_cont), ("carbon_2025", pts_cont, g_cont)]:
        qa[lid] = sample_points(C.COG_DIR / f"{lid}.tif", grid, pts)
    t = C.transformer("EPSG:4326", C.DST_CRS)
    proj_checks = [{"lonlat": [lon, lat], "expected": [round(v, 4) for v in t.transform(lon, lat)]}
                   for lon, lat in C.PROJ_CHECK_POINTS]

    # ------------------------------------------------------------ catalog.json
    proj_extent = Transformer.from_crs("EPSG:4326", C.DST_CRS, always_xy=True).transform_bounds(
        *C.WORLD_EXTENT_LONLAT, densify_pts=50)
    tm_classes = C.CLASS_VALUES
    catalog = {
        "version": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "note": "Dữ liệu GIẢ LẬP cho PoC, không phải số liệu thật.",
        "crs": {"code": C.DST_CRS, "name": C.DST_CRS_NAME, "proj4": C.PROJ4_BROWSER,
                "extent": [round(v) for v in proj_extent], "worldExtent": list(C.WORLD_EXTENT_LONLAT)},
        "extent": [round(v, 3) for v in g_cls.bounds],
        "boundary": {"url": "data/boundary_9209.geojson",
                     "attribution": "Ranh giới: © OpenStreetMap contributors (ODbL)"},
        "swipe": {"left": "hien_trang_2021", "right": "hien_trang_2025"},
        "layers": catalog_layers,
        "transitionMatrix": {
            "unit": "ha", "from": 2021, "to": 2025, "classes": tm_classes,
            "rows": [[round(float(tm_counts[a * 10 + b]) * ha_cls, 2) for b in tm_classes]
                     for a in tm_classes],
        },
    }
    (C.COG_DIR / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (C.COG_DIR / "qa_points.json").write_text(
        json.dumps({"layers": qa, "projection": proj_checks}, ensure_ascii=False),
        encoding="utf-8")
    log(f"Ghi catalog.json ({len(catalog_layers)} lớp) và qa_points.json "
        f"({sum(len(v) for v in qa.values())} điểm)")
    total = sum(l["bytes"] for l in catalog_layers)
    log(f"Tổng dung lượng COG: {total / 1e6:,.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
