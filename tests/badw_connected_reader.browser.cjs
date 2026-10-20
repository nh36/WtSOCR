/* Run against a freshly built, locally served connected preview. See reader README. */
const {chromium}=require('playwright-core');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const base=process.env.BADW_READER_URL||'http://127.0.0.1:8765';
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const data=await (await page.request.get(base+'/data.json')).json();
 const entries=new Map(data.entries.map(e=>[e.id,e]));
 assert.equal(data.preview.reviewed_occurrences,23);
 const url=id=>base+'/#'+encodeURIComponent(id);
 async function go(e){await page.goto(url(e.id));await page.waitForFunction(()=>document.querySelector('#selection-status').textContent.startsWith('Selected:'));assert.equal(await page.locator('#entries [aria-current]').count(),1);}
 let journeys=0,uncertain=0,citations=0,unresolvedCitations=0;
 const visitedSources=new Set();
 for(const entry of data.entries){
  await go(entry);
  assert((await page.locator('#article h2').textContent()).includes(entry.headword.loc));
  for(const s of entry.sources){
   assert.equal(await page.locator('#article > .source-access a').filter({hasText:s.label}).count(),1);
   if(s.url.startsWith('sources/')&&!visitedSources.has(s.url)){
    const response=await page.request.get(base+'/'+s.url);assert.equal(response.status(),200);
    assert.equal(require('node:crypto').createHash('sha256').update(await response.body()).digest('hex'),s.sha256);visitedSources.add(s.url);
   }
  }
  for(const ref of entry.cross_references){
   for(const member of ref.target_members||[]){
    if(member.resolution_status==='resolved'){
     assert(entries.has(member.target_entry_id));
     // Exact href distinguishes repeated wording/homonyms.
     const href='#'+encodeURIComponent(member.target_entry_id);
     const actual=page.locator('.reading a').filter({hasText:member.literal});
     const chosen=await actual.evaluateAll((nodes,h)=>nodes.findIndex(n=>n.getAttribute('href')===h),href);
     assert(chosen>=0);await actual.nth(chosen).click();
     await page.waitForFunction(id=>decodeURIComponent(location.hash.slice(1))===id,member.target_entry_id);
     await page.waitForFunction(label=>document.querySelector('#article h2').textContent.includes(label),entries.get(member.target_entry_id).headword.loc);
     await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2').textContent.includes(label),entry.headword.loc);
     await page.goForward();await page.waitForFunction(id=>decodeURIComponent(location.hash.slice(1))===id,member.target_entry_id);
     await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2').textContent.includes(label),entry.headword.loc);journeys++;
    }else{
     const button=page.locator('.reading .uncertain-reference').filter({hasText:member.literal}).first();
     await button.click();assert(await page.locator('#reference-detail').isVisible());
     assert((await page.locator('#reference-detail-content').textContent()).includes('no destination'));
     await page.keyboard.press('Escape');assert(!(await page.locator('#reference-detail').isVisible()));assert(await button.evaluate(n=>n===document.activeElement));uncertain++;
    }
   }
  }
  if(entry.citations.length){
   const button=page.locator('.citation').first();await button.focus();await page.keyboard.press('Enter');
   assert(await page.locator('#citation-detail').isVisible());
   assert((await page.locator('#citation-detail-content').textContent()).includes('Passage ownership:'));
   assert(await page.locator('#citation-detail .source-access a').count()>0);
   await page.keyboard.press('Escape');assert(await button.evaluate(n=>n===document.activeElement));citations++;
  }
 }
 for(const entry of data.entries){
  const unresolved=entry.citations.filter(c=>c.bibliography_status==='unresolved');
  if(!unresolved.length)continue;await go(entry);
  for(const citation of unresolved){
   const index=await page.locator('.citation').evaluateAll((nodes,text)=>nodes.findIndex(n=>n.textContent.replace(/\s+/g,' ')===text.replace(/\s+/g,' ')),citation.source_form);
   assert(index>=0,'unresolved citation must remain available');
   await page.locator('.citation').nth(index).click();
   assert((await page.locator('#citation-detail-content').textContent()).includes('Identity status: unresolved'));
   await page.keyboard.press('Escape');unresolvedCitations++;
  }
 }
 const facsimileEntry=data.entries.find(e=>e.sources.some(s=>s.url.startsWith('sources/')));await go(facsimileEntry);
 const sourceURL=await page.locator('#article > .source-access a').first().getAttribute('href');
 const [sourcePage,sourceResponse]=await Promise.all([page.waitForEvent('popup'),page.context().waitForEvent('response',{predicate:r=>r.url()===base+'/'+sourceURL}),page.locator('#article > .source-access a').first().click()]);
 assert.equal(sourceResponse.status(),200);assert(sourceResponse.headers()['content-type'].includes('application/pdf'));await sourcePage.close();
 assert(journeys>=47);assert(uncertain>=3);assert.equal(unresolvedCitations,3);
 await go(data.entries[1]);
 const next=await page.locator('[rel=next]').getAttribute('href');await page.locator('[rel=next]').click();assert.equal(decodeURIComponent(next.slice(1)),data.entries[2].id);
 await page.locator('[rel=prev]').click();await page.waitForFunction(id=>decodeURIComponent(location.hash.slice(1))===id,data.entries[1].id);
 const hash=await page.evaluate(()=>location.hash);await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>location.hash),hash);
 await page.locator('#search').fill('impossible headword');assert((await page.locator('#entries').textContent()).includes('No matching'));
 await page.locator('#search').fill('');await page.locator('#search').focus();await page.keyboard.press('ArrowDown');assert(await page.locator('#entries a').first().evaluate(n=>n===document.activeElement));await page.keyboard.press('End');assert(await page.locator('#entries a').last().evaluate(n=>n===document.activeElement));await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await page.waitForFunction(id=>decodeURIComponent(location.hash.slice(1))===id,data.entries[1].id);
 const interesting=data.entries.find(e=>e.headword.loc==='ṅar');await go(interesting);
 const glyph=page.locator('button.unknown-glyph').first();
 if(await glyph.count()){await glyph.click();assert((await page.locator('#reference-detail-content').textContent()).includes('No reading has been supplied'));await page.keyboard.press('Escape');assert(await glyph.evaluate(n=>n===document.activeElement));}
 await page.evaluate(async()=>{await document.fonts.ready;document.activeElement.blur();});
 assert(await page.evaluate(()=>document.fonts.check('32px "WTS Tibetan"')));
 const out=process.env.BADW_SCREENSHOTS||'work/badw_connected_reader_20261020/screenshots';fs.mkdirSync(out,{recursive:true});
 await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
 for(const width of [320,390,768]){
  await page.setViewportSize({width,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`horizontal overflow ${width}`);
  await page.locator('#article').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,`reader-${width}.png`),fullPage:true});
  const citation=page.locator('.citation').first();await citation.click();assert(await page.locator('#citation-detail').isVisible());await page.keyboard.press('Escape');
 }
 await page.goto(base+'/#%ZZ');await page.waitForSelector('#article h2');assert.equal(await page.locator('#article h2').textContent(),'Entry unavailable');
 assert.deepEqual(errors,[]);console.log(JSON.stringify({entries:entries.size,member_journeys:journeys,unresolved_dialogs:uncertain,citation_journeys:citations,unresolved_citation_dialogs:unresolvedCitations,verified_facsimiles:visitedSources.size,viewports:[1440,320,390,768],browser_errors:errors.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
