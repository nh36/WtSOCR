/* Run against a freshly built, locally served full reader; the 83-witness fixture supplies fixed journeys. See reader README. */
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
 const catalog=data.entries;assert.equal(catalog.length,29877);assert.equal(data.sharded,true);
 const fixture=JSON.parse(fs.readFileSync(process.env.BADW_READER_FIXTURE||'work/badw_connected_reader_20261020/run8/reader/data.json'));
 const entries=new Map(catalog.map(e=>[e.id,e]));
 data.entries=[];for(const e of fixture.entries){const meta=entries.get(e.id);assert(meta);const response=await page.request.get(base+'/'+meta.path);assert.equal(response.status(),200);data.entries.push(await response.json());}
 assert.equal(data.preview.reviewed_occurrences,23);
 const url=id=>base+'/#'+encodeURIComponent(id);
 const requests=[];page.on('request',r=>requests.push(r.url()));
 const started=Date.now();await page.goto(url(catalog[0].id));
 await page.waitForFunction(()=>document.querySelector('#selection-status').textContent.startsWith('Selected:'));
 const initialMilliseconds=Date.now()-started;
 assert.equal(requests.filter(u=>u.includes('/entries/')).length,1,'initial load fetches one entry body');
 assert.equal(requests.filter(u=>u.endsWith('/data.json')).length,1);
 assert(initialMilliseconds<15000,`local initial load took ${initialMilliseconds} ms`);
 requests.length=0;await page.locator('#search').fill('mkhar');await page.locator('#search').fill('');
 assert.equal(requests.filter(u=>u.includes('/entries/')).length,0,'search needs no entry bodies');
 async function go(e){await page.goto(url(e.id));await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),e.headword.loc);await page.waitForFunction(()=>document.querySelector('#selection-status').textContent.startsWith('Selected:'));assert.equal(await page.locator('#entries [aria-current]').count(),1);}
 let journeys=0,uncertain=0,citations=0,unresolvedCitations=0;
 const visitedSources=new Set();
 for(const entry of data.entries){
  await go(entry);
  assert((await page.locator('#article h2').textContent()).includes(entry.headword.loc));
  for(const s of entry.sources){
   assert(await page.locator('#article > .source-access a').evaluateAll((links,url)=>links.some(a=>a.getAttribute('href')===url),s.url));
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
     await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(member.target_entry_id).headword.loc);
     await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);
     await page.goForward();await page.waitForFunction(id=>decodeURIComponent(location.hash.slice(1))===id,member.target_entry_id);
     await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);journeys++;
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
 // Actual unresolved bibliography identities in the current full corpus; the
 // current apparatus resolves the former preview's unresolved examples.
 for(const id of ['badw:entry:b02929dd7cac236341035182a2156e52083e149569e05a4526464d99a36cff62','badw:entry:2e1d21ca0ef668f56b2df58656c2433e124595e2c90485d45c4b04c92a20cd89','badw:pdf:badw-v3-ada4e0c7f95483b5511f159d715f24d5d1cac8a74143c1256d5b3f8ea7462b70:489']){
  const meta=entries.get(id);assert(meta);data.entries.push(await (await page.request.get(base+'/'+meta.path)).json());
 }
 for(const entry of data.entries){
  const unresolved=entry.citations.filter(c=>c.bibliography_status==='unresolved');
  if(!unresolved.length)continue;await go(entry);
  for(const citation of unresolved){
   const segment=entry.display_blocks.flatMap(b=>b.segments).find(s=>s.component_ids.includes(citation.component_id));
   assert(segment,'citation retains a displayed source span');
   const index=await page.locator('.citation').evaluateAll((nodes,text)=>nodes.findIndex(n=>n.textContent.replace(/\s+/g,' ')===text.replace(/\s+/g,' ')),segment.text);
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
 assert(journeys>=47);assert(uncertain>=3);assert(unresolvedCitations>=3);
 await go(catalog[1]);
 const next=await page.locator('[rel=next]').getAttribute('href');await page.locator('[rel=next]').click();assert.equal(decodeURIComponent(next.slice(1)),catalog[2].id);
 await page.locator('[rel=prev]').click();await page.waitForFunction(id=>decodeURIComponent(location.hash.slice(1))===id,catalog[1].id);
 assert.equal(await page.locator('#entries a').count(),100);
 const hash=await page.evaluate(()=>location.hash);await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>location.hash),hash);
 await page.locator('#search').fill('impossible headword');assert((await page.locator('#entries').textContent()).includes('No matching'));
 await page.locator('#search').fill('');await page.locator('#search').focus();await page.keyboard.press('ArrowDown');assert(await page.locator('#entries a').first().evaluate(n=>n===document.activeElement));await page.keyboard.press('End');assert(await page.locator('#entries a').last().evaluate(n=>n===document.activeElement));await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await page.waitForFunction(id=>decodeURIComponent(location.hash.slice(1))===id,catalog[1].id);
 await go(catalog[0]);await page.locator('.entry-pager button').filter({hasText:'Next results'}).click();assert.equal(await page.locator('#entries a').first().getAttribute('href'),'#'+encodeURIComponent(catalog[100].id));
 // Search all catalog fields without loading entry bodies.
 for(const [field,query] of [['loc','mkhar ’gro'],['tibetan','ངར']]){
  const expected=catalog.filter(e=>(e.headword[field]||'').includes(query));assert(expected.length);
  await page.locator('#search').fill(query);assert(await page.locator('#entries a').count()>0);
 }
 const aliasEntry=catalog.find(e=>e.search_aliases?.some(a=>a.length>3));assert(aliasEntry);
 await page.locator('#search').fill(aliasEntry.search_aliases.find(a=>a.length>3));assert(await page.locator('#entries a').count()>0);
 await page.locator('#search').fill('');
 // Script switching is a display operation: IDs, links, sources and history
 // remain fixed, and every derived form has independent paired evidence.
 let scriptModes=0;
 if(data.preview.loc_experiment){
  let specimen;
  for(const meta of catalog.filter(e=>e.headword.loc==='ka')){
   const entry=await (await page.request.get(base+'/'+meta.path)).json();
   if(entry.derived_headword){specimen=entry;break;}
  }
  assert(specimen,'an independently corroborated headword is available');
  await go(specimen);
  const originalHash=await page.evaluate(()=>location.hash);
  const sourceLinks=await page.locator('#article > .source-access a').evaluateAll(ns=>ns.map(n=>n.href));
  for(const mode of ['loc','tibetan','both']){
   await page.locator('#script-mode').selectOption(mode);
   assert.equal(await page.evaluate(()=>location.hash),originalHash);
   assert.deepEqual(await page.locator('#article > .source-access a').evaluateAll(ns=>ns.map(n=>n.href)),sourceLinks);
   assert((await page.locator('#article h2').textContent()).includes(mode==='tibetan'?specimen.derived_headword.tibetan:specimen.headword.loc));
   assert((await page.locator('.loc-note').textContent()).includes('Source headword: '+specimen.headword.loc));
   scriptModes++;
  }
 }
 // Lexically established references retain an explicit choice of source witnesses.
 const multi=entries.get('badw:pdf:badw-v4-aa5f071493754b5a6b49af059dd9780a463b355e0ca13a25e0ec17e1c4f2d5fa:504');
 await go(multi);await page.locator('.uncertain-reference').filter({hasText:'thams cad'}).first().click();
 const choices=page.locator('#reference-detail-content a[href^="#"]');assert.equal(await choices.count(),2);
 const destination=await choices.first().getAttribute('href');await choices.first().click();await page.waitForFunction(h=>location.hash===h,destination);
 await page.waitForFunction(()=>!document.querySelector('#reference-detail').open);await page.goBack();
 const interesting=data.entries.find(e=>e.headword.loc==='ṅar');await go(interesting);
 const glyph=page.locator('button.unknown-glyph').first();
 if(await glyph.count()){await glyph.click();assert((await page.locator('#reference-detail-content').textContent()).includes('No reading has been supplied'));await page.keyboard.press('Escape');assert(await glyph.evaluate(n=>n===document.activeElement));}
 await page.evaluate(async()=>{await document.fonts.ready;document.activeElement.blur();});
 assert(await page.evaluate(()=>document.fonts.check('32px "WTS Tibetan"')));
 const out=process.env.BADW_SCREENSHOTS||'work/badw_full_reader_20261020/screenshots';fs.mkdirSync(out,{recursive:true});
 await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
 for(const width of [320,390,768]){
  await page.setViewportSize({width,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`horizontal overflow ${width}`);
  await page.locator('#article').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,`reader-${width}.png`),fullPage:true});
  const citation=page.locator('.citation').first();await citation.click();assert(await page.locator('#citation-detail').isVisible());await page.keyboard.press('Escape');
 }
 // A corrupted entry must fail visibly rather than display unverified content.
 const victim=catalog[500];await page.route('**/'+victim.path,route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
 await page.goto(url(victim.id));await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent==='Entry could not be loaded');assert((await page.locator('#article').textContent()).includes('integrity check failed'));await page.unroute('**/'+victim.path);
 await page.goto(base+'/#%ZZ');await page.waitForSelector('#article h2');assert.equal(await page.locator('#article h2').textContent(),'Entry unavailable');
 assert.deepEqual(errors,[]);console.log(JSON.stringify({entries:entries.size,initial_milliseconds:initialMilliseconds,member_journeys:journeys,unresolved_dialogs:uncertain,citation_journeys:citations,unresolved_citation_dialogs:unresolvedCitations,verified_facsimiles:visitedSources.size,script_modes:scriptModes,viewports:[1440,320,390,768],browser_errors:errors.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
