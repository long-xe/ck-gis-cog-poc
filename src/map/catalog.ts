/**
 * Mô tả lớp (catalog.json) do scripts/etl_to_cog.py sinh ra.
 * Đóng vai trò "mô tả lớp" mà API thật sẽ trả về sau này.
 */

export interface CrsDef {
  code: string;
  name: string;
  proj4: string;
  /** Vùng hợp lệ của projection theo đơn vị của nó (m). */
  extent: [number, number, number, number];
  /** Vùng hợp lệ theo kinh/vĩ độ. */
  worldExtent: [number, number, number, number];
}

export interface ClassEntry {
  value: number;
  label: string;
  /** null = không tô màu (ví dụ pixel "không đổi" của lớp biến động). */
  color: string | null;
  area_ha?: number;
  group?: string | null;
  forest?: boolean;
}

export interface LegendEntry {
  label: string;
  color: string;
  area_ha?: number;
}

export interface RampStop {
  value: number;
  color: string;
}

interface LayerBase {
  id: string;
  name: string;
  group: string;
  year: number;
  url: string;
  dtype: string;
  nodata: number;
  resolution: number;
  width: number;
  height: number;
  unit: string;
  bytes: number;
  sha256: string;
}

export interface CategoricalLayerDef extends LayerBase {
  kind: 'categorical';
  classes: ClassEntry[];
  /** Chú giải gộp nhóm (nếu có); không có thì chú giải là `classes`. */
  legend?: LegendEntry[];
}

export interface ContinuousLayerDef extends LayerBase {
  kind: 'continuous';
  ramp: RampStop[];
  decimals: number;
  legendTitle: string;
  stats: { min: number; max: number; mean: number; total: number; totalUnit: string };
}

export type LayerDef = CategoricalLayerDef | ContinuousLayerDef;

export interface Catalog {
  version: number;
  generatedAt: string;
  note: string;
  crs: CrsDef;
  extent: [number, number, number, number];
  boundary: { url: string; attribution: string };
  swipe: { left: string; right: string };
  layers: LayerDef[];
  transitionMatrix: { unit: string; from: number; to: number; classes: number[]; rows: number[][] };
}

export interface QaPoint {
  x: number;
  y: number;
  row: number;
  col: number;
  kind: string;
  expected: number | null;
}

export interface QaPoints {
  layers: Record<string, QaPoint[]>;
  projection: { lonlat: [number, number]; expected: [number, number] }[];
}

/** URL tuyệt đối của một đường dẫn tương đối trong thư mục public. */
export function resolveUrl(path: string): string {
  return new URL(path, new URL(import.meta.env.BASE_URL, window.location.href)).href;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(resolveUrl(path));
  if (!res.ok) throw new Error(`Không tải được ${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export async function loadCatalog(path = 'cog/catalog.json'): Promise<Catalog> {
  const catalog = await getJson<Catalog>(path);
  if (catalog.version !== 1 || !Array.isArray(catalog.layers) || !catalog.crs?.proj4) {
    throw new Error('catalog.json không đúng định dạng (cần version 1, crs, layers).');
  }
  return catalog;
}

export function loadQaPoints(path = 'cog/qa_points.json'): Promise<QaPoints> {
  return getJson<QaPoints>(path);
}

export function findLayer(catalog: Catalog, id: string): LayerDef {
  const layer = catalog.layers.find((l) => l.id === id);
  if (!layer) throw new Error(`Không có lớp ${id} trong catalog`);
  return layer;
}
