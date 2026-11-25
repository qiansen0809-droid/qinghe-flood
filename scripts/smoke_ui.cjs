/* Browser acceptance check. Use an isolated running instance with the four demo events.
   npm install --no-save playwright && npx playwright install chromium
   QINGHE_URL controls the target. Browser and screenshot output paths are optional. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const base=process.env.QINGHE_URL||'http://127.0.0.1:8000';
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.QINGHE_BROWSER||undefined});
  try{
    const page=await browser.newPage({viewport:{width:1480,height:990},deviceScaleFactor:1});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    page.on('dialog',d=>d.accept());
    await page.goto(base);await page.getByText('服务在线',{exact:true}).waitFor();
    await page.locator('#event-choice').selectOption('event2');
    await page.locator('#ensemble').check();await page.locator('#correction').check();
    await page.getByRole('button',{name:'运行预报',exact:true}).click();
    await page.getByText('预报草稿已生成。',{exact:true}).waitFor();
    assert.equal(await page.locator('.figure svg polygon').count(),1);
    assert.equal(await page.locator('.figure svg circle').count(),40);
    await page.getByRole('button',{name:'签发产品',exact:true}).click();
    const bulletin=page.getByRole('link',{name:'下载签发公报'});await bulletin.waitFor();
    const url=await bulletin.getAttribute('href');
    const response=await page.request.get(base+url);assert.equal(response.status(),200); 
    await page.getByRole('button',{name:'验证回放',exact:true}).click();
    await page.getByText('快照重算结果一致',{exact:true}).waitFor();
    await page.getByRole('button',{name:'关闭',exact:true}).click();
    if(process.env.QINGHE_SCREENSHOT){
      const out=path.resolve(process.env.QINGHE_SCREENSHOT);fs.mkdirSync(path.dirname(out),{recursive:true});
      await page.screenshot({path:out});
    }
    await page.getByRole('button',{name:'数据与质控',exact:true}).click();
    await page.getByRole('button',{name:'查看质控'}).first().click();
    await page.getByText('该场次通过质控。').waitFor();await page.getByRole('button',{name:'关闭',exact:true}).click();
    // Upload a distinct QC sample to this test database.
    const stamp=String(Date.now()),eventId='ui-qc-'+stamp;
    await page.getByRole('button',{name:'导入 CSV'}).click();
    await page.locator('#import-event').fill(eventId);
    const sample=fs.readFileSync(path.join(__dirname,'..','data','events','event2.csv'),'utf8').replace('0.825,8.2','0.825,-999');
    await page.locator('#csv-file').setInputFiles({name:'ui.csv',mimeType:'text/csv',buffer:Buffer.from(sample)});
    for(const [key,value] of Object.entries({WU:20,WL:24.3,WD:0,S:25,QS:.5,QI:3,QG:6})){
      await page.locator('#state-'+key).fill(String(value));
    }
    await page.getByRole('button',{name:'提交质控入库'}).click();
    await page.getByRole('heading',{name:'入库质控结果'}).waitFor();
    await page.getByRole('cell',{name:'缺测',exact:true}).waitFor();
    await page.getByRole('button',{name:'关闭',exact:true}).click();
    await page.getByRole('button',{name:'参数方案',exact:true}).click();
    await page.getByRole('button',{name:'参数',exact:true}).first().click();
    await page.getByRole('cell',{name:'WUM',exact:true}).waitFor();
    await page.getByRole('button',{name:'关闭',exact:true}).click();
    const planName='UI验收-'+stamp;
    await page.getByRole('button',{name:'新建方案',exact:true}).click();
    await page.locator('#plan-name').fill(planName);
    await page.getByRole('button',{name:'保存参数版本',exact:true}).click();
    const rowV1=page.getByRole('row').filter({hasText:planName}).filter({hasText:'v1'});
    await rowV1.getByRole('button',{name:'切换'}).click();
    await rowV1.getByText('当前',{exact:true}).waitFor();
    await rowV1.getByRole('button',{name:'新版本'}).click();
    await page.locator('[data-param="K"]').fill('0.79');
    await page.getByRole('button',{name:'保存参数版本',exact:true}).click();
    const rowV2=page.getByRole('row').filter({hasText:planName}).filter({hasText:'v2'});
    await rowV2.getByRole('button',{name:'删除'}).click();
    await rowV2.waitFor({state:'detached'});
    const baseline=page.getByRole('row').filter({hasText:'一期率定参数'}).first();
    await baseline.getByRole('button',{name:'切换'}).click();
    await baseline.getByText('当前',{exact:true}).waitFor();
    await page.getByRole('button',{name:'定时起报',exact:true}).click();
    await page.locator('#interval').fill('7200');
    await page.getByRole('button',{name:'创建定时任务'}).click();
    await page.getByText('定时起报已创建。').waitFor();
    await page.getByRole('button',{name:'停用',exact:true}).first().click();
    await page.getByText('定时任务已停用。').waitFor();
    await page.getByRole('button',{name:/预警通知/}).click();
    await page.getByRole('heading',{name:'站内预警消息'}).waitFor();
    const trigger=await page.request.post(base+'/api/runs',{data:{event_id:'event2',actor:'ui-async-check'}});
    assert.equal(trigger.ok(),true);
    const remoteRun=await trigger.json();
    const alertRow=page.getByRole('row').filter({has:page.getByRole('button',{name:String(remoteRun.id),exact:true})});
    await alertRow.getByRole('button',{name:'标为已读'}).click({timeout:15000});
    await alertRow.getByText('已读',{exact:true}).waitFor();
    await page.getByRole('button',{name:'操作记录',exact:true}).click();
    await page.getByRole('button',{name:'查看',exact:true}).first().click();
    await page.getByRole('heading',{name:'操作明细'}).waitFor();
    assert.deepEqual(errors,[]);console.log('PASS: forecast, observations, ensemble band, issue, download, replay, CSV import + QC, plan versions/create/switch/archive, schedule create/stop, asynchronous alert/read, audit.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

