import type { Catalog, QaPoints } from '../map/catalog';
import { runSelfTest } from '../map/selfTest';
import { h } from './dom';
import { fmt, fmtKB } from './format';

/** Nút chạy self-test; tự chạy nếu URL có `?selftest`. Kết quả cũng ghi ra console. */
export function mountSelfTestPanel(
  root: HTMLElement,
  catalog: Catalog,
  loadQa: () => Promise<QaPoints>,
): Promise<void> | void {
  const out = h('pre', { class: 'selftest-out', hidden: true });
  const button = h('button', { class: 'btn', type: 'button' }, 'Chạy self-test');

  const run = async () => {
    button.disabled = true;
    out.hidden = false;
    out.className = 'selftest-out';
    out.textContent = 'Đang kiểm tra…';
    try {
      const result = await runSelfTest(catalog, await loadQa());
      const ok = result.failed === 0;
      out.classList.add(ok ? 'is-ok' : 'is-fail');
      out.textContent = [
        `${ok ? 'ĐẠT' : 'KHÔNG ĐẠT'}: ${result.passed} khớp, ${result.failed} lệch`,
        ...result.lines,
      ].join('\n');
      console.info('[self-test]', ok ? 'ĐẠT' : 'KHÔNG ĐẠT', result);
      document.documentElement.dataset.selftest = ok ? 'pass' : 'fail';
    } catch (err) {
      out.classList.add('is-fail');
      out.textContent = `Lỗi: ${err instanceof Error ? err.message : String(err)}`;
      document.documentElement.dataset.selftest = 'error';
    } finally {
      button.disabled = false;
    }
  };
  button.addEventListener('click', () => void run());

  root.replaceChildren(
    h('h2', null, 'Kiểm tra'),
    h(
      'p',
      { class: 'muted small' },
      'So giá trị pixel đọc ở trình duyệt với giá trị Python ghi lúc ETL (qa_points.json), và phép chiếu proj4 với PROJ.',
    ),
    button,
    out,
  );
  if (new URLSearchParams(window.location.search).has('selftest')) return run();
}

/**
 * Đếm request tải COG (Resource Timing): chứng minh trình duyệt chỉ tải từng phần tệp
 * qua HTTP Range, không tải nguyên tệp.
 */
export function mountNetworkStats(root: HTMLElement, catalog: Catalog): void {
  const total = catalog.layers.reduce((s, l) => s + l.bytes, 0);
  let count = 0;
  let bytes = 0;
  const render = () => {
    root.textContent = `COG ${fmt(count)} req · ${fmtKB(bytes)} / ${fmt(total / 1e6, 1)} MB`;
  };
  const observer = new PerformanceObserver((list) => {
    for (const e of list.getEntries() as PerformanceResourceTiming[]) {
      if (!/\/cog\/[^/]+\.tif(\?|$)/.test(e.name)) continue;
      count++;
      bytes += e.transferSize || e.encodedBodySize || 0;
    }
    render();
  });
  observer.observe({ type: 'resource', buffered: true });
  root.title = 'Số request và dung lượng thực tải các tệp COG (Resource Timing API)';
  render();
}
