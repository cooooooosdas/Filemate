import assert from 'node:assert/strict'
import test from 'node:test'
import { themes } from '../src/preferences/themes.ts'
const luminance = hex => { const v=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*v[0]+.7152*v[1]+.0722*v[2] }
const ratio = (a,b) => {const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)}
const pairs=[['text-primary','bg-surface',4.5],['text-secondary','bg-base',4.5],['text-muted','bg-base',4.5],['text-secondary','bg-surface',4.5],['text-muted','bg-elevated',4.5],['hero-copy','hero-background',4.5],['sidebar-secondary','sidebar-surface',4.5],['accent','bg-surface',4.5],['border-strong','bg-base',3],['border-strong','bg-surface',3]]
for(const theme of themes)test(`${theme.id}: ten text/control contrast pairs meet AA`,()=>{for(const [a,b,min] of pairs)assert.ok(ratio(theme.colors[a],theme.colors[b])>=min,`${a}/${b}: ${ratio(theme.colors[a],theme.colors[b]).toFixed(2)} < ${min}`)})
