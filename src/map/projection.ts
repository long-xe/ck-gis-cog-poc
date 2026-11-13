import proj4 from 'proj4';
import type Projection from 'ol/proj/Projection';
import { get as getProjection } from 'ol/proj';
import { register } from 'ol/proj/proj4';
import type { CrsDef } from './catalog';

/**
 * Đăng ký hệ VN-2000 cho OpenLayers. PHẢI gọi trước khi tạo View hoặc bất kỳ source nào.
 *
 * - `ol/source/GeoTIFF` đọc ProjectedCSTypeGeoKey (9209) rồi tra `EPSG:9209` trong bộ nhớ.
 *   Nếu chưa đăng ký, OL lặng lẽ tạo một projection rỗng (không có phép chuyển đổi) và
 *   không báo lỗi → lớp COG lệch hẳn khỏi bản đồ nền.
 * - `register(proj4)` không gán extent; thiếu extent thì lưới tile dùng để chiếu lại bản đồ
 *   nền OSM rơi về một "thế giới" ±20 000 km. Vì vậy gán extent ngay sau khi đăng ký.
 * - Muốn thêm định nghĩa proj4 sau này thì phải gọi lại `register(proj4)`.
 */
export function initProjection(crs: CrsDef): Projection {
  proj4.defs(crs.code, crs.proj4);
  register(proj4);
  const projection = getProjection(crs.code);
  if (!projection) throw new Error(`Không đăng ký được ${crs.code}`);
  projection.setExtent(crs.extent);
  projection.setWorldExtent(crs.worldExtent);
  return projection;
}
