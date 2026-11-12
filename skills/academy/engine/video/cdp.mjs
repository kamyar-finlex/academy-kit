// Headless Google Chrome over the DevTools protocol, with nothing installed:
// Node 22's own WebSocket and fetch.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

const CHROME = process.env.CHROME_BIN || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
// 1600x900 CSS pixels at 1.2 = 1920x1080 frames.
export const VIEW = { width: 1920, height: 1080, deviceScaleFactor: 1 };

export async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "academy-kit-"));
  const child = spawn(CHROME, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--hide-scrollbars", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
    `--window-size=${VIEW.width},${VIEW.height}`,
    // CHROME_OFFLINE=1: no network at all (a dead proxy, no background traffic); file:// still loads.
    ...(process.env.CHROME_OFFLINE ? ["--proxy-server=127.0.0.1:9", "--disable-background-networking", "--disable-component-update",
      "--no-pings", "--disable-domain-reliability", "--disable-sync"] : []),
    "about:blank",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  const ws = await new Promise((resolve, reject) => {
    let seen = "";
    const t = setTimeout(() => reject(new Error("chrome did not start:\n" + seen)), 20000);
    const read = (c) => { seen += c; const m = seen.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); resolve(m[1]); } };
    child.stdout.on("data", read); child.stderr.on("data", read);
  });
  const port = new URL(ws).port;
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = new Page(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await page.open();
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { ...VIEW, mobile: false });
  page.close = () => child.kill("SIGKILL");
  process.on("exit", () => child.kill("SIGKILL"));
  return page;
}

export class Page {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.next = 1;
    this.pending = new Map();
    this.waiters = [];
    this.socket.onmessage = ({ data }) => {
      const msg = JSON.parse(data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
      } else if (msg.method) {
        this.waiters = this.waiters.filter((w) => !(w.method === msg.method && (w.resolve(msg.params), true)));
      }
    };
  }
  open() { return new Promise((resolve, reject) => { this.socket.onopen = resolve; this.socket.onerror = reject; }); }
  send(method, params = {}) {
    const id = this.next++;
    this.socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
  event(method, timeout = 20000) {
    return new Promise((resolve) => {
      const w = { method, resolve };
      this.waiters.push(w);
      setTimeout(() => { this.waiters = this.waiters.filter((x) => x !== w); resolve(null); }, timeout);
    });
  }
  async eval(expression) {
    const { result, exceptionDetails } = await this.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description || exceptionDetails.text);
    return result.value;
  }
  async waitFor(expression, what, timeout = 15000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      try { if (await this.eval(`Boolean(${expression})`)) return true; } catch { /* page mid-render */ }
      await sleep(200);
    }
    throw new Error(`timed out waiting for ${what}`);
  }
  async goto(url) {
    const loaded = this.event("Page.loadEventFired");
    await this.send("Page.navigate", { url });
    await loaded;
  }
  async setContent(html) {
    const { frameTree } = await this.send("Page.getFrameTree");
    const loaded = this.event("Page.loadEventFired", 5000);
    await this.send("Page.setDocumentContent", { frameId: frameTree.frame.id, html });
    await loaded;
  }
  async shot(path) {
    mkdirSync(dirname(path), { recursive: true });
    const { data } = await this.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(path, Buffer.from(data, "base64"));
    return path;
  }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const stamp = () => new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "");
