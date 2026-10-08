/* Rendering only. Language, ownership and resolved targets are data facts. */
"use strict";
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
let byEntry, inspection;
function sourceLink(url,label){const a=el('a',label);if(/^https:\/\/wts-digital\.badw\.de\//.test(url||'')){a.href=url;a.rel='noreferrer';}return a;}
function bibliography(citation,entry){
 const d=el('details',undefined,'bibliography');d.append(el('summary','Bibliography'));
 for(const b of citation.bibliography){d.append(el('h3',b.label));for(const t of b.descriptions)d.append(el('p',t));if(b.edition_status==='unreviewed')d.append(el('p','Edition not independently reviewed.','note'));if(b.coverage_status==='matched_components_only_not_complete_citation')d.append(el('p','Only part of this citation has a resolved bibliographic identity.','note'));}
 entry.append(d);d.open=true;d.scrollIntoView({block:'nearest'});
}
function show(item){
 const a=document.querySelector('#article');a.replaceChildren();
 a.append(el('h2',`${item.headword.loc||''} ${item.homonym||''}`),el('p',item.headword.tibetan||'','heading-tibetan'));
 const reading=el('div',undefined,'reading');
 const citations=new Map(item.citations.map(c=>[c.component_id,c]));
 const references=new Map(item.cross_references.filter(r=>r.component_id).map(r=>[r.component_id,r]));
 for(const segment of item.segments){
  if(segment.starts_types.some(t=>['sense','source_division','lexical_parallel'].includes(t)))reading.append(el('br'));
  const citation=segment.component_ids.map(id=>citations.get(id)).find(Boolean);
  const reference=segment.component_ids.map(id=>references.get(id)).find(Boolean);
  let n=el('span',segment.text);
  if(citation){
   if(citation.bibliography.length){n=el('a',segment.text,'citation');n.href='#bibliography';n.title=citation.bibliography.map(b=>b.descriptions[0]||b.label).join('\n');n.onclick=e=>{e.preventDefault();bibliography(citation,a);};}
   else{n.classList.add('citation');n.title='Bibliographic identity unresolved';}
   if(citation.ownership==='unresolved'){n.classList.add('unresolved');n.title=(n.title||'')+' · passage association unresolved';}
  }else if(reference){
   if(reference.target_entry_id&&byEntry.has(reference.target_entry_id)){n=el('a',segment.text);n.href='#'+encodeURIComponent(reference.target_entry_id);}
   else if(reference.target_entry_id&&reference.source_url){n=sourceLink(reference.source_url,segment.text);n.title='Resolved entry outside the development subset';}
   else n.title='Cross-reference target unresolved';
  }
  for(const language of segment.languages)n.classList.add('lang-'+language);
  if(segment.languages.length>1)n.title=(n.title||'')+' · overlapping source/review language claims';
  if(segment.types.includes('lexical_parallel'))n.classList.add('lexical');
  reading.append(n);
 }
 a.append(reading);
 const reviewed=item.relationships.filter(r=>r.type==='citation_of');
 if(reviewed.length){const d=el('details');d.append(el('summary','Reviewed citation associations'));for(const r of reviewed){const from=item.components.find(c=>c.id===r.from_id);const targets=r.to_ids.map(id=>item.components.find(c=>c.id===id)?.source_form||'');d.append(el('p',`${from?.source_form||''} supports: ${targets.join(' / ')}`));}a.append(d);}
 const debug=el('details',undefined,'inspection');debug.append(el('summary','Source / debug'));
 debug.addEventListener('toggle',async()=>{if(!debug.open||debug.dataset.loaded)return;try{inspection ||= await fetch('inspection.json').then(r=>r.json());const row=inspection.entries.find(e=>e.projection.identity===item.inspection_id);debug.append(sourceLink(item.source_url,'BAdW source'),el('pre',JSON.stringify(row,null,2)));debug.dataset.loaded='yes';}catch(e){debug.append(el('p',e.message));}});
 a.append(debug);
}
function navigate(){const item=byEntry.get(decodeURIComponent(location.hash.slice(1)));if(item)show(item);}
fetch('data.json').then(r=>{if(!r.ok)throw Error('Cannot load dictionary data');return r.json();}).then(d=>{
 byEntry=new Map(d.entries.map(e=>[e.id,e]));
 const search=document.querySelector('#search'),list=document.querySelector('#entries');
 function filter(){list.replaceChildren();const q=search.value.toLowerCase();const items=d.entries.filter(e=>`${e.headword.loc||''} ${e.headword.tibetan||''}`.toLowerCase().includes(q));document.querySelector('#count').textContent=`${items.length} / ${d.entries.length} entries`;for(const e of items){const link=el('a',`${e.headword.loc} ${e.homonym||''}`);link.href='#'+encodeURIComponent(e.id);list.append(link);}}
 search.addEventListener('input',filter);window.addEventListener('hashchange',navigate);filter();navigate();
}).catch(e=>document.querySelector('#article').replaceChildren(el('p',e.message)));
