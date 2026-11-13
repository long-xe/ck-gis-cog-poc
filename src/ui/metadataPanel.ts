import type { LayerDef } from '../map/catalog';
import { resolveUrl } from '../map/catalog';
import { readCogInfo, type CogInfo } from '../map/cogMetadata';
import { h } from './dom';
import { fmt, fmtMB } from './format';

type Row = [string, string | Node];

function table(rows: Row[]): HTMLElement {
  return h('dl', { class: 'kv' }, ...rows.flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)]));
}

function section(title: string, content: HTMLElement): HTMLElement {
  return h('section', { class: 'md-section' }, h('h4', null, title), content);
}

function recordRows(rec: Record<string, unknown> | null): Row[] {
  if (!rec || !Object.keys(rec).length) return [['—', 'Không có']];
  return Object.entries(rec).map(([k, v]) => [k, String(v)]);
}

function render(def: LayerDef, info: CogInfo): HTMLElement[] {
  const m = (v: number) => `${fmt(v, 2)} m`;
  return [
    section(
      'Tệp',
      table([
        ['Đường dẫn', h('code', null, def.url)],
        ['Dung lượng', fmtMB(def.bytes)],
        ['SHA-256', h('code', { title: def.sha256 }, `${def.sha256.slice(0, 16)}…`)],
      ]),
    ),
    section(
      'Hệ tọa độ và lưới',
      table([
        ['CRS (GeoKey)', info.epsg ? `EPSG:${info.epsg}` : 'Không có mã EPSG'],
        ['Tên', String(info.gdalMetadata?.CRS_NAME ?? '—')],
        ['Kích thước', `${fmt(info.width)} × ${fmt(info.height)} px`],
        ['Độ phân giải', `${fmt(info.resolution[0], 2)} × ${fmt(Math.abs(info.resolution[1]), 2)} m`],
        ['Gốc (góc trên trái)', `Y ${m(info.origin[0])} · X ${m(info.origin[1])}`],
        [
          'Khung bao',
          `${fmt(info.bbox[0])}, ${fmt(info.bbox[1])} – ${fmt(info.bbox[2])}, ${fmt(info.bbox[3])}`,
        ],
      ]),
    ),
    section(
      'Cấu trúc COG',
      table([
        ['Tile', `${info.tileWidth} × ${info.tileHeight} px`],
        ['Kiểu dữ liệu', info.dataType],
        ['NoData', info.nodata === null ? 'Không khai báo' : String(info.nodata)],
        ['Nén', info.compression],
        ['Predictor', info.predictor],
        ['Số overview', String(info.overviews.length)],
      ]),
    ),
    section(
      'Overview (kim tự tháp ảnh)',
      h(
        'table',
        { class: 'ovr' },
        h('thead', null, h('tr', null, h('th', null, 'Mức'), h('th', null, 'Kích thước'), h('th', null, 'Độ phân giải'))),
        h(
          'tbody',
          null,
          h('tr', null, h('td', null, 'Gốc'), h('td', null, `${fmt(info.width)} × ${fmt(info.height)}`), h('td', null, m(info.resolution[0]))),
          ...info.overviews.map((o) =>
            h('tr', null, h('td', null, String(o.level)), h('td', null, `${fmt(o.width)} × ${fmt(o.height)}`), h('td', null, m(o.resolution))),
          ),
        ),
      ),
    ),
    section('Ghost header (dấu hiệu COG của GDAL)', table(recordRows(info.ghost))),
    section('Metadata lớp (tag GDAL)', table(recordRows(info.gdalMetadata))),
    section('Metadata band', table(recordRows(info.bandMetadata))),
  ];
}

export interface MetadataPanel {
  open(def: LayerDef): void;
}

/** Panel metadata đọc thẳng từ header COG bằng geotiff.js. */
export function mountMetadataPanel(root: HTMLElement): MetadataPanel {
  let current = 0;
  const close = () => {
    root.hidden = true;
    current++;
  };
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !root.hidden) close();
  });

  return {
    open(def) {
      const id = ++current;
      const body = h('div', { class: 'md-body' }, h('p', { class: 'muted' }, 'Đang đọc header COG…'));
      root.replaceChildren(
        h(
          'div',
          { class: 'md-head' },
          h('div', null, h('div', { class: 'eyebrow' }, 'Metadata COG'), h('h3', null, def.name)),
          h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Đóng', onclick: close }, '×'),
        ),
        body,
      );
      root.hidden = false;
      readCogInfo(resolveUrl(def.url)).then(
        (info) => {
          if (id === current) body.replaceChildren(...render(def, info));
        },
        (err: unknown) => {
          if (id === current) {
            body.replaceChildren(h('p', { class: 'error' }, `Lỗi: ${err instanceof Error ? err.message : String(err)}`));
          }
        },
      );
    },
  };
}
