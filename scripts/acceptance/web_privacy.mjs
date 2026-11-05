async page => {
 const base=new URL(page.url()).origin; await page.goto(base+'/');await page.evaluate(()=>localStorage.removeItem('filemate-experience-notice-dismissed')); 
 await page.goto(base+'/login');const remember=page.getByRole('checkbox',{name:'在这台设备上保持登录 30 天'});
 if(await remember.isChecked())throw new Error('remember is enabled by default');
 await page.goto(base+'/import');await page.locator('.privacy-boundary strong').waitFor();
 if((await page.locator('.privacy-boundary strong').innerText()).length>30)throw new Error('privacy summary too long');
 await page.getByText('查看完整说明',{exact:true}).click();if(await page.locator('.privacy-boundary details').getAttribute('open')===null)throw new Error('details not opened');
 await page.getByRole('button',{name:'关闭体验提示',exact:true}).click();await page.reload();if(await page.locator('.experience-banner').count())throw new Error('dismiss not persisted');
 await page.route('**/api/privacy/boundary',route=>route.abort());await page.reload();await page.getByRole('button',{name:'重试读取说明'}).waitFor();
 if(!await page.getByRole('button',{name:'选择资料',exact:true}).isDisabled())throw new Error('upload not blocked');
 await page.unroute('**/api/privacy/boundary');await page.getByRole('button',{name:'重试读取说明'}).click();await page.waitForFunction(()=>!document.querySelector('.btn-primary')?.disabled);
 if(await page.getByRole('button',{name:'选择资料',exact:true}).isDisabled())throw new Error('retry not recovered');
 return {passed:true};
}


