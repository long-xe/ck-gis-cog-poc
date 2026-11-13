import type { Style } from 'ol/layer/WebGLTile';
import type { CategoricalLayerDef, ContinuousLayerDef, LayerDef } from './catalog';

type Rgba = [number, number, number, number];
const TRANSPARENT: Rgba = [0, 0, 0, 0];

export function hexToRgba(hex: string, alpha = 1): Rgba {
  const h = hex.replace('#', '');
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
    alpha,
  ];
}

/**
 * Lớp phân loại: tra bảng màu theo mã lớp. Mảng màu dài (mã lớn nhất + 1);
 * mã không dùng hoặc không tô màu (`color: null`) là trong suốt.
 * Cần `normalize: false` ở source để `['band', 1]` là mã lớp gốc.
 */
function categoricalStyle(def: CategoricalLayerDef): Style {
  const maxValue = Math.max(...def.classes.map((c) => c.value));
  const palette: Rgba[] = Array.from({ length: maxValue + 1 }, () => TRANSPARENT);
  for (const c of def.classes) {
    if (c.color) palette[c.value] = hexToRgba(c.color);
  }
  return { color: ['palette', ['band', 1], palette] };
}

/** Lớp liên tục: nội suy tuyến tính theo thang màu; ngoài hai đầu thì kẹp về màu biên. */
function continuousStyle(def: ContinuousLayerDef): Style {
  const stops = def.ramp.flatMap((s) => [s.value, s.color]);
  return { color: ['interpolate', ['linear'], ['band', 1], ...stops] };
}

export function buildStyle(def: LayerDef): Style {
  return def.kind === 'categorical' ? categoricalStyle(def) : continuousStyle(def);
}

/** Dải màu CSS cho chú giải lớp liên tục. */
export function rampGradient(def: ContinuousLayerDef): string {
  const min = def.ramp[0].value;
  const max = def.ramp[def.ramp.length - 1].value;
  const parts = def.ramp.map((s) => `${s.color} ${(((s.value - min) / (max - min)) * 100).toFixed(1)}%`);
  return `linear-gradient(to right, ${parts.join(', ')})`;
}
