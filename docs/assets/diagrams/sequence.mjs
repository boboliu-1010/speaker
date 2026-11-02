// Render with an externally installed Mermaid CLI; Chrome is configured by
// PUPPETEER_EXECUTABLE_PATH when the CLI has no bundled browser.
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
execFileSync(process.env.SPEAKER_MERMAID_CLI || 'mmdc', [
  '--input', fileURLToPath(new URL('09b-clip-processing.mmd', import.meta.url)),
  '--output', fileURLToPath(new URL('09b-clip-processing.svg', import.meta.url)),
  '--backgroundColor', 'white',
], { stdio: 'inherit' });
