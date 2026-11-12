// Render one PNG per narration segment for each lesson.
// node render.mjs <lessonDir> <buildDir> L1 L2 ...   (lessonDir holds the normalized lesson JSON that build.py writes)
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { launch } from "./cdp.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const [contentDir, buildDir, ...ids] = process.argv.slice(2);
process.env.CHROME_OFFLINE = "1";
const page = await launch();
await page.goto(pathToFileURL(join(here, "frame.html")).href);
// The academy's colours ("theme" in academy.json), so the video matches the site.
const theme = JSON.parse(process.env.ACADEMY_THEME || "{}");
for (const [k, val] of Object.entries(theme)) if (typeof val === "string") await page.eval(`document.documentElement.style.setProperty(${JSON.stringify("--" + k)}, ${JSON.stringify(val)}), true`);
// An academy may bring its own font (academy.json "font"). It is loaded from the academy's folder, never kept in the kit.
const fontFile = process.env.ACADEMY_FONT_FILE, fontFamily = process.env.ACADEMY_FONT_FAMILY || "AcademyFont";
if (fontFile && existsSync(fontFile)) {
  const data = readFileSync(fontFile).toString("base64");
  await page.eval(`(async () => { const f = new FontFace(${JSON.stringify(fontFamily)}, "url(data:font/woff2;base64,${data})"); await f.load(); document.fonts.add(f);
    document.documentElement.style.setProperty("--font", ${JSON.stringify(`"${fontFamily}", `)} + getComputedStyle(document.documentElement).getPropertyValue("--font")); return true; })()`);
}
await page.waitFor("document.fonts.status === 'loaded'", "fonts");
for (const id of ids) {
  const lesson = JSON.parse(readFileSync(join(contentDir, `${id}.json`), "utf8"));
  let n = 0;
  for (const [si, sc] of lesson.video.scenes.entries()) {
    for (const gi of sc.segments.keys()) {
      const out = join(buildDir, id, "frames", `s${String(si).padStart(2, "0")}_g${String(gi).padStart(2, "0")}.png`);
      await page.eval(`renderFrame(${JSON.stringify(lesson)}, ${si}, ${gi})`);
      await page.eval("document.fonts.ready.then(() => true)");
      await page.shot(out);
      n++;
    }
  }
  console.log(`${id}: ${n} frames`);
}
page.close();
process.exit(0);
