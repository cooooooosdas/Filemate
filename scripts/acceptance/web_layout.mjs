// Playwright CLI callback: check real Home geometry after a production build.
async page => {
 const base=new URL(page.url()).origin,reports=[];
 for(const [width,height] of [[1440,900],[1366,768],[1920,1080],[390,844],[375,667],[320,844]]) {
  await page.setViewportSize({width,height});await page.goto(base+'/');await page.locator('.home-action[aria-busy="false"]').waitFor();await page.waitForTimeout(2700);
  const row=await page.evaluate(()=>{const box=s=>document.querySelector(s)?.getBoundingClientRect().toJSON();return {overflow:document.documentElement.scrollWidth>innerWidth,hero:box('.welcome'),first_card:box('.task-entry'),action:box('.home-action'),cta:box('.home-action-row .solid-link'),workspace:box('.route-surface'),sidebar:box('.sidebar'),nav_rows:[...document.querySelectorAll('.nav-item')].map(n=>n.getBoundingClientRect().height),header_controls:[...document.querySelectorAll('.topbar a,.topbar button')].filter(n=>n.checkVisibility()).map(n=>({label:n.getAttribute('aria-label'),width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height}))}});
  reports.push({width,height,...row});
 }
 const passed=reports.every(r=>!r.overflow&&(r.width>900?r.workspace.width<=1440&&r.nav_rows.every(h=>h>=36&&h<=38):true)&&(r.width===390?r.hero.height<=420&&r.first_card.bottom<=844&&r.first_card.top-r.cta.bottom<=24.1:true)&&(r.width===375?r.hero.height<=360:true)&&r.header_controls.every(b=>b.width>=44&&b.height>=44));
 const result={reports,passed};if(!passed)throw new Error(JSON.stringify(result));return result;
}
