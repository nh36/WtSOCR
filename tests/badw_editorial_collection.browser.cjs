/* Run against the opt-in full reader. Private scans are required only at build time. */
const {chromium} = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const base = process.env.BADW_READER_URL || 'http://127.0.0.1:8830';
  const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1050}}), errors=[];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base);
    await page.getByRole('link', {name:'Editorial Prefaces and Introductions',exact:true}).click();
    await page.waitForSelector('#documents a');
    assert.equal(await page.locator('#documents a').count(),8);
    const response = await page.request.get(base+'/editorial/collection.json');
    const collection = await response.json();
    assert.equal(collection.local_research_only,true);
    assert.equal(collection.distribution_authorised,false);
    const urls = new Set();
    for (const doc of collection.documents) {
      await page.locator(`[data-document="${doc.id}"]`).click();
      await page.waitForFunction(title => document.querySelector('#article h2')?.textContent===title,doc.title);
      assert.equal(await page.locator('#documents [aria-current="page"]').count(),1);
      assert.equal(await page.locator('.editorial-text').count(),doc.sections.length);
      assert((await page.locator('#article').innerText()).includes(doc.volume));
      for (const section of doc.sections) for (const view of section.views) {
        assert.match(view.url,/^pages\/[a-f0-9]{64}\.pdf$/);
        urls.add(view.url);
        const pdf=await page.request.get(base+'/editorial/'+view.url);
        assert.equal(pdf.status(),200); assert((await pdf.body()).subarray(0,5).equals(Buffer.from('%PDF-')));
      }
      if (doc.id==='delivery15-franke-memorial') assert((await page.locator('#article').innerText()).includes('Reviewed transcription'));
      else assert((await page.locator('#article').innerText()).includes('Unreviewed OCR'));
    }
    assert.equal(urls.size,32);
    await page.goBack();
    await page.waitForFunction(()=>document.querySelector('#documents [aria-current]')?.dataset.document==='band08-editorial');
    await page.goForward();
    await page.waitForFunction(()=>document.querySelector('#documents [aria-current]')?.dataset.document==='delivery15-franke-memorial');
    await page.locator('[data-document="delivery03-preface"]').click();
    await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent==='Vorwort zur dritten Lieferung');
    const popupPromise=page.waitForEvent('popup');
    await page.getByRole('link',{name:'Original printed page i',exact:true}).click();
    const popup=await popupPromise; await popup.waitForLoadState('domcontentloaded');
    assert.match(popup.url(),/\/editorial\/pages\/[a-f0-9]{64}\.pdf#page=1&view=Fit$/);
    await popup.close();
    const dir=process.env.BADW_SCREENSHOTS;
    if(dir){fs.mkdirSync(dir,{recursive:true});await page.screenshot({path:dir+'/editorial-desktop.png',fullPage:true});}
    for(const width of [320,390,768]){
      await page.setViewportSize({width,height:844});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      if(dir&&width===390)await page.screenshot({path:dir+'/editorial-mobile.png',fullPage:true});
    }
    await page.goto(base+'/editorial/#%');
    await page.waitForSelector('#article h2');
    assert.deepEqual(errors,[]);
    console.log('Editorial collection: eight documents, 32 facsimiles, history, source popup, desktop/mobile and malformed hash pass.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
