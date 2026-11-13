import { fromUrl, type GeoTIFF, type GeoTIFFImage } from 'geotiff';
import type { Coordinate } from 'ol/coordinate';

export interface OpenedCog {
  tiff: GeoTIFF;
  /** Ảnh độ phân giải gốc (IFD 0). */
  image: GeoTIFFImage;
  origin: number[];
  resolution: number[];
  width: number;
  height: number;
  nodata: number | null;
}

const cache = new Map<string, Promise<OpenedCog>>();

/**
 * Mở COG bằng geotiff.js (chỉ đọc header qua HTTP Range) và giữ lại trong bộ nhớ.
 * OpenLayers không cho truy cập đối tượng GeoTIFF bên trong source, nên mở riêng ở đây.
 */
export function openCog(url: string): Promise<OpenedCog> {
  let p = cache.get(url);
  if (!p) {
    p = (async () => {
      const tiff = await fromUrl(url);
      const image = await tiff.getImage(0);
      return {
        tiff,
        image,
        origin: image.getOrigin(),
        resolution: image.getResolution(),
        width: image.getWidth(),
        height: image.getHeight(),
        nodata: image.getGDALNoData(),
      };
    })();
    p.catch(() => cache.delete(url));
    cache.set(url, p);
  }
  return p;
}

/** Chỉ số pixel (cột, hàng) chứa tọa độ, hoặc null nếu nằm ngoài ảnh. */
export function pixelIndex(cog: OpenedCog, coord: Coordinate): [number, number] | null {
  const [ox, oy] = cog.origin;
  const [rx, ry] = cog.resolution; // ry âm (hàng tăng xuống phía nam)
  const col = Math.floor((coord[0] - ox) / rx);
  const row = Math.floor((coord[1] - oy) / ry);
  if (col < 0 || row < 0 || col >= cog.width || row >= cog.height) return null;
  return [col, row];
}

/**
 * Giá trị pixel tại tọa độ (cùng hệ với COG), đọc ở ĐỘ PHÂN GIẢI GỐC.
 *
 * Không dùng `layer.getData(pixel)` của OpenLayers: hàm đó trả giá trị của tile đang
 * hiển thị, tức là ở mức overview theo mức zoom. Overview AVERAGE của sinh khối sẽ khác
 * giá trị gốc, không đáp ứng yêu cầu "giá trị điểm khớp raster nguồn".
 * Mỗi lần đọc chỉ tải đúng một tile 512×512 (vài KB) qua một request Range.
 *
 * @returns giá trị, hoặc null nếu ngoài ảnh hoặc là NoData.
 */
export async function readValueAt(url: string, coord: Coordinate): Promise<number | null> {
  const cog = await openCog(url);
  const idx = pixelIndex(cog, coord);
  if (!idx) return null;
  const [col, row] = idx;
  const rasters = await cog.image.readRasters({
    window: [col, row, col + 1, row + 1],
    samples: [0],
    interleave: false,
  });
  const value = Number((rasters[0] as ArrayLike<number>)[0]);
  if (cog.nodata !== null && value === cog.nodata) return null;
  return value;
}
