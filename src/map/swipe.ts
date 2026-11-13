import type Map from 'ol/Map';
import type WebGLTileLayer from 'ol/layer/WebGLTile';
import type RenderEvent from 'ol/render/Event';
import { getRenderPixel } from 'ol/render';
import { unByKey } from 'ol/Observable';

/**
 * So sánh hai lớp bằng thanh trượt (TÍNH NĂNG THÊM CỦA PoC – không thuộc phạm vi UC09).
 *
 * Lớp `top` (ví dụ 2025) nằm trên lớp kia; chỉ vẽ phần bên phải vị trí thanh trượt bằng
 * WebGL scissor, nên bên trái lộ ra lớp dưới (2021). Cách làm theo ví dụ
 * `webgl-layer-swipe` của OpenLayers. `getRenderPixel` đổi pixel CSS sang pixel của
 * canvas (tính cả devicePixelRatio).
 *
 * @returns hàm gỡ swipe.
 */
export function attachSwipe(map: Map, top: WebGLTileLayer, getRatio: () => number): () => void {
  const keys = [
    top.on('prerender', (event: RenderEvent) => {
      const gl = event.context as WebGLRenderingContext;
      const size = map.getSize();
      if (!size) return;
      const bottomLeft = getRenderPixel(event, [0, size[1]]);
      const topRight = getRenderPixel(event, [size[0], 0]);
      const fullWidth = topRight[0] - bottomLeft[0];
      const offset = Math.round(fullWidth * getRatio());
      gl.enable(gl.SCISSOR_TEST);
      gl.scissor(bottomLeft[0] + offset, bottomLeft[1], fullWidth - offset, topRight[1] - bottomLeft[1]);
    }),
    top.on('postrender', (event: RenderEvent) => {
      const gl = event.context as WebGLRenderingContext;
      gl.disable(gl.SCISSOR_TEST);
    }),
  ];
  map.render();
  return () => {
    unByKey(keys);
    map.render();
  };
}
