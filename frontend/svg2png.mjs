import { chromium } from 'playwright'
import { readFileSync } from 'node:fs'

const input = process.argv[2]
const output = process.argv[3]
let svg = readFileSync(input, 'utf8')

// Pull intrinsic size from the <svg> viewBox so we can size the page to it.
const vb = (svg.match(/viewBox="([\d.\s]+)"/) || [])[1] || '0 0 900 700'
const [, , vw, vh] = vb.trim().split(/\s+/).map(Number)
const w = Math.ceil(vw)
const h = Math.ceil(vh)
// Ensure the root <svg> fills our sized page.
svg = svg.replace('<svg ', `<svg width="${w}" height="${h}" `)

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2 })
const page = await ctx.newPage()
await page.setContent(
  `<!doctype html><html><body style="margin:0;padding:0;background:#0a0e1a">${svg}</body></html>`,
  { waitUntil: 'networkidle' }
)
await page.waitForTimeout(300)
await page.screenshot({ path: output, clip: { x: 0, y: 0, width: w, height: h } })
await browser.close()
console.log('wrote', output, `${w}x${h}`)
