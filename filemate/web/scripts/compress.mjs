import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { brotliCompressSync, gzipSync, constants } from 'node:zlib'
async function walk(dir){for(const entry of await readdir(dir,{withFileTypes:true})){const path=join(dir,entry.name);if(entry.isDirectory())await walk(path);else if(/\.(html|js|css|json|svg|xml|txt)$/.test(path)){const source=await readFile(path);if(source.length<512)continue;await writeFile(path+'.br',brotliCompressSync(source,{params:{[constants.BROTLI_PARAM_QUALITY]:9}}));await writeFile(path+'.gz',gzipSync(source,{level:9}))}}}
await walk('dist');console.log('Precompressed text assets: Brotli + gzip')
