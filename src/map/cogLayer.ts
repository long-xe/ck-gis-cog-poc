import WebGLTileLayer from 'ol/layer/WebGLTile';
import GeoTIFF from 'ol/source/GeoTIFF';
import { equivalent, type ProjectionLike, get as getProjection } from 'ol/proj';
import { resolveUrl, type LayerDef } from './catalog';
import { buildStyle } from './styles';

export interface CogLayer {
  def: LayerDef;
  layer: WebGLTileLayer;
  source: GeoTIFF;
  /** Hoàn tất khi source đọc xong header COG và projection đã được kiểm tra. */
  ready: Promise<void>;
}

/**
 * Lớp COG hiển thị bằng WebGL, đọc trực tiếp tệp qua HTTP Range (không qua GeoServer).
 *
 * - `normalize: false`: style nhận giá trị gốc (mã lớp, t/ha) thay vì giá trị chuẩn hóa 0..1.
 * - `interpolate: false`: lấy mẫu nearest. Với lớp phân loại để không trộn mã lớp; với lớp
 *   liên tục để mép ranh giới không bị trộn với pixel NoData (lưu là 0 trong texture).
 * - NoData: source tự thêm band alpha từ tag GDAL_NODATA và shader bỏ các pixel đó, nên
 *   không cần khai `nodata` ở đây.
 */
export function createCogLayer(def: LayerDef, viewProjection: ProjectionLike, visible: boolean): CogLayer {
  const source = new GeoTIFF({
    sources: [{ url: resolveUrl(def.url) }],
    normalize: false,
    interpolate: false,
    transition: 0,
  });
  const layer = new WebGLTileLayer({
    source,
    style: buildStyle(def),
    visible,
    properties: { id: def.id, title: def.name },
  });

  const ready = new Promise<void>((resolve, reject) => {
    const check = () => {
      const state = source.getState();
      if (state === 'error') {
        reject(source.getError() ?? new Error(`Không đọc được ${def.url}`));
      } else if (state === 'ready') {
        const proj = source.getProjection();
        const view = getProjection(viewProjection);
        if (!proj || !view || !equivalent(proj, view)) {
          reject(
            new Error(
              `${def.id}: projection của COG (${proj?.getCode() ?? '?'}) khác view ` +
                `(${view?.getCode() ?? '?'}). Kiểm tra initProjection().`,
            ),
          );
        } else {
          resolve();
        }
      } else {
        return; // còn 'loading': chờ sự kiện change tiếp theo
      }
      source.un('change', check);
    };
    source.on('change', check);
    check();
  });
  // Tránh cảnh báo "unhandled rejection"; lỗi được xử lý ở nơi gọi qua `ready`.
  ready.catch(() => {});

  return { def, layer, source, ready };
}
