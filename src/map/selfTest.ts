import { transform } from 'ol/proj';
import { resolveUrl, type Catalog, type QaPoints } from './catalog';
import { readValueAt } from './pixelQuery';

export interface SelfTestResult {
  passed: number;
  failed: number;
  lines: string[];
}

const PROJ_TOLERANCE_M = 0.01;

/**
 * Tự kiểm tra ở trình duyệt:
 * 1. Phép chiếu WGS 84 → VN-2000 của proj4js khớp PROJ/GDAL (< 0,01 m) tại các điểm mẫu.
 * 2. Giá trị pixel đọc qua `readValueAt` khớp TUYỆT ĐỐI giá trị Python đọc bằng
 *    `src.sample` từ cùng tệp COG (gồm cả pixel ở mép ranh giới, mép lớp, ngoài tỉnh).
 */
export async function runSelfTest(catalog: Catalog, qa: QaPoints): Promise<SelfTestResult> {
  const lines: string[] = [];
  let passed = 0;
  let failed = 0;

  for (const p of qa.projection) {
    const [e, n] = transform(p.lonlat, 'EPSG:4326', catalog.crs.code);
    const d = Math.hypot(e - p.expected[0], n - p.expected[1]);
    if (d < PROJ_TOLERANCE_M) passed++;
    else {
      failed++;
      lines.push(`✗ Phép chiếu tại ${p.lonlat.join(', ')}: lệch ${d.toFixed(3)} m`);
    }
  }
  lines.push(`Phép chiếu: ${qa.projection.length} điểm, sai số cho phép < ${PROJ_TOLERANCE_M} m`);

  for (const layer of catalog.layers) {
    const points = qa.layers[layer.id] ?? [];
    const url = resolveUrl(layer.url);
    let layerFailed = 0;
    for (const pt of points) {
      const got = await readValueAt(url, [pt.x, pt.y]);
      // float32 đọc từ tệp đã là số JS chính xác; JSON của Python lưu đúng giá trị float32 đó.
      const expected = pt.expected === null ? null : Math.fround(pt.expected);
      const same = got === expected || (layer.dtype !== 'float32' && got === pt.expected);
      if (same) passed++;
      else {
        failed++;
        layerFailed++;
        if (layerFailed <= 3) {
          lines.push(`✗ ${layer.id} (${pt.kind}) hàng ${pt.row} cột ${pt.col}: đọc ${got}, cần ${pt.expected}`);
        }
      }
    }
    lines.push(`${layerFailed ? '✗' : '✓'} ${layer.id}: ${points.length - layerFailed}/${points.length} điểm khớp`);
  }
  return { passed, failed, lines };
}
