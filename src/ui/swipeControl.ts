import type Map from 'ol/Map';
import type { CogLayer } from '../map/cogLayer';
import { attachSwipe } from '../map/swipe';
import { h } from './dom';

/**
 * Nút bật/tắt so sánh và thanh kéo trên bản đồ.
 * TÍNH NĂNG THÊM CỦA PoC – "side-by-side / swipe comparison" nằm ngoài phạm vi UC09.
 */
export function mountSwipeControl(
  panel: HTMLElement,
  overlay: HTMLElement,
  map: Map,
  left: CogLayer,
  right: CogLayer,
): void {
  let ratio = 0.5;
  let detach: (() => void) | null = null;

  const toggle = h('input', { type: 'checkbox', role: 'switch' });
  const handle = h('div', { class: 'swipe-handle', role: 'slider', tabindex: 0, 'aria-label': 'Vị trí so sánh' });
  const divider = h('div', { class: 'swipe-divider' }, handle);
  overlay.replaceChildren(
    h('div', { class: 'swipe-label is-left' }, left.def.name),
    h('div', { class: 'swipe-label is-right' }, right.def.name),
    divider,
  );

  const place = () => {
    divider.style.left = `${ratio * 100}%`;
    handle.setAttribute('aria-valuenow', String(Math.round(ratio * 100)));
    map.render();
  };

  const setOn = (on: boolean) => {
    toggle.checked = on;
    overlay.hidden = !on;
    detach?.();
    detach = null;
    if (on) {
      left.layer.setVisible(true);
      right.layer.setVisible(true);
      detach = attachSwipe(map, right.layer, () => ratio);
      place();
    }
  };

  handle.addEventListener('pointerdown', (e) => {
    handle.setPointerCapture(e.pointerId);
    handle.classList.add('is-dragging');
  });
  handle.addEventListener('pointermove', (e) => {
    if (!handle.hasPointerCapture(e.pointerId)) return;
    const rect = overlay.getBoundingClientRect();
    ratio = Math.min(0.98, Math.max(0.02, (e.clientX - rect.left) / rect.width));
    place();
  });
  handle.addEventListener('pointerup', (e) => {
    handle.releasePointerCapture(e.pointerId);
    handle.classList.remove('is-dragging');
  });
  handle.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 0.1 : 0.02;
    if (e.key === 'ArrowLeft') ratio = Math.max(0.02, ratio - step);
    else if (e.key === 'ArrowRight') ratio = Math.min(0.98, ratio + step);
    else return;
    e.preventDefault();
    place();
  });
  toggle.addEventListener('change', () => setOn(toggle.checked));

  panel.replaceChildren(
    h('h2', null, 'So sánh'),
    h(
      'label',
      { class: 'switch-row' },
      toggle,
      h('span', { class: 'switch' }),
      h('span', null, `Kéo để so sánh ${left.def.year} / ${right.def.year}`),
    ),
    h('p', { class: 'extra-note' }, 'Tính năng thêm của PoC, không thuộc phạm vi UC09.'),
  );
  overlay.hidden = true;
}
