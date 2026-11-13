import type BaseLayer from 'ol/layer/Base';
import type { CogLayer } from '../map/cogLayer';
import type { CategoricalLayerDef, ContinuousLayerDef } from '../map/catalog';
import { rampGradient } from '../map/styles';
import { h } from './dom';
import { fmt, fmtHa, resolutionBadge } from './format';

interface LayerPanelOptions {
  /** Thứ tự hiển thị trong panel: trên cùng = lớp vẽ trên cùng. */
  cogLayers: CogLayer[];
  basemap: BaseLayer;
  boundary: BaseLayer;
  onShowMetadata: (layer: CogLayer) => void;
}

function categoricalLegend(def: CategoricalLayerDef): HTMLElement {
  const entries = def.legend ?? def.classes.filter((c) => c.color);
  return h(
    'ul',
    { class: 'legend' },
    ...entries.map((e) =>
      h(
        'li',
        null,
        h('span', { class: 'swatch', style: `background:${e.color}` }),
        h('span', { class: 'legend-label' }, e.label),
        e.area_ha !== undefined ? h('span', { class: 'legend-area' }, fmtHa(e.area_ha)) : null,
      ),
    ),
  );
}

function continuousLegend(def: ContinuousLayerDef): HTMLElement {
  const first = def.ramp[0].value;
  const last = def.ramp[def.ramp.length - 1].value;
  const mid = def.ramp[Math.floor(def.ramp.length / 2)];
  return h(
    'div',
    { class: 'ramp' },
    h('div', { class: 'ramp-title' }, def.legendTitle),
    h('div', { class: 'ramp-bar', style: `background:${rampGradient(def)}` }),
    h(
      'div',
      { class: 'ramp-ticks' },
      h('span', null, fmt(first)),
      h('span', { style: `left:${((mid.value - first) / (last - first)) * 100}%` }, fmt(mid.value)),
      h('span', null, `≥ ${fmt(last)}`),
    ),
    h(
      'dl',
      { class: 'stats' },
      h('dt', null, 'Trung bình'),
      h('dd', null, `${fmt(def.stats.mean, def.decimals)} ${def.unit}`),
      h('dt', null, 'Tổng toàn tỉnh'),
      h('dd', null, `${fmt(def.stats.total / 1e6, 2)} triệu ${def.stats.totalUnit}`),
    ),
  );
}

function layerItem(c: CogLayer, onShowMetadata: (c: CogLayer) => void): HTMLElement {
  const { def, layer } = c;
  const checkbox = h('input', { type: 'checkbox', 'aria-label': `Bật/tắt ${def.name}` });
  const opacity = h('input', { type: 'range', min: 0, max: 100, step: 5, value: 100, 'aria-label': 'Độ mờ' });
  const opacityOut = h('output', null, '100%');
  const status = h('div', { class: 'layer-status' }, 'Đang đọc header COG…');
  const item = h(
    'div',
    { class: 'layer-item' },
    h(
      'div',
      { class: 'layer-row' },
      h('label', { class: 'layer-toggle' }, checkbox, h('span', { class: 'layer-name' }, def.name)),
      h('span', { class: 'badge', title: 'Độ phân giải' }, resolutionBadge(def)),
      h(
        'button',
        {
          class: 'icon-btn',
          type: 'button',
          title: 'Xem metadata COG',
          'aria-label': `Metadata của ${def.name}`,
          onclick: () => onShowMetadata(c),
        },
        'i',
      ),
    ),
    h(
      'div',
      { class: 'layer-body' },
      h('div', { class: 'opacity' }, h('span', null, 'Độ mờ'), opacity, opacityOut),
      def.kind === 'categorical' ? categoricalLegend(def) : continuousLegend(def),
    ),
    status,
  );

  const sync = () => {
    checkbox.checked = layer.getVisible();
    item.classList.toggle('is-on', layer.getVisible());
  };
  checkbox.addEventListener('change', () => layer.setVisible(checkbox.checked));
  opacity.addEventListener('input', () => {
    layer.setOpacity(Number(opacity.value) / 100);
    opacityOut.value = `${opacity.value}%`;
  });
  layer.on('change:visible', sync);
  sync();

  c.ready.then(
    () => status.remove(),
    (err: unknown) => {
      status.textContent = `Lỗi: ${err instanceof Error ? err.message : String(err)}`;
      status.classList.add('is-error');
      item.classList.add('has-error');
    },
  );
  return item;
}

function baseItem(layer: BaseLayer, label: string, note: string): HTMLElement {
  const checkbox = h('input', { type: 'checkbox' });
  checkbox.checked = layer.getVisible();
  checkbox.addEventListener('change', () => layer.setVisible(checkbox.checked));
  return h(
    'label',
    { class: 'base-item' },
    checkbox,
    h('span', null, label),
    h('span', { class: 'muted' }, note),
  );
}

export function mountLayerPanel(root: HTMLElement, opts: LayerPanelOptions): void {
  root.replaceChildren(
    h('h2', null, 'Lớp dữ liệu (COG)'),
    h('div', { class: 'layer-list' }, ...opts.cogLayers.map((c) => layerItem(c, opts.onShowMetadata))),
    h('h2', null, 'Lớp nền'),
    baseItem(opts.boundary, 'Ranh giới tỉnh', 'OSM, VN-2000'),
    baseItem(opts.basemap, 'Bản đồ nền OpenStreetMap', 'chiếu lại sang VN-2000'),
  );
}
