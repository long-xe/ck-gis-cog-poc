import { openCog } from './pixelQuery';

export interface OverviewInfo {
  level: number;
  width: number;
  height: number;
  resolution: number;
}

export interface CogInfo {
  width: number;
  height: number;
  resolution: [number, number];
  origin: [number, number];
  bbox: number[];
  epsg: number | null;
  tileWidth: number;
  tileHeight: number;
  dataType: string;
  nodata: number | null;
  compression: string;
  predictor: string;
  overviews: OverviewInfo[];
  /** Giá trị "ghost" ở đầu tệp do GDAL ghi cho COG (LAYOUT=IFDS_BEFORE_DATA…). */
  ghost: Record<string, unknown> | null;
  gdalMetadata: Record<string, unknown> | null;
  bandMetadata: Record<string, unknown> | null;
}

const COMPRESSION: Record<number, string> = {
  1: 'Không nén',
  5: 'LZW',
  7: 'JPEG',
  8: 'DEFLATE',
  32946: 'DEFLATE',
  34887: 'LERC',
  50000: 'ZSTD',
  50001: 'WEBP',
};
const PREDICTOR: Record<number, string> = {
  1: 'Không (1)',
  2: 'Ngang – số nguyên (2)',
  3: 'Dấu phẩy động (3)',
};
const SAMPLE_FORMAT: Record<number, string> = { 1: 'uint', 2: 'int', 3: 'float' };

/** Đọc metadata trực tiếp từ header của COG (không cần backend). */
export async function readCogInfo(url: string): Promise<CogInfo> {
  const { tiff, image } = await openCog(url);
  const fd = image.getFileDirectory();
  // Đọc TUẦN TỰ: với geotiff 3.1.0-beta.0, hai lần loadValue song song trên cùng một tag
  // hoãn (deferred) làm lần sau trả về null (đã thử: getGDALMetadata() và
  // getGDALMetadata(0) chạy cùng lúc → metadata band rỗng).
  const compression = await fd.loadValue('Compression');
  const predictor = await fd.loadValue('Predictor');
  const count = await tiff.getImageCount();
  const res = image.getResolution();
  const overviews: OverviewInfo[] = [];
  for (let i = 1; i < count; i++) {
    const ov = await tiff.getImage(i);
    overviews.push({
      level: i,
      width: ov.getWidth(),
      height: ov.getHeight(),
      resolution: ov.getResolution(image)[0],
    });
  }
  const geoKeys = image.getGeoKeys();
  const sampleFormat = image.getSampleFormat(0);
  const ghost = await tiff.getGhostValues();
  const gdalMetadata = await image.getGDALMetadata();
  const bandMetadata = await image.getGDALMetadata(0);
  return {
    width: image.getWidth(),
    height: image.getHeight(),
    resolution: [res[0], res[1]],
    origin: [image.getOrigin()[0], image.getOrigin()[1]],
    bbox: image.getBoundingBox(),
    epsg: (geoKeys?.ProjectedCSTypeGeoKey as number | undefined) ?? null,
    tileWidth: image.getTileWidth(),
    tileHeight: image.getTileHeight(),
    dataType: `${SAMPLE_FORMAT[sampleFormat] ?? `format ${sampleFormat}`}${image.getBitsPerSample(0)}`,
    nodata: image.getGDALNoData(),
    compression: COMPRESSION[Number(compression)] ?? `Mã ${String(compression)}`,
    predictor: PREDICTOR[Number(predictor ?? 1)] ?? `Mã ${String(predictor)}`,
    overviews,
    ghost,
    gdalMetadata,
    bandMetadata,
  };
}
