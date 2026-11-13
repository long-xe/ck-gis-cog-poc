# CK-GIS – PoC hiển thị raster COG (VN-2000) bằng OpenLayers

PoC thuần frontend. Raster đầu ra của ETL (Cloud Optimized GeoTIFF, hệ VN-2000 / TM-3 kinh tuyến trục 105°30′, **EPSG:9209**) được trình duyệt đọc trực tiếp qua HTTP Range và hiển thị bằng OpenLayers. Không cần backend hay GeoServer.

> **Dữ liệu giả lập.** Bảng lớp hiện trạng, sinh khối, tỷ lệ biến động… chỉ để có raster trông hợp lý. Đây không phải số liệu thật. Ranh giới tỉnh lấy từ OpenStreetMap (ODbL).

## PoC chứng minh điều gì

| Mục tiêu | Cách kiểm chứng |
|---|---|
| Trình duyệt đọc COG trực tiếp, chỉ tải phần cần | Mọi request tới `.tif` là `206 Partial Content`. Thanh trạng thái đếm số request và số KB đã tải so với tổng dung lượng |
| Hiển thị đúng VN-2000, khớp bản đồ nền | View dùng chính EPSG:9209 nên COG được vẽ không chiếu lại. OSM do OpenLayers chiếu lại. Phép chiếu ở trình duyệt khớp PROJ/GDAL dưới 0,01 m |
| Giá trị click khớp raster nguồn (KB04) | Đọc pixel ở độ phân giải gốc bằng geotiff.js. Self-test so 275 điểm với giá trị Python, kết quả khớp tuyệt đối |

## Chạy

Cần Node 24 trở lên, và Python 3.13 nếu muốn sinh lại dữ liệu.

```bash
npm install
npm run dev            # http://localhost:5173  (thêm ?selftest để tự chạy kiểm tra)
npm run build && npm run preview   # bản build, http://localhost:4173
```

Các tệp `public/cog/*.tif` không đưa vào git. Nếu chưa có, sinh lại như sau (seed cố định, mất khoảng 2 phút, RAM đỉnh khoảng 2,4 GB):

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/check_proj.py        # so phép chiếu PROJ và proj4 ở trình duyệt
.venv/bin/python scripts/fetch_boundary.py    # ranh giới OSM (tải 1 lần, có cache trong data/)
.venv/bin/python scripts/make_raw_mocks.py    # raster "thô" UTM 48N (thêm --res 20 để chạy nhanh)
.venv/bin/python scripts/etl_to_cog.py        # ETL → public/cog/*.tif + catalog.json + qa_points.json
.venv/bin/python scripts/check_cogs.py        # QA/QC các COG cuối
```

## Dữ liệu

Chuỗi ETL giả lập gồm ba bước:
1. **Thô:** WGS 84 / UTM 48N, phủ rộng hơn ranh giới 2 km.
2. **Chuyển đổi:** chiếu sang EPSG:9209 trên lưới có gốc là bội số 30 m, cắt theo ranh giới tỉnh.
3. **Nạp:** ghi ra COG nén DEFLATE, tile 512, kèm overview.

| Lớp | Kiểu | Độ phân giải | Ghi chú |
|---|---|---|---|
| `hien_trang_2021`, `hien_trang_2025` | uint8, NoData 0 | 10 m (11 967 × 7 275) | 7 lớp giả lập; overview tính bằng MODE (giữ đúng mã lớp) |
| `bien_dong_2021_2025` | uint8 | 10 m | Mã = 2021 × 10 + 2025, tính theo từng pixel. Chú giải gộp 4 nhóm; pixel không đổi để trong suốt |
| `sinh_khoi_2025` | float32, NoData −9999 | 30 m | t/ha; overview AVERAGE; predictor 3 |
| `carbon_2025` | float32, NoData −9999 | 30 m | = sinh khối × 0,47 (tC/ha) |

- Tổng dung lượng khoảng 33 MB.
- Mỗi tệp mang sẵn tag metadata theo yêu cầu: `LAYER_CODE`, `DATA_SOURCE`, `ACQUISITION_DATE`, `UPDATE_TIME`, `PROCESSING_VERSION`, `QAQC_STATUS`, `CRS_NAME`, `ETL_STEPS`. Panel "i" của từng lớp đọc thẳng các tag này từ header COG.
- `catalog.json` đóng vai trò "mô tả lớp" mà API thật sẽ trả về sau này: url, bảng lớp, thang màu, diện tích, ma trận chuyển đổi.

## Cấu trúc mã

```
src/map/   lõi bản đồ, không phụ thuộc framework (chép được sang admin/src/map/)
  projection.ts   đăng ký EPSG:9209 (proj4 + register + setExtent), phải gọi trước khi tạo View/source
  cogLayer.ts     WebGLTile + ol/source/GeoTIFF (normalize:false, interpolate:false), kiểm tra projection
  styles.ts       biểu thức style: palette (phân loại), interpolate (liên tục)
  pixelQuery.ts   đọc giá trị pixel ở độ phân giải gốc bằng geotiff.js
  cogMetadata.ts  đọc metadata từ header COG
  coordinates.ts  ô tọa độ (X = Bắc, Y = Đông theo quy ước VN-2000) và thước tỷ lệ
  swipe.ts        so sánh bằng WebGL scissor
  selfTest.ts     kiểm tra phép chiếu và giá trị pixel
src/ui/    giao diện DOM thuần cho PoC (không chép sang app thật)
scripts/   sinh dữ liệu giả lập, ETL và QA (Python)
```

## Ghi chú kỹ thuật

- **Chuỗi `+towgs84` phải đảo dấu 3 tham số xoay.**
  - EPSG công bố 7 tham số VN-2000 theo quy ước *coordinate frame*, còn proj4 hiểu `+towgs84` theo quy ước *position vector*.
  - Chuỗi trong `public/config.json` của app admin giữ nguyên dấu nên lệch khoảng **0,76 m** so với GDAL. Chuỗi dùng trong PoC khớp tuyệt đối (`scripts/check_proj.py`).
  - Nếu bỏ hẳn `towgs84` thì lệch khoảng 224 m.
- **NoData:** source GeoTIFF tự tạo band alpha từ tag `GDAL_NODATA`, nên style không cần xử lý NoData.
- **`interpolate: false` cho cả lớp liên tục.** Nếu để nội suy, pixel ở mép ranh giới bị trộn với NoData (lưu là 0 trong texture) và tạo ra một viền tối.
- **`appType: 'mpa'` trong `vite.config.ts`.** Với chế độ SPA mặc định, tệp `.tif` thiếu bị trả về `index.html` kèm mã 200, và geotiff.js báo lỗi khó hiểu.
- **`geotiff` ghim đúng bản 3.1.0-beta.0,** trùng bản OpenLayers 10.11 dùng (`npm ls geotiff` chỉ ra 1 bản).
  - Bản này có lỗi: hai lệnh `getGDALMetadata()` chạy song song làm lệnh sau trả `null`.
  - Vì vậy `cogMetadata.ts` đọc tuần tự.
- **Click lấy giá trị bằng geotiff.js, không dùng `layer.getData()`.** `getData` trả giá trị ở mức overview đang hiển thị; với overview AVERAGE, giá trị đó khác giá trị gốc.

## Điểm cần chốt / ngoài phạm vi

- **So sánh swipe 2021/2025 là tính năng thêm của PoC.** "Side-by-side / swipe comparison" nằm ngoài phạm vi UC09.
- **Kinh tuyến trục cho tỉnh sau sáp nhập vẫn chờ chốt.**
  - EPSG:9209 có vùng áp dụng chính thức tới 106,69E, trong khi tỉnh kéo dài tới 107,03E.
  - Về tính toán thì không ảnh hưởng. Nếu đổi kinh tuyến trục, chỉ cần sửa `DST_CRS` / `PROJ4_*` trong `scripts/config.py` rồi chạy lại ETL.
- **Sửa chuỗi `towgs84` trong app admin là một quyết định riêng,** chưa thực hiện ở đây.
- **Cần mạng internet** để tải bản đồ nền OSM. Bản thân COG được phục vụ hoàn toàn từ máy chạy PoC.
