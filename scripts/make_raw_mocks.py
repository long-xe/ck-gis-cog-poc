"""Sinh raster "thô" giả lập (trước ETL) theo WGS 84 / UTM 48N.

Mô phỏng dữ liệu được bàn giao ở hệ tọa độ khác VN-2000:
  data/raw/hien_trang_2021.tif   uint8, 10 m – phân loại hiện trạng 2021
  data/raw/hien_trang_2025.tif   uint8, 10 m – phân loại hiện trạng 2025
  data/raw/sinh_khoi_2025.tif    float32, 30 m – sinh khối 2025 (t/ha)

Hình thái là nhiễu fractal: lưới ngẫu nhiên thô được phóng to bằng nội suy cubic spline
rồi cộng dồn nhiều cấp, thêm xu hướng Đông Bắc (núi, nhiều rừng) → Tây Nam (đồng bằng,
đô thị). Kết quả chỉ để PoC, KHÔNG phải số liệu thật.

Chạy:  .venv/bin/python scripts/make_raw_mocks.py [--res 10|20]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

import config as C

THREADS = 4


def log(msg: str, t0: list[float] = [time.perf_counter()]) -> None:  # noqa: B006
    print(f"[{time.perf_counter() - t0[0]:6.1f}s] {msg}", flush=True)


def fractal(shape, transform: Affine, rng, octaves) -> np.ndarray:
    """Nhiễu fractal float32 đã chuẩn hóa (trung bình 0, độ lệch chuẩn 1)."""
    h, w = shape
    res = transform.a
    acc = np.zeros(shape, np.float32)
    tmp = np.empty(shape, np.float32)
    for cell, amp in octaves:
        nx = int(np.ceil(w * res / cell)) + 4
        ny = int(np.ceil(h * res / cell)) + 4
        src = rng.standard_normal((ny, nx), dtype=np.float32)
        src_t = Affine(cell, 0, transform.c - 2 * cell, 0, -cell, transform.f + 2 * cell)
        reproject(src, tmp, src_transform=src_t, src_crs=C.SRC_CRS,
                  dst_transform=transform, dst_crs=C.SRC_CRS,
                  resampling=Resampling.cubic_spline, num_threads=THREADS)
        np.multiply(tmp, np.float32(amp), out=tmp)
        acc += tmp
    del tmp
    sample = acc[::17, ::13]
    acc -= np.float32(sample.mean())
    acc /= np.float32(sample.std())
    return acc


def river_mask(shape, transform: Affine, rng) -> np.ndarray:
    """Vài con sông uốn khúc: đường cong = xu hướng tuyến tính + tổng các sóng sin, đệm theo bề rộng."""
    from rasterio.features import rasterize
    from shapely.geometry import LineString

    h, w = shape
    x0, y1 = transform.c, transform.f
    width_m, height_m = w * transform.a, h * transform.a
    u = np.linspace(-0.05, 1.05, 1500)
    rivers = []
    #             y đầu (tỉ lệ từ trên), y cuối, bề rộng (m)
    for start, end, river_w in [(0.30, 0.55, 140), (0.10, 0.35, 90), (0.62, 0.92, 120),
                                (0.45, 0.70, 70)]:
        v = start + (end - start) * u
        for freq, amp in [(1.3, 0.05), (3.1, 0.02), (7.7, 0.008), (17.0, 0.003)]:
            v = v + amp * np.sin(2 * np.pi * (freq * u + rng.random()))
        line = LineString(np.column_stack([x0 + u * width_m, y1 - v * height_m]))
        rivers.append((line.buffer(river_w / 2, cap_style="flat"), 1))
    return rasterize(rivers, out_shape=shape, transform=transform, fill=0,
                     dtype=np.uint8).astype(bool)


def q(values: np.ndarray, p: float) -> np.float32:
    return np.float32(np.quantile(values, p))


def write_raw(path, arr, transform, nodata) -> None:
    profile = dict(driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1,
                   dtype=arr.dtype.name, crs=C.SRC_CRS, transform=transform, nodata=nodata,
                   tiled=True, blockxsize=512, blockysize=512, compress="deflate",
                   predictor=3 if arr.dtype.kind == "f" else 2, BIGTIFF="IF_SAFER")
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)
    log(f"Ghi {path.relative_to(C.ROOT)}  {arr.shape[1]}×{arr.shape[0]}  "
        f"{path.stat().st_size / 1e6:,.1f} MB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=C.CLASS_RES, choices=[10.0, 20.0],
                    help="độ phân giải raster phân loại (20 = chạy thử nhanh)")
    args = ap.parse_args()
    res = args.res
    C.RAW.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(C.SEED)

    # ------------------------------------------------------------ Lưới thô (UTM 48N)
    geom = C.boundary_in(C.SRC_CRS)
    minx, miny, maxx, maxy = C.snapped_bounds(geom, snap=C.CONT_RES, buffer=C.RAW_BUFFER_M)
    w, h = int(round((maxx - minx) / res)), int(round((maxy - miny) / res))
    t10 = Affine(res, 0, minx, 0, -res, maxy)
    log(f"Lưới thô {C.SRC_CRS}: {minx:.0f},{miny:.0f} – {maxx:.0f},{maxy:.0f}  "
        f"{w}×{h} px ở {res:g} m ({w * h / 1e6:,.1f} Mpx)")

    inside = geometry_mask([geom], (h, w), t10, invert=True)
    idx = np.flatnonzero(inside.ravel())
    sample_idx = rng.choice(idx, size=min(2_000_000, idx.size), replace=False)
    del idx

    def sample_of(arr: np.ndarray) -> np.ndarray:
        return arr.ravel()[sample_idx]

    # ------------------------------------------------------------ "Độ rừng" F + xu hướng
    F = fractal((h, w), t10, rng, [(16000, 1.0), (8000, 0.8), (4000, 0.6), (2000, 0.45),
                                    (1000, 0.3), (500, 0.2), (250, 0.12), (60, 0.06)])
    tx = np.linspace(0, 1, w, dtype=np.float32)[None, :]   # 0 = tây, 1 = đông
    ty = np.linspace(1, 0, h, dtype=np.float32)[:, None]   # 0 = nam, 1 = bắc
    F += np.float32(2.4) * (np.float32(0.7) * tx - np.float32(0.35))
    F += np.float32(2.4) * (np.float32(0.3) * ty - np.float32(0.15))
    log("Xong trường độ rừng F")

    G = fractal((h, w), t10, rng, [(6000, 1.0), (3000, 0.7), (1500, 0.5), (700, 0.35),
                                    (300, 0.2)])
    log("Xong trường phân loại phụ G")

    fs = sample_of(F)
    f_forest, f_edge, f_mount = q(fs, 0.66), q(fs, 0.52), q(fs, 0.80)
    forest = F >= f_forest
    s = F + np.float32(0.7) * G                      # cao = rừng tự nhiên, thấp = rừng trồng
    s_forest = sample_of(s)[sample_of(forest)]
    s_nat, s_mix = q(s_forest, 0.65), q(s_forest, 0.45)

    c21 = np.full((h, w), 6, np.uint8)               # mặc định: nông nghiệp, dân cư, khác
    edge = (F >= f_edge) & ~forest
    c21[edge & (G > 0)] = 4
    c21[edge & (G <= 0)] = 5
    c21[forest] = 3
    c21[forest & (s >= s_mix)] = 2
    c21[forest & (s >= s_nat)] = 1
    del s, edge, forest, G

    # Sông: đường cong uốn khúc chảy Tây Bắc → Đông Nam; hồ: đỉnh của một trường nhiễu
    water = river_mask((h, w), t10, rng)
    L = fractal((h, w), t10, rng, [(3000, 1.0), (1500, 0.5), (600, 0.25)])
    water |= (L > q(sample_of(L), 0.992)) & (F < f_mount)
    del L
    c21[water] = 7
    del water, F
    log("Xong hiện trạng 2021")

    # ------------------------------------------------------------ Biến động → hiện trạng 2025
    P = fractal((h, w), rng=rng, transform=t10,
                octaves=[(3000, 1.0), (1500, 0.7), (700, 0.5), (300, 0.3), (120, 0.15)])
    ps = sample_of(P)
    natural = (c21 == 1) | (c21 == 2)
    c25 = c21.copy()
    c25[natural & (P > q(ps, 0.975))] = 5            # mất rừng tự nhiên
    c25[(c21 == 3) & (P > q(ps, 0.95))] = 5          # khai thác trắng rừng trồng
    c25[natural & (P < q(ps, 0.02))] = 3             # rừng tự nhiên → rừng trồng
    del P, ps, natural
    Q = fractal((h, w), t10, rng, [(2500, 1.0), (1200, 0.7), (500, 0.4), (150, 0.2)])
    qs = sample_of(Q)
    open_land = (c21 == 4) | (c21 == 5)
    c25[open_land & (Q > q(qs, 0.85))] = 3           # trồng rừng mới
    c25[(c21 == 4) & (Q < q(qs, 0.10))] = 2          # tái sinh thành rừng
    c25[(c21 == 5) & (Q < q(qs, 0.05))] = 6          # mở rộng đô thị / nông nghiệp
    del Q, qs, open_land
    log("Xong hiện trạng 2025")

    write_raw(C.RAW / "hien_trang_2021.tif", c21, t10, 0)
    write_raw(C.RAW / "hien_trang_2025.tif", c25, t10, 0)
    del c21

    # ------------------------------------------------------------ Sinh khối 2025 (30 m)
    r30 = C.CONT_RES
    w30, h30 = int(round((maxx - minx) / r30)), int(round((maxy - miny) / r30))
    t30 = Affine(r30, 0, minx, 0, -r30, maxy)
    c25_30 = np.zeros((h30, w30), np.uint8)
    reproject(c25, c25_30, src_transform=t10, src_crs=C.SRC_CRS, dst_transform=t30,
              dst_crs=C.SRC_CRS, resampling=Resampling.mode, num_threads=THREADS)
    del c25
    N = fractal((h30, w30), t30, rng, [(2000, 1.0), (800, 0.6), (300, 0.4), (120, 0.25)])
    lut = np.zeros(256, np.float32)
    for k, v in C.BIOMASS_MEAN.items():
        lut[k] = v
    bio = lut[c25_30] * (np.float32(1) + np.float32(0.25) * N)
    np.clip(bio, 0, C.BIOMASS_MAX, out=bio)
    bio[c25_30 == 7] = 0
    bio = np.round(bio, 1).astype(np.float32)
    del N, c25_30
    write_raw(C.RAW / "sinh_khoi_2025.tif", bio, t30, -9999.0)

    manifest = {"class_res": res, "cont_res": r30, "crs": C.SRC_CRS, "seed": C.SEED,
                "bounds": [minx, miny, maxx, maxy]}
    (C.RAW / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log("Hoàn tất")
    return 0


if __name__ == "__main__":
    sys.exit(main())
