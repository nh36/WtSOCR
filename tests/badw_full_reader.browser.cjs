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
 // Preserve all 47 independently accepted fixture members across reviewed extent changes.
 let frozenAccepted=0;
 for(const original of fixture.entries){
  const current=data.entries.find(e=>e.id===original.id);
  for(const ref of original.cross_references)for(const member of ref.target_members||[]){
   if(member.resolution_status!=='resolved')continue;
   const replacement=current.cross_references.find(r=>r.component_id===ref.component_id||r.supersedes_component_id===ref.component_id);assert(replacement);
   const actual=replacement.target_members.find(m=>m.literal===member.literal&&m.source_span.start===member.source_span.start&&m.source_span.end===member.source_span.end);assert(actual);
   assert.equal(actual.resolution_status,'resolved');assert.equal(actual.target_entry_id,member.target_entry_id);assert.deepEqual(actual.source_binding,member.source_binding);frozenAccepted++;
  }
 }
 assert.equal(frozenAccepted,47);
 const wrapped=data.entries.find(e=>e.id==='badw:pdf:badw-v3-14b4f88a35d115421e6df75e14a8b54f43d038366ae6fff493e698d8bbe34151:1769');
 const repaired=wrapped.cross_references.find(r=>r.extent_review);assert(repaired);
 assert.equal(repaired.target_members.length,4);assert(repaired.target_members.every(m=>m.resolution_status==='resolved'));
 assert.equal(repaired.status,'unresolved');assert.equal(repaired.target_entry_id,null);
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
 // Facsimile-checked pairs inside one continuous italic run. Keep their plural
 // parents unresolved while exercising each independently accepted destination.
 for(const id of [
  'badw:pdf:badw-v3-45c686fe81fc99871046464267301efa11a53030167ced5e2df92cee70380505:1288',
  'badw:pdf:badw-v2-8b2374405a57fe2dac90bcd6f028a85a90aec5427b1f0a86bc0d6451ebbca3f1:273',
  'badw:pdf:badw-v3-4d60bc78f20721f4e32d6b2711b54b90c41d52c0566f68c5cffba1c2148afd75:1760',
 ]){
  const meta=entries.get(id);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();
  const pair=entry.cross_references.find(r=>r.target_members?.length===2);assert(pair);
  assert.equal(pair.status,'unresolved');assert.equal(pair.target_entry_id,null);
  assert(pair.target_members.every(m=>m.resolution_status==='resolved'));
  data.entries.push(entry);
 }
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
 // Individually source-bound malformed editorial hrefs, including nested span
 // tags which truncate the parsed label. Broken URLs remain source evidence.
 let editorialJourneys=0,editorialAbsent=0;
 for(const [label,homonym] of [['ldaṅs','2'],['nod','1'],['rbas','1'],['snom','2'],['kun las btus pa','1'],['dkar','1'],['dkar po','1'],['dka’ thub','1'],['ku co','1'],['smag rum','1']]){
  const meta=catalog.find(e=>e.source_kind==='html'&&e.headword.loc===label&&String(e.homonym)===homonym);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();await go(entry);
  const reviewed=entry.cross_references.filter(r=>r.resolution_evidence?.method==='reviewed_exact_editorial_target');assert(reviewed.length);
  for(const ref of reviewed){
  assert(ref.source_url.includes('%3Ctib%3E')||ref.source_url.includes('%3Cspan%20class='));
  assert.equal(ref.resolution_evidence.target_review.source_target_url,ref.source_url);
  if(ref.status==='resolved'){
   const href='#'+encodeURIComponent(ref.target_entry_id);
   const links=page.locator('.reading a');const chosen=await links.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),href);assert(chosen>=0);
   await links.nth(chosen).click();await page.waitForFunction(h=>location.hash===h,href);
   await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(ref.target_entry_id).headword.loc);
   await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);editorialJourneys++;
  }else{
   assert.equal(ref.status,'unresolved');assert.equal(ref.candidate_entry_ids.length,0);
   await page.locator('.reading .uncertain-reference').filter({hasText:ref.wording}).first().click();
   assert((await page.locator('#reference-detail-content').textContent()).includes('no destination'));
   await page.keyboard.press('Escape');editorialAbsent++;
  }
  }
 }
 assert.equal(editorialJourneys,11);assert.equal(editorialAbsent,2);
 // A trailing arrow in a malformed shared anchor has a separately typed
 // sibling target. Its frozen arrow span remains the clickable occurrence.
 const detachedMeta=entries.get('badw:entry:d8553ae3da5102268ab59eff76ae8427e971a905708ea9f6d0cf0f4d204d74b7');
 const detachedEntry=await (await page.request.get(base+'/'+detachedMeta.path)).json();
 const detachedRef=detachedEntry.cross_references.find(r=>r.resolution_evidence?.target_parsing_evidence?.method==='exact_typed_sibling_after_trailing_arrow');assert(detachedRef);
 assert.deepEqual(detachedRef.source_span,{start:678,end:679});assert.equal(detachedRef.wording,'bka’ chen');
 assert.equal(detachedRef.status,'resolved');assert.equal(detachedRef.source_url,null);
 const detachedTargets=detachedRef.target_lexical_entity.witness_entry_ids;assert.equal(detachedTargets.length,1);
 await go(detachedEntry);
 const detachedHref='#'+encodeURIComponent(detachedTargets[0]);
 const detachedButton=page.locator('.reading button').filter({hasText:'↓'}).last();
 await detachedButton.click();assert(await page.locator('#reference-detail').isVisible());
 const detachedChoice=page.locator('#reference-detail-content a[href^="#"]');assert.equal(await detachedChoice.count(),1);
 assert.equal(await detachedChoice.getAttribute('href'),detachedHref);
 await detachedChoice.click();await page.waitForFunction(h=>location.hash===h,detachedHref);
 await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(detachedTargets[0]).headword.loc);
 await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),detachedEntry.headword.loc);
 // Facsimile-reviewed headword tildes preserve their printed labels. Three
 // exact expanded targets navigate; the three absent targets explain abstention.
 let tildeJourneys=0,tildeAbsent=0;
 for(const label of ['cho ’phrul','ñal','gtugs','lta']){
  const meta=catalog.find(e=>e.source_kind==='pdf'&&e.headword.loc===label);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();await go(entry);
  const reviewed=entry.cross_references.filter(r=>r.resolution_evidence?.method==='reviewed_exact_printed_substitution');assert(reviewed.length);
  for(const ref of reviewed){
   assert(ref.wording.includes('~'));
   if(ref.status==='resolved'){
    const href='#'+encodeURIComponent(ref.target_entry_id);
    const links=page.locator('.reading a');const chosen=await links.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),href);assert(chosen>=0);
    await links.nth(chosen).click();await page.waitForFunction(h=>location.hash===h,href);
    await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(ref.target_entry_id).headword.loc);
    await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);tildeJourneys++;
   }else{
    assert.equal(ref.status,'unresolved');assert.equal(ref.candidate_entry_ids.length,0);
    await page.locator('.reading .uncertain-reference').filter({hasText:ref.wording}).first().click();
    const detail=await page.locator('#reference-detail-content').textContent();
    assert(detail.includes('no destination'));assert(detail.includes('reviewed expanded target absent'));
    await page.keyboard.press('Escape');tildeAbsent++;
   }
  }
 }
 assert.equal(tildeJourneys,3);assert.equal(tildeAbsent,3);
 // DOM comma lists retain their own exact members and visible qualifiers.
 let htmlCommaJourneys=0,htmlCommaUncertain=0;
 for(const id of [
  'badw:entry:9d3b5f30749bc5cec5b1d47a385dbac3e9908cab16c6fcd1258f3184749828a4',
  'badw:entry:b6a18a4529ddcb2ede14a6525915400d5d9231f84ee0508bffe4f3763805efec',
  'badw:entry:f250a6b9d9ee3dcc0ba574f91cc205da557a9a2d187ffce8d79410880478e170',
  'badw:entry:7bd1b7853aca4c63ea47bd892246feacdc93d4ea16a19a72db0ddff1dd00ecc9',
  'badw:entry:f26c7a3de2aa7dbe5522bbbfe8146af1d57c46d0bde1d20845c64d1b1a54a974',
  'badw:entry:ef234685ab3cc47c3485c2502afc60986affce5ab52cc4a99302c17f58649c0a',
 ]){
  const entry=await (await page.request.get(base+'/'+entries.get(id).path)).json();
  const ref=entry.cross_references.find(r=>r.resolution_evidence?.method==='exact_source_bound_html_comma_members');assert(ref);
  assert.equal(ref.status,'unresolved');assert.equal(ref.target_entry_id,null);assert.equal(ref.target_members.length,2);
  await go(entry);
  for(const member of ref.target_members){
   if(member.resolution_status==='resolved'){
    assert(member.target_entry_id);const href='#'+encodeURIComponent(member.target_entry_id);
    const links=page.locator('.reading a');const chosen=await links.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),href);assert(chosen>=0);
    await links.nth(chosen).click();await page.waitForFunction(h=>location.hash===h,href);
    await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(member.target_entry_id).headword.loc);
    await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);htmlCommaJourneys++;
   }else{
    const literal=member.literal.replace(/\s+/g,' ');
    const buttons=page.locator('.reading .uncertain-reference');
    const chosen=await buttons.evaluateAll((ns,t)=>ns.findIndex(n=>n.textContent.replace(/\s+/g,' ')===t),literal);assert(chosen>=0);
    await buttons.nth(chosen).click();assert(await page.locator('#reference-detail').isVisible());
    const detail=await page.locator('#reference-detail-content').textContent();
    assert(detail.toLowerCase().includes('no destination'));assert.equal(await page.locator('#reference-detail-content a[href^="#"]').count(),0);
    await page.keyboard.press('Escape');htmlCommaUncertain++;
   }
  }
 }
 assert.equal(htmlCommaJourneys,8);assert.equal(htmlCommaUncertain,4);
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
 assert(journeys>=56);assert(uncertain>=2);assert(unresolvedCitations>=3);
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
 assert.deepEqual(errors,[]);console.log(JSON.stringify({entries:entries.size,initial_milliseconds:initialMilliseconds,member_journeys:journeys,editorial_journeys:editorialJourneys,editorial_absent:editorialAbsent,detached_target_journeys:1,html_comma_journeys:htmlCommaJourneys,html_comma_uncertain:htmlCommaUncertain,tilde_journeys:tildeJourneys,tilde_absent:tildeAbsent,unresolved_dialogs:uncertain,citation_journeys:citations,unresolved_citation_dialogs:unresolvedCitations,verified_facsimiles:visitedSources.size,script_modes:scriptModes,viewports:[1440,320,390,768],browser_errors:errors.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
