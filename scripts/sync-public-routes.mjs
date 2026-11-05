import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = fs.readFileSync(path.join(root, 'filemate/web/src/router/index.ts'), 'utf8')
const routes = [...new Set([...source.matchAll(/path:\s*'([^']+)'/g)].map(row => row[1]))]
  .filter(route => !route.includes(':')).sort()
if (!routes.includes('/') || routes.some(route => !/^\/[a-z/-]*$/.test(route))) throw new Error('Unsupported route; review gateway matcher before publishing.')
const outputs = {
  'deploy/nginx.filemate.conf': '# BEGIN GENERATED SPA ROUTES\nmap $uri $filemate_spa_route {\n    default 0;\n' + routes.map(route => `    ${route} 1;`).join('\n') + '\n}\n# END GENERATED SPA ROUTES',
  'deploy/Caddyfile': '# BEGIN GENERATED SPA ROUTES\n\t@spa path ' + routes.join(' ') + '\n\t# END GENERATED SPA ROUTES',
}
for (const [relative, block] of Object.entries(outputs)) {
  const target = path.join(root, relative)
  const before = fs.readFileSync(target, 'utf8').replaceAll('\r\n', '\n')
  const after = before.replace(/# BEGIN GENERATED SPA ROUTES[\s\S]*?# END GENERATED SPA ROUTES/, block)
  if (!after.includes(block)) throw new Error(`Route markers missing: ${relative}`)
  if (process.argv.includes('--check')) {
    if (before !== after) throw new Error(`Routes changed: run node scripts/sync-public-routes.mjs (${relative})`)
  } else fs.writeFileSync(target, after)
}
console.log(`Public gateway routes synchronized: ${routes.length}`)
