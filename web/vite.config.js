import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'

function fieldPrecache() {
  let output
  return {
    name: 'watsen-field-precache',
    apply: 'build',
    transformIndexHtml: { order: 'pre', handler: html => html.replace(/\r\n?/g, '\n') },
    configResolved(config) { output = resolve(config.root, config.build.outDir) },
    closeBundle() {
      const bundles = readdirSync(resolve(output, 'assets')).filter(file => /\.(js|css)$/.test(file)).map(file => `/assets/${file}`)
      const paths = ['/', '/index.html', '/manifest.webmanifest', '/assets/logo.png', '/assets/watsen-mark.svg', '/assets/field-camera.png', ...bundles]
      const source = readFileSync(resolve(output, 'sw.js'), 'utf8')
      const hash = createHash('sha256').update(source)
      for (const path of paths.filter(path => path !== '/')) hash.update(readFileSync(resolve(output, path.slice(1))))
      writeFileSync(resolve(output, 'sw.js'), source.replace('__WATSEN_BUILD__', hash.digest('hex').slice(0, 16)).replace(/const PRECACHE = \[[^\n]+\]/, `const PRECACHE = ${JSON.stringify(paths)}`))
    },
  }
}

export default defineConfig({
  plugins: [react(), fieldPrecache()],
  server: { port: 5173, host: true },
})
