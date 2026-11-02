// Rebuild with @viz-js/viz installed outside this design-only repository:
// SPEAKER_VIZ_MODULE=/absolute/path/to/@viz-js/viz/dist/viz.js node components.mjs
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const { instance } = await import(process.env.SPEAKER_VIZ_MODULE || '@viz-js/viz');
const viz = await instance();
for (const stem of ['09-clip-components', '10-web-components']) {
  const source = new URL(`${stem}.dot`, import.meta.url);
  const svg = viz.renderString(await readFile(source, 'utf8'), { format: 'svg', engine: 'dot' });
  await writeFile(fileURLToPath(new URL(`${stem}.svg`, import.meta.url)), svg);
}
