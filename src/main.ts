import 'ol/ol.css';
import './style.css';
import { transform } from 'ol/proj';
import { loadCatalog, loadQaPoints } from './map/catalog';
import { createCogLayer, type CogLayer } from './map/cogLayer';
import { createMap } from './map/createMap';
import { readValueAt } from './map/pixelQuery';
import { initProjection } from './map/projection';
import { byId, h } from './ui/dom';
import { mountInfoPanel } from './ui/infoPanel';
import { mountLayerPanel } from './ui/layerPanel';
import { mountMetadataPanel } from './ui/metadataPanel';
import { mountNetworkStats, mountSelfTestPanel } from './ui/statusPanels';
import { mountSwipeControl } from './ui/swipeControl';

/** Thứ tự vẽ: dưới → trên. Lớp không có trong danh sách được đặt theo thứ tự catalog. */
const DRAW_ORDER = ['hien_trang_2021', 'hien_trang_2025', 'sinh_khoi_2025', 'carbon_2025', 'bien_dong_2021_2025'];
const DEFAULT_VISIBLE = new Set(['hien_trang_2025']);

async function main(): Promise<void> {
  const catalog = await loadCatalog();
  // Phải đăng ký VN-2000 trước khi tạo View và các source GeoTIFF.
  initProjection(catalog.crs);

  const { map, basemap, boundary } = createMap(byId('map'), catalog, byId('mouse-position'));
  byId('crs-label').textContent = `${catalog.crs.name} · ${catalog.crs.code}`;

  const rank = (id: string) => {
    const i = DRAW_ORDER.indexOf(id);
    return i === -1 ? DRAW_ORDER.length : i;
  };
  const cogLayers: CogLayer[] = [...catalog.layers]
    .sort((a, b) => rank(a.id) - rank(b.id))
    .map((def, i) => {
      const c = createCogLayer(def, catalog.crs.code, DEFAULT_VISIBLE.has(def.id));
      c.layer.setZIndex(10 + i);
      map.addLayer(c.layer);
      return c;
    });
  const topFirst = [...cogLayers].reverse();
  const byLayerId = (id: string): CogLayer => {
    const c = cogLayers.find((l) => l.def.id === id);
    if (!c) throw new Error(`catalog.swipe trỏ tới lớp không tồn tại: ${id}`);
    return c;
  };

  const metadata = mountMetadataPanel(byId('metadata-panel'));
  mountLayerPanel(byId('layer-panel'), {
    cogLayers: topFirst,
    basemap,
    boundary,
    onShowMetadata: (c) => metadata.open(c.def),
  });
  mountInfoPanel(byId('info-panel'), map, topFirst, catalog.crs.code);
  mountSwipeControl(byId('compare-panel'), byId('swipe-ui'), map, byLayerId(catalog.swipe.left), byLayerId(catalog.swipe.right));
  mountNetworkStats(byId('network-stats'), catalog);

  const results = await Promise.allSettled(cogLayers.map((c) => c.ready));
  const failed = results.filter((r) => r.status === 'rejected').length;
  byId('load-status').textContent = failed
    ? `${failed}/${cogLayers.length} lớp lỗi`
    : `${cogLayers.length} lớp sẵn sàng`;
  byId('load-status').classList.toggle('is-error', failed > 0);
  document.documentElement.dataset.ready = failed ? 'error' : 'true';

  // Dùng để kiểm tra từ DevTools, ví dụ: __poc.transform([106.3, 21.2], 'EPSG:4326', 'EPSG:9209')
  Object.assign(window, { __poc: { map, catalog, cogLayers, transform, readValueAt } });

  await mountSelfTestPanel(byId('selftest-panel'), catalog, () => loadQaPoints());
}

main().catch((err: unknown) => {
  console.error(err);
  document.documentElement.dataset.ready = 'error';
  byId('map').replaceChildren(
    h('div', { class: 'fatal' }, h('h2', null, 'Không khởi tạo được bản đồ'), h('p', null, err instanceof Error ? err.message : String(err))),
  );
});
