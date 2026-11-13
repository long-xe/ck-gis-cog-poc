import Map from 'ol/Map';
import View from 'ol/View';
import type BaseLayer from 'ol/layer/Base';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
import OSM from 'ol/source/OSM';
import VectorSource from 'ol/source/Vector';
import GeoJSON from 'ol/format/GeoJSON';
import { defaults as defaultControls } from 'ol/control/defaults';
import ZoomToExtent from 'ol/control/ZoomToExtent';
import { buffer, type Extent } from 'ol/extent';
import { resolveUrl, type Catalog } from './catalog';
import { createMousePosition, createScaleLine } from './coordinates';

export interface MapParts {
  map: Map;
  view: View;
  basemap: TileLayer<OSM>;
  boundary: BaseLayer;
  dataExtent: Extent;
}

/**
 * Bản đồ dùng chính hệ VN-2000 của COG làm hệ hiển thị:
 * - COG cùng hệ với view → OpenLayers vẽ thẳng pixel, không chiếu lại raster dữ liệu;
 * - bản đồ nền OSM (Web Mercator) được OpenLayers tự chiếu lại sang VN-2000 ở trình duyệt.
 * Phải gọi `initProjection()` trước hàm này.
 */
export function createMap(
  target: HTMLElement,
  catalog: Catalog,
  mousePositionTarget: HTMLElement,
): MapParts {
  const projection = catalog.crs.code;
  const dataExtent = catalog.extent;

  const basemap = new TileLayer({
    source: new OSM(),
    properties: { id: 'basemap', title: 'Bản đồ nền OpenStreetMap' },
  });

  const boundary = new VectorLayer({
    source: new VectorSource({
      url: resolveUrl(catalog.boundary.url),
      // Tệp đã ở VN-2000 nên không chiếu lại.
      format: new GeoJSON({ dataProjection: projection, featureProjection: projection }),
      attributions: catalog.boundary.attribution,
    }),
    style: [
      { 'stroke-color': 'rgba(255, 255, 255, 0.85)', 'stroke-width': 4.5 },
      { 'stroke-color': '#7a1f2b', 'stroke-width': 1.75, 'stroke-line-dash': [10, 5] },
    ],
    zIndex: 100,
    properties: { id: 'boundary', title: 'Ranh giới tỉnh' },
  });

  const view = new View({
    projection,
    extent: buffer(dataExtent, 40_000),
    constrainOnlyCenter: true,
    showFullExtent: true,
    maxZoom: 22,
  });

  const map = new Map({
    target,
    layers: [basemap, boundary],
    view,
    controls: defaultControls({ attributionOptions: { collapsible: true, collapsed: false } }).extend([
      new ZoomToExtent({ extent: dataExtent, label: '⤢', tipLabel: 'Xem toàn tỉnh' }),
      createScaleLine(),
      createMousePosition(mousePositionTarget, projection),
    ]),
  });
  view.fit(dataExtent, { padding: [24, 24, 24, 24] });

  return { map, view, basemap, boundary, dataExtent };
}
