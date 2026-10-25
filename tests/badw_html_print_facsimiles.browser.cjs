/* Real-source milestone check: editorial sources, exact single-page PDFs,
 * unconfirmed homonyms and unchanged PDF witnesses, at desktop/mobile widths. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {chromium}=require('playwright-core');
(async()=>{
 const base=process.env.BADW_READER_URL||'http://127.0.0.1:8806';
 const screenshots=process.env.BADW_SCREENSHOTS||'work/html-print-browser';fs.mkdirSync(screenshots,{recursive:true});
 const reviewed=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/badw_html_print_pages.json')));
 const generated=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/badw_html_print_alignment.generated.json')));
 reviewed.witnesses.push(...generated.witnesses);Object.assign(reviewed.pages,generated.pages);
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:process.env.BADW_HEADED!=='1'});
 const errors=[];const report={};
 try{
 const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
 const catalog=(await (await page.request.get(base+'/data.json')).json()).entries;
 const printed=await (await page.request.get(base+'/print_facsimiles.json')).json();
 assert.equal(catalog.length,29878);assert.equal(printed.witnesses.length,reviewed.witnesses.length);assert.equal(Object.keys(printed.pages).length,Object.keys(reviewed.pages).length);
 const bodies=[];
 for(const meta of catalog.filter(e=>reviewed.witnesses.some(r=>r.headword===e.headword.loc&&String(r.homonym)===String(e.homonym)))){
  const response=await page.request.get(base+'/'+meta.path);assert(response.ok());const body=await response.json();
  if(reviewed.witnesses.some(r=>r.source_url===body.source_url))bodies.push({...body,path:meta.path});
 }
 assert.equal(bodies.length,reviewed.witnesses.length);
 assert(!JSON.stringify(printed).includes('originals/'));
 for(const body of bodies){
  const provenance=body.sources[1].print_provenance;
  const reviewedWitness=reviewed.witnesses.find(r=>r.source_url===body.source_url);
  assert.equal(provenance.printed_heading,reviewedWitness.printed_heading);
  assert.deepEqual(provenance.evidence,reviewedWitness.evidence);
  if(provenance.evidence.certificate){
   const observation=provenance.evidence.certificate.print_observation;
   assert.equal(observation.verification,'visual transcription; not machine-verified');
   assert.equal(observation.heading,provenance.printed_heading);
   assert.equal(observation.heading_anchor,observation.evidence_anchor);
  }
  assert(!('original_url' in provenance));
  assert(!/file:|\/Users\/|\/private\//.test(JSON.stringify(body)));
  assert.equal((await page.request.get(base+'/sources/originals/'+provenance.source_sha256+'.pdf')).status(),404);
 }
 const go=async body=>{await page.goto(base+'/#'+encodeURIComponent(body.id));await page.waitForFunction(id=>document.querySelector('#entries [aria-current]')?.hash==='#'+encodeURIComponent(id)&&document.querySelector('#article > .source-access a'),body.id);};
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:1050});
  for(const body of bodies){
   await go(body);
   assert.equal(await page.getByText('Complete original scan',{exact:true}).count(),0);
   const links=page.locator('#article > .source-access a');assert.equal(await links.count(),2);
   assert.equal(await links.nth(0).textContent(),'BAdW editorial text');assert.equal(await links.nth(0).getAttribute('href'),body.source_url);
   const source=body.sources[1];assert((await links.nth(1).textContent()).startsWith('Original printed edition'));
   assert.equal(await links.nth(1).getAttribute('href'),source.url);assert(source.url.endsWith('#page=1&view=Fit'));
   const response=await page.request.get(base+'/'+source.url.split('#')[0]);assert.equal(response.status(),200);
   const bytes=await response.body();assert(bytes.subarray(0,5).toString()==='%PDF-');
   assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),source.sha256);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   if(body.headword.loc==='ba'&&String(body.homonym)==='1')await page.screenshot({path:path.join(screenshots,`ba1-${width}.png`),fullPage:true});
   if(body.headword.loc==='ba tshwa'){
    assert.equal(provenanceAnchor(body),'wts_8_b:17:63');
    await page.screenshot({path:path.join(screenshots,`ba-tshwa-${width}.png`),fullPage:true});
   }
  }
 }
 // A continuation-page running header must not turn ma4 into an exact link.
 const ma4=catalog.find(e=>e.source_kind==='html'&&e.headword.loc==='ma'&&String(e.homonym)==='4');assert(ma4);
 await go(ma4);assert.equal(await page.locator('#article > .source-access a').count(),1);
 assert.equal(await page.locator('#article > .source-access a').textContent(),'BAdW editorial text');
 // Correct printed pages do not justify retaining running-header identities.
 // Both actual article starts lack C6 anchors and remain explicitly deferred.
 for(const heading of ['da yaṅ','mdun']){
  const meta=catalog.find(e=>e.source_kind==='html'&&e.headword.loc===heading&&String(e.homonym)==='1');assert(meta);
  await go(meta);
  assert.equal(await page.locator('#article > .source-access a').count(),1);
  assert.equal(await page.locator('#article > .source-access a').textContent(),'BAdW editorial text');
 }
 const gyur=catalog.find(e=>e.source_kind==='pdf'&&e.headword.loc==='’gyur'&&String(e.homonym)==='1');assert(gyur);
 const pdfBody=await (await page.request.get(base+'/'+gyur.path)).json();assert(!pdfBody.sources.some(s=>s.print_provenance));
 await go(gyur);assert.equal(await page.locator('#article > .source-access a').count(),pdfBody.sources.length);
 assert.equal(await page.locator('#article > .source-access a').first().textContent(),'Printed facsimile');
 assert.deepEqual(await page.locator('#article > .source-access a').evaluateAll(links=>links.map(a=>a.getAttribute('href'))),pdfBody.sources.map(s=>s.url));
 // Actually follow primary links into ordinary Chrome's PDF viewer. It must
 // receive a single-page derivative rather than the complete source spread.
 const seen=new Set();
 for(const body of bodies){
  const source=body.sources[1];if(seen.has(source.url))continue;seen.add(source.url);
  await page.setViewportSize({width:1440,height:1050});await go(body);
  const [popup]=await Promise.all([page.waitForEvent('popup'),page.locator('#article > .source-access a').nth(1).click()]);
  await popup.waitForLoadState();assert(popup.url().endsWith(source.url));
  await popup.waitForTimeout(800);
  await popup.screenshot({path:path.join(screenshots,'printed-'+source.print_provenance.volume+'-'+source.print_provenance.printed_page+'.png')});
  await popup.close();
 }
 // Compare original-print and existing born-digital single-page presentation
 // on mobile too; the ordinary PDF viewer supplies zoom without a new UI.
 const mobileSources=[bodies.find(b=>b.sources[1].print_provenance.side==='left').sources[1],bodies.find(b=>b.headword.loc==='ba'&&String(b.homonym)==='1').sources[1],pdfBody.sources[0]];
 await page.setViewportSize({width:390,height:844});
 for(const [index,source] of mobileSources.entries()){
  const viewer=await browser.newPage({viewport:{width:390,height:844}});
  await viewer.goto(base+'/'+source.url);await viewer.waitForTimeout(1000);
  await viewer.screenshot({path:path.join(screenshots,`mobile-pdf-${index}.png`)});await viewer.close();
 }
 assert.deepEqual(errors,[]);report.mobilePDFComparisons=mobileSources.length;report.reviewedWitnesses=bodies.length;report.openedSinglePagePDFs=seen.size;report.widths=[1440,390];report.browserErrors=errors;
 console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

function provenanceAnchor(body){return body.sources[1].print_provenance.evidence.certificate.anchor;}
