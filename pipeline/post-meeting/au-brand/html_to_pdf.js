// render.js — Chromium (CDP) HTML -> PDF with AU running footer.
// usage: node render.js <input.html> <output.pdf> [title]
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');

const [htmlPath, pdfPath, docTitle] = process.argv.slice(2);
const PORT = 9333;

function get(path) {
  return new Promise((res, rej) => {
    http.get({ host: '127.0.0.1', port: PORT, path }, (r) => {
      let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(d));
    }).on('error', rej);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const chrome = spawn('google-chrome', [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
    '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check',
    `--remote-debugging-port=${PORT}`, '--user-data-dir=/tmp/aubrand/chrome-profile',
    'about:blank',
  ], { stdio: 'ignore' });

  let version = null;
  for (let i = 0; i < 60; i++) {
    try { version = JSON.parse(await get('/json/version')); break; } catch { await sleep(250); }
  }
  if (!version) { chrome.kill(); throw new Error('chrome did not start'); }

  const ws = new WebSocket(version.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const events = [];
  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    const msgId = ++id;
    pending.set(msgId, { res, rej });
    ws.send(JSON.stringify({ id: msgId, method, params, sessionId }));
  });
  await new Promise((r) => (ws.onopen = r));
  let sessionId = null;
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const p = pending.get(m.id); pending.delete(m.id);
      m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
    } else if (m.method) events.push(m);
  };

  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const att = await send('Target.attachToTarget', { targetId, flatten: true });
  sessionId = att.sessionId;

  await send('Page.enable', {}, sessionId);
  await send('Page.navigate', { url: 'file://' + htmlPath }, sessionId);
  for (let i = 0; i < 200; i++) {
    await sleep(100);
    if (events.some((e) => e.method === 'Page.loadEventFired')) break;
  }
  await sleep(900); // fonts + layout settle
  await send('Runtime.evaluate', { expression: 'document.fonts.ready', awaitPromise: true }, sessionId);

  const footer = `
  <div style="width:100%;font-family:Arial,Helvetica,sans-serif;font-size:7.6pt;color:#536174;
              padding:0 16mm;display:flex;justify-content:space-between;align-items:center;">
    <span>aquaponicsunited.com</span>
    <span>${docTitle || ''}</span>
    <span>P&aacute;g. <span class="pageNumber"></span>/<span class="totalPages"></span></span>
  </div>`;

  const { data } = await send('Page.printToPDF', {
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: footer,
    marginTop: 0.51, marginBottom: 0.63, marginLeft: 0.63, marginRight: 0.63,
  }, sessionId);

  fs.writeFileSync(pdfPath, Buffer.from(data, 'base64'));
  console.log('pdf ->', pdfPath, fs.statSync(pdfPath).size, 'bytes');
  ws.close();
  chrome.kill();
  process.exit(0);
})().catch((e) => { console.error('ERROR', e.message); process.exit(1); });
