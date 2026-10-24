/* Shared browser regressions: run standalone with a synthetic catalogue, or
 * from badw_full_reader.browser.cjs against all acquired source witnesses. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {entryMatchesSearch,rankSearchResults,searchMatchRank,normalizeSearchKey}=require('../scripts/badw_dictionary_prototype/app.js');
const root=path.resolve(__dirname,'..');
async function validateSearch(browser,base,catalog){
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 const errors=[],bodies=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(/\/entries\//.test(r.url()))bodies.push(r.url());});
 const load=performance.now();await page.goto(base);await page.waitForSelector('#entries a');
 await page.waitForFunction(()=>document.querySelector('#selection-status').textContent.startsWith('Selected:'));
 const indexLoadMs=performance.now()-load;
 const ids=()=>page.locator('#entries a').evaluateAll(nodes=>nodes.map(n=>decodeURIComponent(n.hash.slice(1))));
 const fill=async q=>{await page.locator('#search').fill(q);return ids();};
 if(catalog.some(e=>e.id==='rank:0')){
  assert.deepEqual(await fill('rankprobe'),Array.from({length:8},(_,i)=>'rank:'+i));
  assert.deepEqual(await fill('ཟཟ'),['rank:tibetan-exact','rank:tibetan-prefix','rank:tibetan-boundary']);
 }
 const before=bodies.length,expected=rankSearchResults(catalog,normalizeSearchKey("'gyur"));
 assert(expected.some(e=>String(e.homonym)==='1'));
 assert.deepEqual(expected.map(e=>e.id).sort(),catalog.filter(e=>entryMatchesSearch(e,"'gyur")).map(e=>e.id).sort());
 let apostrophes;
 for(const query of ["'gyur",'’gyur','‘gyur','ʼgyur']){
  const actual=await fill(query);assert.deepEqual(actual,expected.slice(0,100).map(e=>e.id));
  if(apostrophes)assert.deepEqual(actual,apostrophes);apostrophes=actual;
 }
 // Independently specified real-catalogue examples, rather than a ranking oracle.
 if(catalog.length===29878){
  assert.equal(expected.length,61);
  assert.deepEqual(expected.slice(0,10).map(e=>[e.headword.loc,String(e.homonym||'')]),[
   ['’gyur','1'],['’gyur','2'],['’gyur bkod',''],['’gyur khug',''],
   ['’gyur ta re',''],['’gyur ldog',''],['’gyur bag mkhan',''],['’gyur byed',''],
   ['gyur ta re',''],['kun tu myoṅ bar ’gyur ba','1']]);
 }
 const tibetanQuery=expected[0].headword.tibetan;
 const tibetan=await fill(tibetanQuery);
 const exactTibetan=catalog.filter(e=>normalizeSearchKey(e.headword.tibetan)===normalizeSearchKey(tibetanQuery));
 assert.deepEqual(tibetan.slice(0,exactTibetan.length),exactTibetan.slice(0,100).map(e=>e.id));
 assert((await fill('འགྱུར')).length);
 const fallback=catalog.find(e=>e.collation_fallback);
 if(fallback){const matches=catalog.filter(e=>entryMatchesSearch(e,fallback.headword.loc));assert(matches.some(e=>e.id===fallback.id));await fill(fallback.headword.loc);let found=(await ids()).includes(fallback.id);while(!found&&await page.getByRole('button',{name:'Next results',exact:true}).count()){await page.getByRole('button',{name:'Next results',exact:true}).click();found=(await ids()).includes(fallback.id);}assert(found,'fallback witness remains discoverable');}
 const alias=catalog.find(e=>e.search_aliases?.length);assert(alias);
 assert((await fill(alias.search_aliases[0])).includes(alias.id)||catalog.filter(e=>entryMatchesSearch(e,alias.search_aliases[0])).findIndex(e=>e.id===alias.id)>=100);
 // Independent WTS ga-series expectation, not a comparison with the library.
 const ga=['གྱུར','འགྱུ','འགྱུར','རྒྱུ','སྒྱུ','བརྒྱུད','བསྒྱུར'];
 const positions=ga.map(word=>catalog.findIndex(e=>e.headword.tibetan.replace(/[་།༎]+$/u,'')===word));
 assert(positions.every(n=>n>=0));assert.deepEqual([...positions].sort((a,b)=>a-b),positions);
 const filtered=rankSearchResults(catalog,'gyu');assert(filtered.length>200);
 const collected=await fill('gyu');
 while(await page.getByRole('button',{name:'Next results',exact:true}).count()){
  await page.getByRole('button',{name:'Next results',exact:true}).click();collected.push(...await ids());
 }
 assert.deepEqual(collected,filtered.map(e=>e.id));assert.equal(new Set(collected).size,collected.length);
 assert.deepEqual([...collected].sort(),catalog.filter(e=>entryMatchesSearch(e,'gyu')).map(e=>e.id).sort());
 if(catalog.length===29878)assert.equal(collected.length,447);
 // Pure searches and pagination must never request article bodies.
 assert.equal(bodies.length,before);
 const selectedHash=await page.evaluate(()=>location.hash);
 await fill('no-such-headword-xyz');assert.equal(await page.locator('#entries a').count(),0);
 assert.equal(await page.locator('#entries [aria-current]').count(),0);
 assert((await page.locator('#entries').textContent()).includes('No matching'));
 assert.equal(await page.evaluate(()=>location.hash),selectedHash);
 assert((await page.locator('#selection-status').textContent()).startsWith('Selected:'));
 // Enter opens the highest-ranked result, while ordinary next remains global.
 await fill("'gyur");await page.locator('#search').press('Enter');
 const topHash='#'+encodeURIComponent(expected[0].id);
 await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,topHash);
 const globalNext=catalog[catalog.findIndex(e=>e.id===expected[0].id)+1];
 if(globalNext){assert.equal(await page.locator('[rel=next]').getAttribute('href'),'#'+encodeURIComponent(globalNext.id));}
 const globalPrevious=catalog[catalog.findIndex(e=>e.id===expected[0].id)-1];
 if(globalPrevious){
  const previousHash='#'+encodeURIComponent(globalPrevious.id);
  assert.equal(await page.locator('[rel=prev]').getAttribute('href'),previousHash);
  await page.locator('[rel=prev]').click();
  await page.waitForFunction(h=>location.hash===h&&document.querySelector('#selection-status').textContent.startsWith('Selected:'),previousHash);
  await page.goBack();await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,topHash);
 }
 await fill('');assert.deepEqual(await ids(),catalog.slice(0,100).map(e=>e.id));
 await page.locator('#search').focus();await page.keyboard.press('ArrowDown');
 assert(await page.locator('#entries a').first().evaluate(n=>n===document.activeElement));
 await page.keyboard.press('End');await page.keyboard.press('Enter');
 const hash99='#'+encodeURIComponent(catalog[99].id);
 await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,hash99);
 await page.locator('[rel=next]').click();
 const hash100='#'+encodeURIComponent(catalog[100].id);
 await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,hash100);
 assert.deepEqual(await ids(),catalog.slice(100,200).map(e=>e.id));
 await page.locator('[rel=prev]').click();
 await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,hash99);
 await page.goBack();await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,hash100);
 await page.goForward();await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,hash99);
 await page.goto(base+'/#'+encodeURIComponent(expected[0].id));
 await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,'#'+encodeURIComponent(expected[0].id));
 await fill("'gyur");assert.equal(await page.locator('#entries [aria-current]').count(),1);
 const timings=await page.evaluate(()=>{
  const input=document.querySelector('#search'),measure=fn=>{const t=performance.now();fn();return performance.now()-t;};
  const result={filterOnly:{}};
  for(const q of ['ka','rgyu','gyu',"'gyur"]){const key=normalizeSearchKey(q),pure=[];for(let i=0;i<10;i++)pure.push(measure(()=>rankSearchResults(orderedEntries,key)));result.filterOnly[q]=pure.reduce((a,b)=>a+b)/pure.length;const samples=[];for(let i=0;i<10;i++)samples.push(measure(()=>{input.value=q;input.dispatchEvent(new Event('input'));}));result[q]=samples.reduce((a,b)=>a+b)/samples.length;}
  input.value='gyu';input.dispatchEvent(new Event('input'));
  result.pagination=measure(()=>[...document.querySelectorAll('.entry-pager button')].find(n=>n.textContent==='Next results').click());
  result.indexResource=performance.getEntriesByType('resource').find(r=>r.name.endsWith('/data.json'))?.duration;
  return result;
 });
 for(const width of [320,390,768]){
  await page.setViewportSize({width,height:900});await fill("'gyur");
  assert((await ids()).length);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);
 }
 if(process.env.BADW_SCREENSHOTS){
  fs.mkdirSync(process.env.BADW_SCREENSHOTS,{recursive:true});
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1050});await fill("'gyur");
   await page.locator('#search').press('Enter');
   await page.waitForFunction(h=>document.querySelector('#entries [aria-current]')?.hash===h,'#'+encodeURIComponent(expected[0].id));
   await page.locator('#entries').evaluate(n=>n.scrollTop=0);await page.evaluate(()=>scrollTo(0,0));
   await page.screenshot({path:path.join(process.env.BADW_SCREENSHOTS,`relevance-${width}.png`)});
  }
 }
 assert.deepEqual(errors,[]);
 const report={entries:catalog.length,apostropheMatches:expected.length,gyuMatches:filtered.length,indexLoadMs,meanFilterAndRenderMs:timings,searchBodyRequests:0,firstTen:expected.slice(0,10).map(e=>({headword:e.headword.loc,homonym:e.homonym,category:searchMatchRank(e,normalizeSearchKey("'gyur"))+1})),browserErrors:errors.length};
 console.log(JSON.stringify({searchValidation:report}));await page.close();return report;
}
module.exports={validateSearch};
if(require.main===module)(async()=>{
 const {chromium}=require('playwright-core'),http=require('node:http'),{execFileSync}=require('node:child_process');
 const sequence=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/wts_tibetan_order.json'))).sequences;
 const words=[...new Set(sequence.flat())];
 const entries=words.map((word,i)=>({id:'fixture:'+i,headword:{loc:'gyu '+i,tibetan:word},source_kind:i%2?'html':'pdf',components:[],citations:[],relationships:[],cross_references:[],display_blocks:[],sources:[]}));
 for(let i=0;i<240;i++)entries.push({id:'duplicate:'+i,headword:{loc:'gyu '+i,tibetan:'འགྱུར'},homonym:i+1,source_kind:'pdf',components:[],citations:[],relationships:[],cross_references:[],display_blocks:[],sources:[]});
 entries.push({...entries[0],id:'apostrophe:1',headword:{loc:'’gyur',tibetan:'འགྱུར'},homonym:1,search_aliases:['‘alias','é-form']});
 const rankForms=[['rankprobe',[]],['other',['rankprobe']],['rankprobe tail',[]],['other',['rankprobe tail']],['before rankprobe',[]],['other',['before rankprobe']],['xrankprobe',[]],['other',['xrankprobe']]];
 for(let i=7;i>=0;i--)entries.push({...entries[0],id:'rank:'+i,headword:{loc:rankForms[i][0],tibetan:'ཀ'},search_aliases:rankForms[i][1]});
 for(const [id,tibetan] of [['boundary','ཀ་ཟཟ'],['prefix','ཟཟ་ཀ'],['exact','ཟཟ']])entries.push({...entries[0],id:'rank:tibetan-'+id,headword:{loc:'other',tibetan}});
 entries.push({...entries[0],id:'fallback:missing',headword:{loc:'unavailable Tibetan',tibetan:''}});
 const prepared=JSON.parse(execFileSync('node',[path.join(root,'scripts/prepare_badw_catalogue.mjs')],{input:JSON.stringify(entries)}));
 const data=JSON.stringify({entries:prepared.entries,preview:{ordering:prepared.ordering}});
 const server=http.createServer((req,res)=>{const name=req.url==='/'?'index.html':req.url.slice(1);if(name==='data.json'){res.setHeader('Content-Type','application/json');res.end(data);return;}if(!/^(index.html|app.js|style.css|fonts\/[\w.-]+)$/.test(name)){res.writeHead(404);res.end();return;}const file=path.join(root,'scripts/badw_dictionary_prototype',name);res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;try{browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});await validateSearch(browser,'http://127.0.0.1:'+server.address().port,prepared.entries);}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
