// Page navigation tests do not establish lexical identity.
const {launchTestBrowser}=require('./badw_browser_process.cjs');
const {chromium}=require('playwright-core');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
(async()=>{
 const base=process.env.BADW_READER_URL||'http://127.0.0.1:8806';
 const {browser,closeBrowser}=await launchTestBrowser(chromium,{executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const get=async path=>{const r=await page.request.get(base+'/'+path);assert(r.ok());return r.json();};
 const catalog=(await get('data.json')).entries, dataset=await get('provisional_print_links.json');
 const certified=await get('print_facsimiles.json');
 assert.equal(certified.witnesses.length,691);assert.equal(Object.keys(certified.pages).length,89);
 const certURLs=new Set(certified.witnesses.map(r=>r.source_url));
 const pages=new Map();let checked=0;
 for(const row of dataset.witnesses){
  assert(!certURLs.has(row.source_url));
  const meta=catalog.find(e=>e.source_kind==='html'&&e.headword.loc===row.headword&&String(e.homonym)===String(row.homonym));assert(meta);
  const body=await get(meta.path);assert.equal(body.source_url,row.source_url);
  assert.equal(body.sources.filter(s=>s.suggested_print_provenance).length,1);
  assert(!body.sources.some(s=>s.print_provenance));
  const source=body.sources.find(s=>s.suggested_print_provenance),p=source.suggested_print_provenance;
  assert.equal(p.physical_page,dataset.pages[row.page].physical_page);
  assert.equal(p.source_sha256,dataset.pages[row.page].source_sha256);
  assert.equal(p.printed_folio,null);assert.equal(p.side,null);
  pages.set(row.page,{body,source});checked++;
 }
 for(const {body,source} of pages.values()){
  await page.goto(base+'/#'+encodeURIComponent(body.id));
  await page.waitForFunction(id=>document.querySelector('#entries [aria-current]')?.hash==='#'+encodeURIComponent(id)&&document.querySelector('.suggested-print'),body.id);
  const link=page.locator('#article .suggested-print');assert(await link.isVisible());
  assert((await link.textContent()).includes('automatically matched, not yet verified'));
  const r=await page.request.get(base+'/'+source.url.split('#')[0]);assert(r.ok());
  const bytes=await r.body();assert.equal(bytes.subarray(0,5).toString(),'%PDF-');
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),source.sha256);
 }
 const {body,source}=pages.values().next().value;
 const toggle=page.getByRole('checkbox',{name:'Show suggested print links'});
 await toggle.uncheck();assert(!(await page.locator('.suggested-print').isVisible()));
 await page.reload();await page.waitForSelector('.suggested-print',{state:'attached'});
 assert(!(await page.locator('.suggested-print').isVisible()));
 await page.getByRole('checkbox',{name:'Show suggested print links'}).check();
 await page.goto(base+'/#'+encodeURIComponent(body.id));
 await page.waitForFunction(id=>document.querySelector('#entries [aria-current]')?.hash==='#'+encodeURIComponent(id)&&document.querySelector('.suggested-print'),body.id);
 const [popup]=await Promise.all([page.waitForEvent('popup'),page.locator('.suggested-print').click()]);
 await popup.waitForLoadState();assert(popup.url().endsWith(source.url));await popup.close();
 assert.equal(page.url(),base+'/#'+encodeURIComponent(body.id));
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({provisional:checked,physical_scans:pages.size,certified:691,pdf_checks:true,hide_resume_return:true}));
 }finally{await closeBrowser();}
})().catch(e=>{console.error(e);process.exit(1);});
