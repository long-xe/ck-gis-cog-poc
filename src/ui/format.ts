import type { ContinuousLayerDef, LayerDef } from '../map/catalog';
import { hexToRgba } from '../map/styles';

const cache = new Map<number, Intl.NumberFormat>();
function nf(decimals: number): Intl.NumberFormat {
  let f = cache.get(decimals);
  if (!f) {
    f = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    cache.set(decimals, f);
  }
  return f;
}

export const fmt = (value: number, decimals = 0): string => nf(decimals).format(value);
export const fmtHa = (ha: number): string => `${fmt(ha, ha < 100 ? 1 : 0)} ha`;
export const fmtMB = (bytes: number): string => `${fmt(bytes / 1e6, 2)} MB`;
export const fmtKB = (bytes: number): string => `${fmt(bytes / 1024, 0)} KB`;

/** Màu của giá trị trên thang màu (để tô ô màu trong bảng thông tin điểm). */
export function rampColor(def: ContinuousLayerDef, value: number): string {
  const r = def.ramp;
  if (value <= r[0].value) return r[0].color;
  for (let i = 1; i < r.length; i++) {
    if (value <= r[i].value) {
      const t = (value - r[i - 1].value) / (r[i].value - r[i - 1].value);
      const a = hexToRgba(r[i - 1].color);
      const b = hexToRgba(r[i].color);
      const mix = a.slice(0, 3).map((v, k) => Math.round(v + (b[k] - v) * t));
      return `rgb(${mix.join(', ')})`;
    }
  }
  return r[r.length - 1].color;
}

export interface ValueLabel {
  text: string;
  detail?: string;
  color: string | null;
}

/** Diễn giải giá trị pixel theo mô tả lớp. */
export function describeValue(def: LayerDef, value: number | null): ValueLabel {
  if (value === null) return { text: 'Ngoài vùng dữ liệu (NoData)', color: null };
  if (def.kind === 'categorical') {
    const c = def.classes.find((k) => k.value === value);
    return c
      ? { text: c.label, detail: `mã ${value}`, color: c.color }
      : { text: `Mã ${value} (không có trong bảng lớp)`, color: null };
  }
  return { text: `${fmt(value, def.decimals)} ${def.unit}`, color: rampColor(def, value) };
}

export function resolutionBadge(def: LayerDef): string {
  return `${fmt(def.resolution)} m`;
}
