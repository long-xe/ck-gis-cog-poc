import MousePosition from 'ol/control/MousePosition';
import ScaleLine from 'ol/control/ScaleLine';
import type { Coordinate } from 'ol/coordinate';
import { toLonLat } from 'ol/proj';

const meters = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const degrees = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 6, maximumFractionDigits: 6 });

/**
 * Tọa độ theo quy ước Việt Nam: X là tọa độ Bắc (Northing), Y là tọa độ Đông (Easting).
 * Trục của EPSG:9209 là (Easting, Northing) nên coord[0] = Y, coord[1] = X.
 */
export function formatVn2000(coord: Coordinate): string {
  return `X ${meters.format(coord[1])} m · Y ${meters.format(coord[0])} m`;
}

/** Kinh/vĩ độ WGS 84, đổi bằng proj4 (đã gồm tham số towgs84 của VN-2000). */
export function formatLonLat(coord: Coordinate, projection: string): string {
  const [lon, lat] = toLonLat(coord, projection);
  return `${degrees.format(lat)}° N · ${degrees.format(lon)}° E`;
}

export function createMousePosition(target: HTMLElement, projection: string): MousePosition {
  return new MousePosition({
    projection,
    target,
    className: 'mouse-position',
    wrapX: false,
    placeholder: 'Di chuột trên bản đồ để xem tọa độ',
    coordinateFormat: (c) =>
      c
        ? `<span class="crs-tag">VN-2000</span> ${formatVn2000(c)}` +
          `<span class="sep">|</span><span class="crs-tag">WGS 84</span> ${formatLonLat(c, projection)}`
        : '',
  });
}

export function createScaleLine(): ScaleLine {
  return new ScaleLine({ units: 'metric', bar: true, steps: 4, text: true, minWidth: 120 });
}
