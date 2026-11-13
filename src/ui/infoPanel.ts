import type Map from 'ol/Map';
import Overlay from 'ol/Overlay';
import type { Coordinate } from 'ol/coordinate';
import type { CogLayer } from '../map/cogLayer';
import { resolveUrl } from '../map/catalog';
import { formatLonLat, formatVn2000 } from '../map/coordinates';
import { openCog, pixelIndex, readValueAt } from '../map/pixelQuery';
import { h } from './dom';
import { describeValue, fmt } from './format';

/**
 * Click lên bản đồ → giá trị pixel của mọi lớp COG đang bật, đọc ở độ phân giải gốc
 * (khớp raster nguồn, theo kịch bản KB04).
 */
export function mountInfoPanel(root: HTMLElement, map: Map, cogLayers: CogLayer[], projection: string): void {
  const marker = new Overlay({
    element: h('div', { class: 'click-marker' }),
    positioning: 'center-center',
    stopEvent: false,
  });
  map.addOverlay(marker);
  let requestId = 0;

  const close = () => {
    root.hidden = true;
    marker.setPosition(undefined);
    requestId++;
  };

  async function show(coord: Coordinate) {
    const id = ++requestId;
    marker.setPosition(coord);
    const visible = cogLayers.filter((c) => c.layer.getVisible());
    const body = h('div', { class: 'info-body' });
    root.replaceChildren(
      h(
        'div',
        { class: 'info-head' },
        h('h3', null, 'Thông tin điểm'),
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Đóng', onclick: close }, '×'),
      ),
      h(
        'div',
        { class: 'info-coords' },
        h('div', null, h('span', { class: 'crs-tag' }, 'VN-2000'), ' ', formatVn2000(coord)),
        h('div', null, h('span', { class: 'crs-tag' }, 'WGS 84'), ' ', formatLonLat(coord, projection)),
      ),
      body,
      h('p', { class: 'info-note' }, 'Giá trị đọc trực tiếp từ COG ở độ phân giải gốc (một request Range cho mỗi lớp).'),
    );
    root.hidden = false;

    if (!visible.length) {
      body.append(h('p', { class: 'muted' }, 'Chưa bật lớp dữ liệu nào.'));
      return;
    }
    const rows = visible.map((c) => {
      const row = h(
        'div',
        { class: 'info-row is-loading' },
        h('span', { class: 'swatch' }),
        h('div', null, h('div', { class: 'info-layer' }, c.def.name), h('div', { class: 'info-value' }, 'Đang đọc…')),
      );
      body.append(row);
      return row;
    });

    await Promise.all(
      visible.map(async (c, i) => {
        const row = rows[i];
        try {
          const url = resolveUrl(c.def.url);
          const [value, cog] = await Promise.all([readValueAt(url, coord), openCog(url)]);
          if (id !== requestId) return;
          const idx = pixelIndex(cog, coord);
          const label = describeValue(c.def, value);
          const swatch = row.querySelector<HTMLElement>('.swatch');
          if (swatch) {
            swatch.style.background = label.color ?? 'transparent';
            swatch.classList.toggle('is-empty', !label.color);
          }
          row.querySelector('.info-value')?.replaceChildren(
            label.text,
            label.detail ? h('span', { class: 'muted' }, ` · ${label.detail}`) : '',
            idx ? h('span', { class: 'muted' }, ` · hàng ${fmt(idx[1])}, cột ${fmt(idx[0])}`) : '',
          );
        } catch (err) {
          row.querySelector('.info-value')!.textContent = `Lỗi: ${err instanceof Error ? err.message : String(err)}`;
        } finally {
          row.classList.remove('is-loading');
        }
      }),
    );
  }

  map.on('singleclick', (evt) => {
    void show(evt.coordinate);
  });
  root.hidden = true;
}
