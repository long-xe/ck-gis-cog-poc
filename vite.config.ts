import { defineConfig } from 'vite';

export default defineConfig({
  // 'mpa': tệp không tồn tại trả 404 thay vì index.html (200).
  // Nếu để mặc định 'spa', geotiff.js sẽ nhận nhầm HTML và báo lỗi khó hiểu.
  appType: 'mpa',
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
  build: { target: 'es2022', chunkSizeWarningLimit: 1500 },
});
