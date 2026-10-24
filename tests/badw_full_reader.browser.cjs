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
 const manifest=await (await page.request.get(base+'/manifest.json')).json();
 const catalog=data.entries;assert.equal(catalog.length,29877+(manifest.supplemental_witnesses||0));assert.equal(data.sharded,true);
 await require('./badw_reader_search.browser.cjs').validateSearch(browser,base,catalog);
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
   if(replacement.target_members){
    const actual=replacement.target_members.find(m=>m.literal===member.literal&&m.source_span.start===member.source_span.start&&m.source_span.end===member.source_span.end);assert(actual);
    assert.equal(actual.resolution_status,'resolved');assert.equal(actual.target_entry_id,member.target_entry_id);assert.deepEqual(actual.source_binding,member.source_binding);
   }else{
    assert.equal(replacement.extent_review?.annotation_id,'badw-reviewed-arrow-boundary-thig-1');
    assert.equal(replacement.status,'resolved');assert.equal(replacement.wording,member.literal);
    assert.deepEqual(member.source_span,{start:replacement.source_span.start+1,end:replacement.source_span.end});
    assert.equal(replacement.target_entry_id,member.target_entry_id);assert.deepEqual(replacement.source_binding,ref.source_binding);
    assert.deepEqual(replacement.parsed_target,member.printed_target);
   }
   frozenAccepted++;
  }
 }
 assert.equal(frozenAccepted,47);
 const wrapped=data.entries.find(e=>e.id==='badw:pdf:badw-v3-14b4f88a35d115421e6df75e14a8b54f43d038366ae6fff493e698d8bbe34151:1769');
 const repaired=wrapped.cross_references.find(r=>r.extent_review);assert(repaired);
 assert.equal(repaired.target_members.length,4);assert(repaired.target_members.every(m=>m.resolution_status==='resolved'));
 assert.equal(repaired.status,'unresolved');assert.equal(repaired.target_entry_id,null);
 assert.equal(data.preview.reviewed_occurrences,23);
 const url=id=>base+'/#'+encodeURIComponent(id);
 // A changed hash precedes asynchronous entry rendering. Wait for the exact
 // selected identity and its source controls, including prefix-sharing labels.
 async function selected(href){await page.waitForFunction(h=>location.hash===h&&document.querySelector('#entries [aria-current]')?.getAttribute('href')===h&&document.querySelector('#article > .source-access a'),href);}
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
 // A recovered editorial article has its own explicit homonym identity. The
 // acquired homonym 1 stays distinct, and browser history returns to the source.
 if(manifest.supplemental_witnesses){
  const targetMeta=entries.get('badw:entry:17d8c073e0aef6a87940c7009907fbaeeebfec3aae633a87e23a527632b4816d');assert(targetMeta);
  const drugMeta=catalog.find(e=>e.headword.loc==='drug'&&e.homonym==='2');assert(drugMeta);
  const drug=await (await page.request.get(base+'/'+drugMeta.path)).json();
  const ref=drug.cross_references.find(r=>r.target_entry_id===targetMeta.id);assert(ref);assert.equal(ref.status,'resolved');
  await go(drug);
  const link=page.locator('.reading a');
  const n=await link.evaluateAll((nodes,href)=>nodes.findIndex(el=>el.getAttribute('href')===href),'#'+encodeURIComponent(targetMeta.id));assert(n>=0);
  await link.nth(n).focus();await page.keyboard.press('Enter');
  await selected('#'+encodeURIComponent(targetMeta.id));
  await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('dru gu'));
  assert(await page.locator('#article > .source-access a[href="https://wts-digital.badw.de/lemma/dru%20gu/2"]').count());
  await page.goBack();await selected('#'+encodeURIComponent(drug.id));
  await page.goForward();await selected('#'+encodeURIComponent(targetMeta.id));
  assert(catalog.some(e=>e.headword.loc==='dru gu'&&e.homonym==='1'&&e.id!==targetMeta.id));
 }
 // Individually reviewed spelling/compound links preserve their literal
 // labels while reaching hash-verified editorial headings. No global rule.
 let editorialVariantJourneys=0;
 for(const [sourceId,literal,destination] of [
  ['badw:entry:0e2af2fa687900651e6cfba9e312b6a6cc637f059440e67cdfab0c63320b6c12','kiṅ śị','kiṅ śi'],
  ['badw:entry:c903f897858c9193923e511914000e294a6724b060ca5b04621a8202c04285ab','kiṅ śị','kiṅ śi'],
  ['badw:entry:6e7f3c91163071a79e59cbcfef94e477f91457af260b09acc186b8e3fc587596','kiṅ śị','kiṅ śi'],
  ['badw:entry:4acae5d5587079b033c5941094197c1d01194a5abe98afe49d6139e8a339ffa4','kiṅ śị','kiṅ śi'],
  ['badw:entry:fb59948c7cf7f58dff4862ca71f5593f6399c9951cf471569ef5b19a087c5d5c','dug-mo-ñuṅ','dug mo ñuṅ'],
  ['badw:entry:f83b9ff2bb09f46b18632bfad212b7c208a79e99e65a724a8a88741a684395d6','dug-mo-ñuṅ','dug mo ñuṅ'],
  ['badw:entry:25928411ccc5f88650577b84c9edb571462a4c4a21b3ccb89524be82528ec598','mu-stegs-pa','mu stegs pa']]){
  const meta=entries.get(sourceId);assert(meta);
  const e=await (await page.request.get(base+'/'+meta.path)).json();
  const r=e.cross_references.find(r=>r.resolution_evidence?.target_review?.basis==='reviewed_editorial_headword_variant');assert(r);
  assert.equal(r.status,'resolved');assert.equal(r.wording,literal);
  const target=entries.get(r.target_entry_id);assert.equal(target.headword.loc,destination);assert.equal(target.homonym,'1');
  await go(e);
  const links=page.locator('.reading a');
  const n=await links.evaluateAll((nodes,href)=>nodes.findIndex(el=>el.getAttribute('href')===href),'#'+encodeURIComponent(target.id));assert(n>=0);
  assert((await links.nth(n).textContent()).includes(literal));
  await links.nth(n).focus();await page.keyboard.press('Enter');
  await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),target.headword.loc);
  assert(await page.locator('#article > .source-access a').count()>0);
  await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),e.headword.loc);
  await page.goForward();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),target.headword.loc);
  editorialVariantJourneys++;
 }
 assert.equal(editorialVariantJourneys,7);
 // The printed compound stays literal; its individually reviewed destination
 // is established by the deity definition and Neb 313, not a general alias.
 const compoundMeta=entries.get('badw:pdf:badw-v3-1d977621afbefaf1db170e3bec2e2acd3a966d3fde30b8f6369a42611c434462:1579');assert(compoundMeta);
 const compoundEntry=await (await page.request.get(base+'/'+compoundMeta.path)).json();
 const compoundRef=compoundEntry.cross_references.find(r=>r.resolution_evidence?.method==='reviewed_exact_printed_compound');assert(compoundRef);
 assert.equal(compoundRef.wording,'gyad-mo');assert.deepEqual(compoundRef.source_span,{start:11,end:19});assert.equal(compoundRef.status,'resolved');
 const compoundTarget=entries.get(compoundRef.target_entry_id);assert.equal(compoundTarget.headword.loc,'gyad mo');assert.equal(compoundTarget.homonym,'');
 await go(compoundEntry);
 const compoundLink=page.locator('.reading a').filter({hasText:'gyad-mo'});assert.equal(await compoundLink.count(),1);
 assert(await page.locator('#article > .source-access a').count()>0);
 await compoundLink.focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('gyad mo'));
 assert(await page.locator('#article > .source-access a').count()>0);
 await page.goBack();await page.waitForFunction(()=>document.querySelector('.reading')?.textContent.includes('gyad-mo'));
 await page.goForward();await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('gyad mo'));
 const numberedCompoundMeta=catalog.find(e=>e.headword.loc==='kaṅ ka rgod mgo');assert(numberedCompoundMeta);
 const numberedCompound=await (await page.request.get(base+'/'+numberedCompoundMeta.path)).json();
 const numberedRef=numberedCompound.cross_references.find(r=>r.wording==='gyad-mo');assert(numberedRef);
 assert.equal(numberedRef.status,'unresolved');assert.equal(numberedRef.target_entry_id,null);
 // An individually reviewed reciprocal perfect paradigm identifies homonym 1.
 const reciprocalMeta=entries.get('badw:pdf:badw-v3-6a87e97597dc33da0b83005819251e26f368adb33f4890a1103470240c63a92e:485');assert(reciprocalMeta);
 const reciprocalEntry=await (await page.request.get(base+'/'+reciprocalMeta.path)).json();
 const reciprocalRef=reciprocalEntry.cross_references.find(r=>r.resolution_evidence?.method==='reviewed_exact_reciprocal_perfect');assert(reciprocalRef);
 assert.equal(reciprocalRef.wording,'’jum');assert.deepEqual(reciprocalRef.source_span,{start:8,end:13});assert.equal(reciprocalRef.status,'resolved');
 const reciprocalTarget=entries.get(reciprocalRef.target_entry_id);assert.equal(reciprocalTarget.headword.loc,'’jum');assert.equal(reciprocalTarget.homonym,'1');
 await go(reciprocalEntry);
 const reciprocalLink=page.locator('.reading a').filter({hasText:'’jum'});assert.equal(await reciprocalLink.count(),1);
 assert(await page.locator('#article > .source-access a').count()>0);
 await reciprocalLink.focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('’jum'));
 assert.equal(decodeURIComponent(await page.evaluate(()=>location.hash.slice(1))),reciprocalTarget.id);
 assert(await page.locator('#article > .source-access a').count()>0);
 await page.goBack();await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('bcum'));
 await page.goForward();await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('’jum'));
 // Further individually reviewed paradigms include a destination homonym 2.
 for(const [id,source,target,homonym,end,start=8] of [["badw:pdf:badw-v2-48d35d1f99eb48c897d464b20a5b6bfa05721028f717693ef68bd8fad396ee1f:477", "gas", "’gas", "1", 13], ["badw:pdf:badw-v2-8b2374405a57fe2dac90bcd6f028a85a90aec5427b1f0a86bc0d6451ebbca3f1:273", "groṅs", "’groṅs", "1", 15], ["badw:pdf:badw-v2-eafe95ccfbbc796b97a4f4987f73a344da6240c45d5a2e35ce8b7e2a4e12519d:632", "khol", "’khol", "2", 14], ["badw:pdf:badw-v2-2825decd4210a03624a1267f9e71f178cc4bd8f75ba382d34299fab303ec252c:2330", "brgyas", "brgya", "2", 14], ["badw:pdf:badw-v2-b108dd8667b5c6ca7e376cfee40640587a5e5c3871adcc089020811b4554cfb7:1930", "bsgrags", "sgrog", "1", 27, 21], ["badw:pdf:badw-v2-b2874d6d3d91f7e23e6692d1f8e1d00fc022d80c8b3b7a42707c98f7b78c4733:2073", "khyer", "’khyer", "1", 25, 18]]){
  const meta=entries.get(id);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();
  const ref=entry.cross_references.find(r=>r.resolution_evidence?.method==='reviewed_exact_reciprocal_perfect');assert(ref);
  assert.equal(ref.status,'resolved');assert.equal(ref.wording,target);
  assert.deepEqual(ref.source_span,{start,end});
  const destination=entries.get(ref.target_entry_id);assert.equal(destination.headword.loc,target);assert.equal(destination.homonym,homonym);
  await go(entry);
  const link=page.locator('.reading a').filter({hasText:target});assert.equal(await link.count(),1);
  await link.focus();await page.keyboard.press('Enter');
  await selected('#'+encodeURIComponent(destination.id));
  await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),target);
  assert(await page.locator('#article > .source-access a').count()>0);
  await page.goBack();await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),source);
  await page.goForward();await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),target);
 }
 // Complementary perfect-and-future paradigms identify two numbered entries.
 for(const [id,source,target,start,end] of [
  ['badw:pdf:badw-v4-1c8e4f8581322c3f8d5f25d6e4fffa6ad2734d46caa924552ab7af07da1f045f:0','gtad','gtod',17,22],
  ['badw:pdf:badw-v4-eb65fff2be55dc564c68855c84e0b5dce23749b2cf1adaf8051b95d3137b5b4e:664','gtod','gtad',14,19]]){
  const meta=entries.get(id);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();
  const ref=entry.cross_references.find(r=>r.resolution_evidence?.method==='reviewed_exact_reciprocal_perfect_future');assert(ref);
  assert.equal(ref.status,'resolved');assert.equal(ref.wording,target);
  assert.deepEqual(ref.source_span,{start,end});
  const destination=entries.get(ref.target_entry_id);assert.equal(destination.headword.loc,target);assert.equal(destination.homonym,'1');
  await go(entry);
  const link=page.locator('.reading a').filter({hasText:target});assert.equal(await link.count(),1);
  await link.focus();await page.keyboard.press('Enter');await selected('#'+encodeURIComponent(destination.id));
  await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),target);
  assert(await page.locator('#article > .source-access a').count()>0);
  await page.goBack();await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),source);
  await page.goForward();await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),target);
 }
 // Complementary perfect-and-imperative paradigms identify two numbered entries.
 for(const [id,source,target,start,end] of [
  ["badw:pdf:badw-v2-82e01ef85ce15f1c8626bb1548d2999953dc75355fd9cc4f9edb9681a5c59cb0:1588", "gyur", "’gyur", 36, 42],
  ["badw:pdf:badw-v2-1b84ba2586a82f90866aedbb0f595515e5b308f2a3f72af2a9e7459a0549a934:793", "’gyur", "gyur", 14, 19]]){
  const meta=entries.get(id);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();
  const ref=entry.cross_references.find(r=>r.resolution_evidence?.method==='reviewed_exact_reciprocal_perfect_imperative');assert(ref);
  assert.equal(ref.status,'resolved');assert.equal(ref.wording,target);
  assert.deepEqual(ref.source_span,{start,end});
  const destination=entries.get(ref.target_entry_id);assert.equal(destination.headword.loc,target);assert.equal(destination.homonym,'1');
  await go(entry);
  const link=page.locator('.reading a').filter({hasText:target});assert.equal(await link.count(),1);
  await link.focus();await page.keyboard.press('Enter');await selected('#'+encodeURIComponent(destination.id));
  await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),target);
  assert(await page.locator('#article > .source-access a').count()>0);
  await page.goBack();await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),source);
  await page.goForward();await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),target);
 }
 // Batch-adjudicated grammatical identities retain literal source extents.
 let grammaticalBatchJourneys=0;
 for(const [id,source,target,homonym,start,end,method] of [["badw:pdf:badw-v2-b108dd8667b5c6ca7e376cfee40640587a5e5c3871adcc089020811b4554cfb7:1566", "bsgrag", "sgrog", "1", 9, 15, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v2-d046ffeed24861654ecb97d49c872663ac0d3cdf190e658ab0810ed0623a911b:163", "rgyoṅ", "brgyaṅs", "1", 5, 13, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v3-c1970fa5a7c46672badf5fdece4e18f9c5e7dea8f3f5eb1ecb1812b54826498b:0", "ños", "ño", "2", 17, 20, "reviewed_exact_reciprocal_perfect_imperative"], ["badw:pdf:badw-v2-01c106c697d5459227c049b9dd06b62fe98df7bf9e4d39527b7f9557cf74e2c7:2329", "’groṅ", "’groṅs", "1", 9, 16, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v2-cde781aaf39b434b88c938fe7f722b42ecdc0d700f8b4cb6a85974fcbb82b34d:285", "’groṅs", "’groṅ", "1", 6, 12, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v3-6ffabab9a505c6c2c8eaab3dd34725afadbb62a5433180329b81604eb18847fc:1638", "’joms", "bcom", "1", 5, 10, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v2-f73596e90cb59ae277d125fabfc02528028d14e20ec8737f5412d4102b28027e:830", "’khol", "khol", "2", 5, 10, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v2-20b81e0bdb6e0a29f1cf9f05183d1c61cf71e24a1a58d6b194e7306ec042cff4:1424", "’khon bzuṅ", "’khon ’dzin", "1", 24, 36, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v2-78a3b1d2c6689a5269b89f294522ef6e943f3187a5aebf77fc685edfeff12177:1512", "’khu", "’khus", "1", 15, 21, "reviewed_exact_grammatical_reciprocal"], ["badw:pdf:badw-v2-28a8d1cf6674188c8bfee5352add16557f89323762f5e419c40ee6ab726373ce:1351", "’khyer", "khyer", "1", 5, 11, "reviewed_exact_grammatical_reciprocal"]]){
  const meta=entries.get(id);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();
  const ref=entry.cross_references.find(r=>r.source_span.start===start&&r.source_span.end===end&&r.resolution_evidence?.method===method);assert(ref);
  assert.equal(ref.status,'resolved');assert.equal(ref.wording,target);
  const destination=entries.get(ref.target_entry_id);assert.equal(destination.headword.loc,target);assert.equal(destination.homonym,homonym);
  await go(entry);
  const links=page.locator('.reading a');
  const n=await links.evaluateAll((nodes,href)=>nodes.findIndex(el=>el.getAttribute('href')===href),'#'+encodeURIComponent(destination.id));assert(n>=0);
  await links.nth(n).focus();await page.keyboard.press('Enter');await selected('#'+encodeURIComponent(destination.id));
  await page.waitForFunction(word=>document.querySelector('#article h2')?.textContent.includes(word),target);
  const sources=page.locator('#article > .source-access a');assert(await sources.count()>0);
  for(const href of await sources.evaluateAll(nodes=>nodes.map(n=>n.href)))if(href.startsWith(base))assert.equal((await page.request.get(href)).status(),200);
  await page.goBack();await selected('#'+encodeURIComponent(entry.id));
  await page.goForward();await selected('#'+encodeURIComponent(destination.id));
  grammaticalBatchJourneys++;
 }
 assert.equal(grammaticalBatchJourneys,10);
 // The printed raised reciprocal qualifier establishes thul 1 specifically.
 {
  const meta=entries.get('badw:pdf:badw-v4-bd3109dea567834eac8fb3e7c547ab652c3c4329ddd1ede095333f602c0957ac:445');assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();
  const ref=entry.cross_references.find(r=>r.resolution_evidence?.method==='reviewed_exact_qualified_reciprocal_perfect');assert(ref);
  assert.equal(ref.status,'resolved');assert.equal(ref.wording,'’thul');
  assert.deepEqual(ref.source_span,{start:8,end:14});
  assert.equal(ref.resolution_evidence.target_review.source_homonym,'1');
  const destination=entries.get(ref.target_entry_id);assert.equal(destination.headword.loc,'’thul');assert.equal(destination.homonym,'1');
  await go(entry);
  const link=page.locator('.reading a').filter({hasText:'’thul'});assert.equal(await link.count(),1);
  await link.focus();await page.keyboard.press('Enter');await selected('#'+encodeURIComponent(destination.id));
  await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('’thul'));
  assert(await page.locator('#article > .source-access a').count()>0);
  await page.goBack();await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('thul'));
  await selected('#'+encodeURIComponent(entry.id));
  await page.goForward();await selected('#'+encodeURIComponent(destination.id));
 }
 // A confirmed printed marker error has an explicit interpretation, while
 // its literal ↑fut and the unresolved numbered imperative remain visible.
 const printedMeta=entries.get('badw:pdf:badw-v2-a58041c8ebea1dab16a0479fa5d9830cf2d2f3bd393a95b4f62c7d801b8b2574:2381');
 const printedEntry=await (await page.request.get(base+'/'+printedMeta.path)).json();
 const printedRef=printedEntry.cross_references.find(r=>r.resolution_evidence?.method==='reviewed_printed_misplaced_arrow');assert(printedRef);
 assert.equal(printedRef.marker+printedRef.wording,'↑fut');assert.deepEqual(printedRef.source_span,{start:13,end:17});assert.equal(printedRef.status,'resolved');
 assert(printedEntry.cross_references.some(r=>r.wording.includes('khrus')&&r.status!=='resolved'));
 await go(printedEntry);
 assert((await page.locator('.editorial-interpretation').textContent()).includes('fut. ↑bkru'));
 assert((await page.locator('.editorial-interpretation').textContent()).includes('↑fut'));
 const printedLink=page.locator('.reading a').filter({hasText:'fut'});assert.equal(await printedLink.count(),1);
 assert((await printedLink.getAttribute('title')).includes('Printed marker error'));
 await printedLink.focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('bkru'));
 await page.goBack();await page.waitForFunction(()=>document.querySelector('.editorial-interpretation'));
 await page.goForward();await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('bkru'));

 let journeys=0,uncertain=0,citations=0,unresolvedCitations=0;
 // A reviewed nonprinting font-switch interlude remains in the literal source;
 // its independently replayed lookup expression reaches the exact PDF entry.
 const bridgeMeta=entries.get('badw:pdf:badw-v2-75b4d859af9a9790acfa1e6532e8ab9c71309fb693334b0372f229c24f02cf40:1108');
 const bridgeEntry=await (await page.request.get(base+'/'+bridgeMeta.path)).json();
 const bridgeRef=bridgeEntry.cross_references.find(r=>r.extent_review?.annotation_id==='badw-reviewed-nonprinting-bridge-dgra-bla');assert(bridgeRef);
 assert.equal(bridgeRef.status,'resolved');assert(bridgeRef.wording.includes('⟦UNKNOWN:Arial:italic:0003:ebbba6ed181c⟧'));
 const bridgeTarget=entries.get(bridgeRef.target_entry_id);assert.equal(bridgeTarget.headword.loc,'’go ba’i lha');
 await go(bridgeEntry);
 const bridgeLink=page.locator('.reading a');
 const bridgeHref='#'+encodeURIComponent(bridgeRef.target_entry_id);
 const bridgeIndex=await bridgeLink.evaluateAll((nodes,href)=>nodes.findIndex(n=>n.getAttribute('href')===href),bridgeHref);assert(bridgeIndex>=0);
 await bridgeLink.nth(bridgeIndex).focus();await page.keyboard.press('Enter');
 await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),bridgeTarget.headword.loc);
 await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),bridgeEntry.headword.loc);
 await page.goForward();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),bridgeTarget.headword.loc);
 assert(await page.locator('#article > .source-access a').count()>0);
 // A reviewed reference continues across consecutive printed pages in one PDF.
 const pageFixture=JSON.parse(fs.readFileSync('tests/fixtures/badw_pdf_page_continuation.json'));
 const pageMeta=entries.get(pageFixture.identity);assert(pageMeta);
 const pageEntry=await (await page.request.get(base+'/'+pageMeta.path)).json();
 const pageRef=pageEntry.cross_references.find(r=>r.extent_review?.annotation_id==='badw-reviewed-page-continuation-thabs');assert(pageRef);
 assert.equal(pageRef.status,'resolved');assert.equal(pageRef.wording,'pha\nrol tu phyin pa');
 assert.deepEqual(pageRef.source_span,{start:pageFixture.new.start,end:pageFixture.new.end});
 const pageTarget=entries.get(pageRef.target_entry_id);assert.equal(pageTarget.headword.loc,'pha rol tu phyin pa');
 await go(pageEntry);
 const pageLinks=page.locator('.reading a');
 const pageLinkIndex=await pageLinks.evaluateAll((nodes,href)=>nodes.findIndex(n=>n.getAttribute('href')===href),'#'+encodeURIComponent(pageTarget.id));assert(pageLinkIndex>=0);
 await pageLinks.nth(pageLinkIndex).focus();await page.keyboard.press('Enter');
 await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),pageTarget.headword.loc);
 assert(await page.locator('#article > .source-access a').count()>0);
 await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),pageEntry.headword.loc);
 await page.goForward();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),pageTarget.headword.loc);
 // Six facsimile-reviewed upright-space extents retain literal source text.
 // Completing an extent must not invent an unavailable destination.
 let uprightSpaceJourneys=0,uprightSpaceAbsent=0;
 const uprightFixtures=JSON.parse(fs.readFileSync('tests/fixtures/badw_upright_space_references.json'));
 for(const f of uprightFixtures){
  const meta=entries.get(f.identity);assert(meta);
  const e=await (await page.request.get(base+'/'+meta.path)).json();
  const r=e.cross_references.find(r=>r.extent_review?.claim.basis==='reviewed_printed_upright_space');assert(r);
  assert.deepEqual(r.source_span,{start:f.new.start,end:f.new.end});
  assert.equal(e.components.find(c=>c.id===r.component_id).source_form,f.new.literal);
  const unit=r.target_members?.[0]||r;
  await go(e);
  if((unit.resolution_status||unit.status)==='resolved'){
   const target=entries.get(unit.target_entry_id);assert(target);
   const links=page.locator('.reading a');
   const n=await links.evaluateAll((nodes,href)=>nodes.findIndex(el=>el.getAttribute('href')===href),'#'+encodeURIComponent(target.id));assert(n>=0);
   await links.nth(n).focus();await page.keyboard.press('Enter');
   await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),target.headword.loc);
   assert(await page.locator('#article > .source-access a').count()>0);
   await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),e.headword.loc);
   await page.goForward();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),target.headword.loc);
   uprightSpaceJourneys++;
  }else{
   assert.equal(unit.target_entry_id,null);
   const uncertain=page.locator('.reading .uncertain-reference').filter({hasText:f.target.split(',')[0]});assert.equal(await uncertain.count(),1);
   await uncertain.click();assert(await page.locator('#reference-detail').isVisible());
   assert((await page.locator('#reference-detail-content').textContent()).includes('no destination'));
   await page.keyboard.press('Escape');assert(await uncertain.evaluate(n=>n===document.activeElement));
   uprightSpaceAbsent++;
  }
 }
 assert.equal(uprightSpaceJourneys,5);assert.equal(uprightSpaceAbsent,1);
 // Two printed arrows remain separate occurrences. Contracting the first
 // extent preserves its already accepted ka thig destination and leaves the
 // independently printed tshaṅs thig unresolved, with its own explanation.
 const thigMeta=entries.get('badw:pdf:badw-v4-5644b990758444b6b7b00f0adbb75fcdfe54b08c0bd3ec6c80120cbaea4a2281:605');assert(thigMeta);
 const thig=await (await page.request.get(base+'/'+thigMeta.path)).json();
 const contracted=thig.cross_references.find(r=>r.extent_review?.annotation_id==='badw-reviewed-arrow-boundary-thig-1');assert(contracted);
 assert.equal(contracted.status,'resolved');assert.equal(contracted.wording,'ka thig');assert(!contracted.target_members);
 const separate=thig.cross_references.find(r=>r.wording==='tshaṅs thig');assert(separate);assert.equal(separate.status,'unresolved');assert.equal(separate.target_entry_id,null);
 await go(thig);
 const thigLinks=page.locator('.reading a');
 const thigLinkIndex=await thigLinks.evaluateAll((nodes,href)=>nodes.findIndex(n=>n.getAttribute('href')===href),'#'+encodeURIComponent(contracted.target_entry_id));assert(thigLinkIndex>=0);
 await thigLinks.nth(thigLinkIndex).focus();await page.keyboard.press('Enter');
 await selected('#'+encodeURIComponent(contracted.target_entry_id));
 await page.goBack();await selected('#'+encodeURIComponent(thig.id));
 journeys++; // The preserved fixture destination is now a single reference.
 await page.locator('.reading .uncertain-reference').filter({hasText:'tshaṅs thig'}).waitFor();
 const thigUncertain=page.locator('.reading .uncertain-reference').filter({hasText:'tshaṅs thig'});assert.equal(await thigUncertain.count(),1);
 await thigUncertain.click();assert(await page.locator('#reference-detail').isVisible());assert((await page.locator('#reference-detail-content').textContent()).includes('no destination'));
 await page.keyboard.press('Escape');assert(await thigUncertain.evaluate(n=>n===document.activeElement));
 uncertain++; // Its own occurrence replaces the former duplicated list member.
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
     await selected('#'+encodeURIComponent(member.target_entry_id));
     await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(member.target_entry_id).headword.loc);
     await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);
     await page.goForward();await selected('#'+encodeURIComponent(member.target_entry_id));
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
   await links.nth(chosen).click();await selected(href);
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
 // Whitespace in four individually reviewed hrefs is kept as source evidence.
 // Exact destinations navigate; absent or differently qualified identities do not.
 let whitespaceJourneys=0,whitespaceUnresolved=0;
 for(const label of ['piṇḍa pa','’brog ’brog','me loṅ lta bu’i ye śes','po ta la']){
  const meta=catalog.find(e=>e.source_kind==='html'&&e.headword.loc===label);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();await go(entry);
  const ref=entry.cross_references.find(r=>r.resolution_evidence?.target_review?.annotation_id?.startsWith('badw-reviewed-editorial-whitespace-'));assert(ref);
  assert.equal(ref.resolution_evidence.target_review.source_target_url,ref.source_url);
  assert.equal(ref.resolution_evidence.target_review.homonym,'1');
  if(['piṇḍa pa','’brog ’brog'].includes(label)){
   assert.equal(ref.status,'resolved');
   const href='#'+encodeURIComponent(ref.target_entry_id);
   const links=page.locator('.reading a');const chosen=await links.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),href);assert(chosen>=0);
   await links.nth(chosen).focus();await page.keyboard.press('Enter');
   await selected(href);
   await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(ref.target_entry_id).headword.loc);
   assert(await page.locator('#article > .source-access a').count()>0);
   await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),label);
   await page.goForward();await selected(href);whitespaceJourneys++;
  }else{
   assert.equal(ref.status,'unresolved');assert.equal(ref.target_entry_id,null);
   await page.locator('.reading .uncertain-reference').filter({hasText:ref.wording}).first().click();
   assert((await page.locator('#reference-detail-content').textContent()).includes('no destination'));
   await page.keyboard.press('Escape');whitespaceUnresolved++;
  }
 }
 assert.equal(whitespaceJourneys,2);assert.equal(whitespaceUnresolved,2);
 // The editorial anchor contains only the apostrophe; its immediately adjacent
 // Tibetan element supplies the rest of the individually reviewed target.
 const splitMeta=entries.get('badw:entry:055cc21052cbdb35872dc282a400ec1493f5ee80480807f9492ad33940476181');
 const splitEntry=await (await page.request.get(base+'/'+splitMeta.path)).json();
 const splitRef=splitEntry.cross_references.find(r=>r.resolution_evidence?.target_review?.basis==='reviewed_split_editorial_anchor');assert(splitRef);
 assert.deepEqual(splitRef.source_span,{start:59,end:61});
 assert.equal(splitRef.source_url,'https://wts-digital.badw.de/lemma/%E2%80%99/1');
 assert.equal(splitRef.resolution_evidence.target_review.lemma,'’dren');
 assert.equal(splitRef.resolution_evidence.target_review.homonym,null);
 assert.equal(splitRef.status,'resolved');
 assert.equal(splitRef.target_entry_id,'badw:entry:c2d69506408ac2708416ce0f7a50c9c945568b5c94242bc447459f58e9468625');
 await go(splitEntry);
 const splitHref='#'+encodeURIComponent(splitRef.target_entry_id);
 const splitLink=page.locator('.reading a').filter({hasText:'’'});
 const splitChosen=await splitLink.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),splitHref);assert(splitChosen>=0);
 assert.equal((await splitLink.nth(splitChosen).textContent()).replace('↑',''),'’');
 await splitLink.nth(splitChosen).focus();await page.keyboard.press('Enter');
 await selected(splitHref);
 await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('’dren'));
 await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.getAttribute('href')===h,splitHref);
 assert(await page.locator('#article > .source-access a').count()>0);
 await page.goBack();await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('’drend'));
 await page.goForward();await selected(splitHref);
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
 await detachedChoice.click();await selected(detachedHref);
 await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(detachedTargets[0]).headword.loc);
 await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),detachedEntry.headword.loc);
 // Facsimile-reviewed headword tildes preserve their printed labels. Three
 // exact expanded targets navigate; two absent targets explain abstention.
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
    await links.nth(chosen).click();await selected(href);
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
 assert.equal(tildeJourneys,3);assert.equal(tildeAbsent,2);
 // Individually reviewed wrapped PDF headings preserve source/index readings.
 // The three qualified HTML counterparts remain uncertain rather than having
 // their explicit homonym 1 silently mapped to an unnumbered PDF identity.
 let wrappedHeadingJourneys=0;
 for(const label of ['ñu le ñab kyi lag riṅ','cho ’phrul','ñer len phuṅ po']){
  const meta=catalog.find(e=>e.source_kind==='pdf'&&e.headword.loc===label);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();await go(entry);
  const refs=entry.cross_references.filter(r=>r.resolution_evidence?.method==='reviewed_exact_wrapped_headword');assert.equal(refs.length,1);
  const ref=refs[0];assert.equal(ref.status,'resolved');assert(ref.target_entry_id);
  const target=entries.get(ref.target_entry_id);assert(target.headword.loc.includes('\n'));assert.equal(target.homonym,'');
  const href='#'+encodeURIComponent(ref.target_entry_id);
  const links=page.locator('.reading a');const chosen=await links.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),href);assert(chosen>=0);
  await links.nth(chosen).click();await selected(href);
  await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),target.headword.loc);
  assert(await page.locator('.source-access a').count()>0);
  await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);
  await page.goForward();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),target.headword.loc);
  wrappedHeadingJourneys++;
 }
 assert.equal(wrappedHeadingJourneys,3);
 for(const label of ['bdud kyi źags pa dgu sgrol','dom nag sdig pa’i mgo bo can','na ra seṅ ha']){
  const meta=catalog.find(e=>e.source_kind==='html'&&e.headword.loc===label);assert(meta);
  const entry=await (await page.request.get(base+'/'+meta.path)).json();await go(entry);
  const refs=entry.cross_references.filter(r=>r.wording.includes(label==='na ra seṅ ha'?'stobs ldan pho ña sde brgyad':'jo bo klu bdud mched dgu'));assert(refs.length);
  for(const ref of refs){assert.notEqual(ref.status,'resolved');assert(!ref.target_entry_id);}
 }
 // DOM comma lists retain their own exact members and visible qualifiers.
 let htmlCommaJourneys=0,htmlCommaUncertain=0,memberWhitespaceJourneys=0,memberWhitespaceAmbiguous=0;
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
   const reviewedWhitespace=member.target_review?.basis==='reviewed_editorial_member_whitespace';
   if(reviewedWhitespace){
    assert(member.literal.includes('\u00a0'));
    assert.equal(member.parsed_target.source_lexical_target,member.literal);
    assert.equal(member.parsed_target.lexical_target,member.literal.replaceAll('\u00a0',' '));
    assert.equal(member.target_review.homonym,null);
    assert.equal(member.resolution_status,'resolved');
   }
   if(member.resolution_status==='resolved'){
    assert(member.target_entry_id);const href='#'+encodeURIComponent(member.target_entry_id);
    const links=page.locator('.reading a');const chosen=await links.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),href);assert(chosen>=0);
    await links.nth(chosen).focus();await page.keyboard.press('Enter');await selected(href);
    await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(member.target_entry_id).headword.loc);
    assert(await page.locator('#article > .source-access a').count()>0);
    await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);htmlCommaJourneys++;
    if(reviewedWhitespace){
     await page.goForward();await selected(href);
     await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entries.get(member.target_entry_id).headword.loc);
     await page.goBack();await page.waitForFunction(label=>document.querySelector('#article h2')?.textContent.includes(label),entry.headword.loc);
     memberWhitespaceJourneys++;
    }
   }else{
    const literal=member.literal.replace(/\s+/g,' ');
    const buttons=page.locator('.reading .uncertain-reference');
    const chosen=await buttons.evaluateAll((ns,t)=>ns.findIndex(n=>n.textContent.replace(/\s+/g,' ')===t),literal);assert(chosen>=0);
    await buttons.nth(chosen).click();assert(await page.locator('#reference-detail').isVisible());
    const detail=await page.locator('#reference-detail-content').textContent();
    assert(detail.toLowerCase().includes('no destination'));assert.equal(await page.locator('#reference-detail-content a[href^="#"]').count(),0);
    if(entry.headword.loc==='rmyaṅ'&&member.literal==='rñaṅ'){
     assert.equal(member.resolution_status,'ambiguous');assert.equal(member.exact_index_candidate_ids.length,2);
     assert(detail.includes('rñaṅ'));memberWhitespaceAmbiguous++;
    }
    await page.keyboard.press('Escape');htmlCommaUncertain++;
   }
  }
 }
 assert.equal(htmlCommaJourneys,10);assert.equal(htmlCommaUncertain,2);
 assert.equal(memberWhitespaceJourneys,2);assert.equal(memberWhitespaceAmbiguous,1);
 // A facsimile-reviewed upright final r belongs to the target, despite the
 // italic-run boundary. Follow its exact destination and return by history.
 const terminalMeta=catalog.find(e=>e.source_kind==='pdf'&&e.headword.loc==='kha kha khyer');assert(terminalMeta);
 const terminalEntry=await (await page.request.get(base+'/'+terminalMeta.path)).json();
 const terminalRef=terminalEntry.cross_references.find(r=>r.extent_review);assert(terminalRef);
 assert.deepEqual(terminalRef.source_span,{start:1,end:11});
 assert.equal(terminalRef.wording,'kha khyer');assert.equal(terminalRef.status,'resolved');
 assert.equal(entries.get(terminalRef.target_entry_id).headword.loc,'kha khyer');
 await go(terminalEntry);
 const terminalHref='#'+encodeURIComponent(terminalRef.target_entry_id);
 const terminalLinks=page.locator('.reading a');
 const terminalIndex=await terminalLinks.evaluateAll((ns,h)=>ns.findIndex(n=>n.getAttribute('href')===h),terminalHref);assert(terminalIndex>=0);
 await terminalLinks.nth(terminalIndex).click();await selected(terminalHref);
 await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('kha khyer'));
 await page.goBack();await page.waitForFunction(()=>document.querySelector('#article h2')?.textContent.includes('kha kha khyer'));
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
 await page.locator('[rel=prev]').click();await selected('#'+encodeURIComponent(catalog[1].id));
 assert.equal(await page.locator('#entries a').count(),100);
 const hash=await page.evaluate(()=>location.hash);await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>location.hash),hash);
 await page.locator('#search').fill('impossible headword');assert((await page.locator('#entries').textContent()).includes('No matching'));
 await page.locator('#search').fill('');await page.locator('#search').focus();await page.keyboard.press('ArrowDown');assert(await page.locator('#entries a').first().evaluate(n=>n===document.activeElement));await page.keyboard.press('End');assert(await page.locator('#entries a').last().evaluate(n=>n===document.activeElement));await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await selected('#'+encodeURIComponent(catalog[1].id));
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
 const destination=await choices.first().getAttribute('href');await choices.first().click();await selected(destination);
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
 assert.deepEqual(errors,[]);console.log(JSON.stringify({entries:entries.size,editorial_variant_journeys:editorialVariantJourneys,printed_compound_journeys:1,reciprocal_perfect_journeys:7,reciprocal_perfect_future_journeys:2,reciprocal_perfect_imperative_journeys:2,grammatical_batch_journeys:grammaticalBatchJourneys,qualified_reciprocal_perfect_journeys:1,printed_marker_journeys:1,page_continuation_journeys:1,upright_space_journeys:uprightSpaceJourneys,upright_space_absent:uprightSpaceAbsent,initial_milliseconds:initialMilliseconds,member_journeys:journeys,editorial_journeys:editorialJourneys,editorial_absent:editorialAbsent,whitespace_journeys:whitespaceJourneys,whitespace_unresolved:whitespaceUnresolved,split_anchor_journeys:1,detached_target_journeys:1,terminal_letter_journeys:1,wrapped_heading_journeys:wrappedHeadingJourneys,html_comma_journeys:htmlCommaJourneys,html_comma_uncertain:htmlCommaUncertain,member_whitespace_journeys:memberWhitespaceJourneys,member_whitespace_ambiguous:memberWhitespaceAmbiguous,tilde_journeys:tildeJourneys,tilde_absent:tildeAbsent,unresolved_dialogs:uncertain,citation_journeys:citations,unresolved_citation_dialogs:unresolvedCitations,verified_facsimiles:visitedSources.size,script_modes:scriptModes,viewports:[1440,320,390,768],browser_errors:errors.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
