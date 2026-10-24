/* Rendering only. Language, ownership and resolved targets are data facts. */
"use strict";
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
let byEntry, orderedEntries=[], preview={}, sharded=false, navigationVersion=0;
let syncIndexSelection=()=>{};
let displayMode='both', currentEntry=null;
const loadedEntries=new Map();
function sourceLink(url,label){const a=el('a',label);if(/^https:\/\/wts-digital\.badw\.de\//.test(url||'')){a.href=url;a.rel='noreferrer';}return a;}
const relationLabels={perfect_of:'Perfect of',future_of:'Future of',imperative_of:'Imperative of'};
function headerFieldsModel(item){
 const fields=item?.semantic_hierarchy?.header_fields;
 if(!Array.isArray(fields))return {alternatives:[],relations:[],verbForms:[],grammaticalLabels:[]};
 const alternatives=fields.filter(f=>f?.header_kind==='alternate_headword'&&typeof f.form_span?.literal==='string')
  .map(f=>({literal:f.form_span.literal}));
 const relations=fields.filter(f=>f?.header_kind==='header_relation').map(f=>{
  const types=Array.isArray(f.relation_types)&&f.relation_types.length?f.relation_types:(f.relation_type?[f.relation_type]:[]);
  return {literal:typeof f.literal==='string'?f.literal:'',target:typeof f.target_span?.literal==='string'?f.target_span.literal:'',relationTypes:types.map(type=>({code:type,label:relationLabels[type]||String(type).replaceAll('_',' ')}))};
 });
 const verbForms=fields.filter(f=>f?.header_kind==='verb_form'&&typeof f.form_span?.literal==='string')
  .map(f=>({literal:typeof f.literal==='string'?f.literal:'',form:f.form_span.literal,label:typeof f.label_span?.literal==='string'?f.label_span.literal:'',labelSpan:f.label_span||null,sourceBinding:f.source_binding||null}));
 const sameSourceBinding=(a,b)=>typeof a?.identity==='string'&&a.identity.length>0&&typeof b?.identity==='string'&&b.identity.length>0&&typeof a?.text_sha256==='string'&&a.text_sha256.length>0&&typeof b?.text_sha256==='string'&&b.text_sha256.length>0&&a.identity===b.identity&&a.text_sha256===b.text_sha256;
 const grammaticalLabels=fields.filter(f=>f?.header_kind==='grammatical_label'&&typeof f.literal==='string')
  .filter(label=>!verbForms.some(form=>Number.isInteger(label.start)&&Number.isInteger(label.end)&&Number.isInteger(form.labelSpan?.start)&&Number.isInteger(form.labelSpan?.end)&&label.start===form.labelSpan.start&&label.end===form.labelSpan.end&&label.literal===form.label&&sameSourceBinding(label.source_binding,form.sourceBinding)))
  .map(f=>({literal:f.literal,sourceBinding:f.source_binding||null,start:f.start,end:f.end}));
 return {alternatives,relations,verbForms,grammaticalLabels};
}
function renderHeaderFields(item){
 const model=headerFieldsModel(item);
 if(!model.alternatives.length&&!model.relations.length&&!model.verbForms.length&&!model.grammaticalLabels.length)return null;
 const section=el('section',undefined,'header-fields');section.setAttribute('aria-label','Source-derived heading information');
 for(const form of model.alternatives){const row=el('p',undefined,'header-alternative');row.append(el('span','Alternative form: ','header-field-label'),el('span',form.literal,'header-form'));section.append(row);}
 for(const form of model.verbForms){const row=el('p',undefined,'header-verb-form');row.append(el('span','Verb form: ','header-field-label'));if(form.label)row.append(el('span',form.label,'header-grammatical-label'),el('span',' ','header-field-separator'));row.append(el('span',form.form,'header-form'));section.append(row);}
 for(const label of model.grammaticalLabels){const row=el('p',undefined,'header-grammatical-label-row');row.append(el('span','Grammatical label: ','header-field-label'),el('span',label.literal,'header-grammatical-label'));section.append(row);}
 for(const relation of model.relations){
  const row=el('div',undefined,'header-relation');
  if(relation.relationTypes.length)row.append(el('span',relation.relationTypes.map(t=>t.label).join(' · '),'header-relation-types'));
  if(relation.target)row.append(el('span',` → ${relation.target}`,'header-target'));
  row.append(el('small',`Source: ${relation.literal}`,'header-source-literal'));section.append(row);
 }
 return section;
}
// Search only: these four characters represent the transliteration apostrophe.
// NFC preserves accents and Tibetan structure; punctuation is never stripped.
function normalizeSearchKey(value){return String(value??'').normalize('NFC').toLowerCase().replace(/[‘’ʼ]/g,"'");}
const searchKeyCache=new WeakMap();
function entrySearchKeys(item){
 if(Array.isArray(item.search_keys))return item.search_keys;
 if(!searchKeyCache.has(item)){
  const aliases=item.search_aliases||headerFieldsModel(item).alternatives.map(form=>form.literal);
  searchKeyCache.set(item,[item?.headword?.loc||'',item?.headword?.tibetan||'',...aliases].map(normalizeSearchKey));
 }
 return searchKeyCache.get(item);
}
function matchesSearchKey(item,key){return entrySearchKeys(item).some(value=>value.includes(key));}
// search_keys has a fixed schema: primary LoC, primary Tibetan, then accepted
// alternatives. Preserve that distinction without changing the catalogue format.
// Categories are zero-based in priority order; Infinity means no match.
// Callers supply an already normalized query.
function searchMatchRank(item,key){
 let best=Infinity;
 const keys=entrySearchKeys(item);
 for(let i=0;i<keys.length;i++){
  const value=keys[i], offset=i<2?0:1;
  const at=value.indexOf(key);
  if(at<0)continue;
  let rank;
  if(value===key)rank=offset;
  else if(at===0)rank=2+offset;
  else {
   // LoC whitespace and Tibetan tsheg/shad delimit words or syllables.
   // Check every occurrence: an earlier embedded match can precede a boundary.
   let boundary=false;
   for(let pos=at;pos>=0;pos=value.indexOf(key,pos+1)){
    if(/[\s་༌།༎༏༐༑༔]/u.test(value[pos-1])){boundary=true;break;}
   }
   rank=(boundary?4:6)+offset;
  }
  best=Math.min(best,rank);
  if(best===0)break;
 }
 return best;
}
function rankSearchResults(entries,key){
 if(!key)return entries;
 const buckets=Array.from({length:8},()=>[]);
 for(const entry of entries){const rank=searchMatchRank(entry,key);if(rank<8)buckets[rank].push(entry);}
 return buckets.flat();
}
function entryMatchesSearch(item,query){return matchesSearchKey(item,normalizeSearchKey(query));}
function citationDetailModel(citation,entry){
 const component=entry.components.find(c=>c.id===citation.component_id);
 const related=entry.relationships.filter(r=>r.type==='citation_of'&&(r.from_id===citation.component_id||r.to_ids.includes(citation.component_id)));
 const passageIds=new Set(related.flatMap(r=>r.from_id===citation.component_id?r.to_ids:[r.from_id]));
 const passages=entry.components.filter(c=>passageIds.has(c.id)).map(c=>c.source_form);
 const bibliography=citation.bibliography||[];
 const incomplete=bibliography.some(b=>b.coverage_status==='matched_components_only_not_complete_citation_resolution');
 const status=incomplete?'partial':citation.bibliography_status||'unresolved';
 return {literal:component?.source_form||citation.source_form||'',bibliography,status,ownership:citation.ownership||'unresolved',passages};
}
function openCitationDetail(citation,entry){
 const dialog=document.querySelector('#citation-detail'),body=document.querySelector('#citation-detail-content');
 const model=citationDetailModel(citation,entry);body.replaceChildren();
 body.append(el('h2',model.literal||'Citation details','citation-detail-literal'));
 const identity=el('section',undefined,'citation-identity');identity.append(el('h3','Bibliographic identity'));
 if(model.bibliography.length){for(const b of model.bibliography){identity.append(el('h4',b.label));for(const description of b.descriptions||[])identity.append(el('p',description));
   if(b.edition_status)identity.append(el('p',`Edition status: ${b.edition_status.replaceAll('_',' ')}.`,'detail-status'));
   if(b.coverage_status==='matched_components_only_not_complete_citation_resolution')identity.append(el('p','Only matched components have an accepted identity; the full citation is not resolved.','detail-status'));
  }}else identity.append(el('p','Bibliographic identity unresolved.','detail-status'));
 body.append(identity);
 const occurrence=el('section',undefined,'citation-occurrence');occurrence.append(el('h3','Source occurrence'));
 occurrence.append(el('p',model.literal||'Source literal unavailable in this view.'));
 occurrence.append(el('p',`Identity status: ${model.status.replaceAll('_',' ')}. Passage ownership: ${model.ownership.replaceAll('_',' ')}.`,'detail-status'));
 if(model.passages.length){occurrence.append(el('h3','Source passage supported by this citation'));for(const passage of model.passages)occurrence.append(el('blockquote',passage));}
 else occurrence.append(el('p','No accepted source-passage relationship is recorded for this citation.','detail-status'));
 body.append(occurrence);
 if(entry.sources)appendSources(body,entry);
 if(!dialog.open)dialog.showModal();
}
function referenceForSegment(reference,segment){
 if(!Array.isArray(reference.target_members))return reference;
 const binding=segment.cross_reference_member;
 if(binding?.component_id!==reference.component_id)return null;
 const member=reference.target_members.find(m=>m.ordinal===binding.ordinal);
 if(!member)return null;
 return {...member,target_entry_id:member.resolution_status==='resolved'?member.target_entry_id:null,status:member.resolution_status};
}
function renderReference(reference,segment,entries){
 const target=referenceForSegment(reference,segment);
 let n=el('span',segment.text);
 if(!target)return n;
 if(target.target_entry_id&&entries.has(target.target_entry_id)){n=el('a',segment.text);n.href='#'+encodeURIComponent(target.target_entry_id);}
 else if(target.target_entry_id&&target.source_url){n=sourceLink(target.source_url,segment.text);n.title='Resolved entry outside the development subset';}
 else if(target.target_entry_id)n.title='Resolved target outside the development subset';
 else if(target.status==='resolved')n.title='Resolved lexical identity; no unique target witness';
 else n.title=target.status==='ambiguous'?'Cross-reference target ambiguous':'Cross-reference target unresolved';
 if(reference.resolution_evidence?.editorial_interpretation)n.title='Printed marker error. Reviewed interpretation: '+reference.resolution_evidence.editorial_interpretation;
 return n;
}
function referenceExplanation(target){
 if(target.target_entry_id)return 'The resolved destination is outside this collection.';
 if(target.status==='resolved')return 'The lexical identity is resolved, but there is no unique source witness to open.';
 if(target.status==='ambiguous')return 'Several possible destinations remain. No destination has been selected.';
 return 'The source wording is preserved, but no destination has passed the source-bound resolution checks.';
}
function openReferenceDetail(reference,segment,item){
 const target=referenceForSegment(reference,segment)||reference;
 const body=document.querySelector('#reference-detail-content');body.replaceChildren(el('h2',segment.text),el('p',referenceExplanation(target)));
 const reason=target.residual_reason||reference.residual_reason;
 if(reason)body.append(el('p','Recorded reason: '+reason.replaceAll('_',' '),'detail-status'));
 if(target.status==='resolved'&&target.target_lexical_entity){
  const ids=target.candidate_entry_ids||target.exact_index_candidate_ids||[];
  const choices=ids.map(id=>byEntry.get(id)).filter(Boolean);
  if(choices.length){
   body.append(el('h3','Choose a source witness'));
   for(const choice of choices){const link=el('a',entryLabel(choice)+' · '+(choice.source_kind==='html'?'Editorial HTML':'Printed PDF'));link.href='#'+encodeURIComponent(choice.id);link.addEventListener('click',()=>document.querySelector('#reference-detail').close());const row=el('p');row.append(link);body.append(row);}
  }
 }
 if(reference.target_members_status)body.append(el('p','Collection status: '+reference.target_members_status+'. Each printed target is assessed independently.','detail-status'));
 body.append(el('p','Printed reference: '+reference.wording));
 appendSources(body,item);
 document.querySelector('#reference-detail').showModal();
}
function appendSources(container,item){
 const section=el('section',undefined,'source-access');section.setAttribute('aria-label','Original sources');
 section.append(el('span','Read the source','source-label'));
 for(const source of item.sources||[{url:item.source_url,label:'BAdW source'}]){
  if(!source.url)continue;
  const link=source.url.startsWith('sources/')?el('a',source.label):sourceLink(source.url,source.label);
  if(source.url.startsWith('sources/'))link.href=source.url;
  link.target='_blank';link.rel='noopener noreferrer';section.append(link);
 }
 container.append(section);
}
// Unmapped PDF glyphs remain explicit, without exposing extraction codes in prose.
function sourceTextParts(text){
 return text.split(/(⟦UNKNOWN:[^⟧]+⟧)/u).filter(Boolean).map(literal=>({literal,unknown:literal.startsWith('⟦UNKNOWN:')}));
}
function renderSourceText(node,text,item){
 const parts=sourceTextParts(text);if(!parts.some(p=>p.unknown))return;
 node.replaceChildren();
 for(const part of parts){
  if(!part.unknown){node.append(el('span',part.literal));continue;}
  const interactive=node.tagName!=='BUTTON'&&node.tagName!=='A';
  const marker=el(interactive?'button':'span','[unread sign]','unknown-glyph');
  marker.title='An original source glyph has not been decoded. Inspect the facsimile.';
  if(interactive){marker.type='button';marker.addEventListener('click',()=>{
   const body=document.querySelector('#reference-detail-content');
   body.replaceChildren(el('h2','Unread source sign'),el('p','The source contains a glyph that has not been decoded. No reading has been supplied; consult the original facsimile.'));
   const evidence=el('details');evidence.append(el('summary','Extraction evidence'),el('code',part.literal));body.append(evidence);appendSources(body,item);
   document.querySelector('#reference-detail').showModal();
  });}
  node.append(marker);
 }
}
function entryLabel(item){return `${item.headword.loc||''}${item.homonym?' '+item.homonym:''}`;}
function displayForm(source,tibetan,mode){
 if(!tibetan)return source;
 return mode==='tibetan'?tibetan:mode==='both'?`${source} · ${tibetan}`:source;
}
function show(item){
 currentEntry=item;
 const a=document.querySelector('#article');a.replaceChildren();
 const position=orderedEntries.findIndex(e=>e.id===item.id);
 const context=el('p',`Entry ${position+1} of ${orderedEntries.length} · ${item.source_kind==='html'?'Editorial HTML witness':'Printed PDF witness'}`,'entry-context');
 a.append(context,el('h2',entryLabel(item)),el('p',item.headword.tibetan||'','heading-tibetan'));
 a.querySelector('h2').id='entry-title';a.querySelector('.heading-tibetan').lang='bo';
 if(preview.loc_experiment){
  const agreed=item.derived_headword?.tibetan;
  if(agreed){
   if(displayMode==='tibetan'){
    a.querySelector('h2').textContent=agreed+(item.homonym?' '+item.homonym:'');
    a.querySelector('h2').classList.add('tibetan');a.querySelector('h2').lang='bo';
    a.querySelector('h2').title='Source headword: '+entryLabel(item);
   }
   a.querySelector('.heading-tibetan').hidden=displayMode!=='both';
  }
  const note=el('details',undefined,'loc-note');note.append(el('summary',agreed?'Experimental script display · attested agreement':'Script conversion unavailable for this headword'));
  note.append(el('p','Conversion is a derived representation, limited to exact agreement with independently attested Tibetan forms. Unsupported forms retain their source spelling. This does not correct the published text.'));
  note.append(el('p','Source headword: '+entryLabel(item)));a.append(note);
 }
 appendSources(a,item);
 const pager=el('nav',undefined,'entry-pager');pager.setAttribute('aria-label','Previous and next entries');
 for(const [delta,label] of [[-1,'Previous'],[1,'Next']]){
  const adjacent=orderedEntries[position+delta];
  if(adjacent){const link=el('a',`${label} · ${entryLabel(adjacent)}`);link.href='#'+encodeURIComponent(adjacent.id);link.rel=delta<0?'prev':'next';pager.append(link);}
  else pager.append(el('span',label+' · end of collection','muted'));
 }
 a.append(pager);
 const header=renderHeaderFields(item);if(header)a.append(header);
 const reading=el('div',undefined,'reading');reading.lang='de';
 const citations=new Map(item.citations.map(c=>[c.component_id,c]));
 const references=new Map(item.cross_references.filter(r=>r.component_id).map(r=>[r.component_id,r]));
 for(const block of item.display_blocks){
  const paragraph=el('p',undefined,'dictionary-block '+block.kind);
  for(const segment of block.segments){
   const citation=segment.component_ids.map(id=>citations.get(id)).find(Boolean);
   const reference=segment.component_ids.map(id=>references.get(id)).find(Boolean);
   let n=el('span',segment.text);
   if(citation){
    n=el('button',segment.text,'citation');n.type='button';
    const labels=citation.bibliography.map(b=>b.label);
    n.title=labels.length?labels.join(' · '):'Bibliographic identity unresolved';
    n.setAttribute('aria-label',`${segment.text}. Open citation details.`);
    n.addEventListener('click',()=>openCitationDetail(citation,item));
   }else if(reference){
    n=renderReference(reference,segment,byEntry);
    const target=referenceForSegment(reference,segment);
    if(target&&n.tagName!=='A'){
     n=el('button',segment.text,'uncertain-reference');n.type='button';
     n.title=referenceExplanation(target);n.setAttribute('aria-label',segment.text+'. '+n.title+' Open reference details.');
     n.addEventListener('click',()=>openReferenceDetail(reference,segment,item));
    }
   }
   const languages=segment.effective_languages||segment.languages||[];
   for(const language of languages)n.classList.add('lang-'+language);
   if(/[\u0f00-\u0fff]/u.test(segment.text)){n.classList.add('tibetan');n.lang='bo';}
   if(languages.length>1)n.title=(n.title||'')+' · overlapping source/review language claims';
   if(segment.types.includes('lexical_parallel')||(segment.semantic_item_ids||[]).length)n.classList.add('lexical');
   renderSourceText(n,segment.text,item);
   if(preview.loc_experiment&&segment.derived_tibetan&&displayMode!=='loc'){
    n.textContent=displayForm(segment.text,segment.derived_tibetan,displayMode);
    n.title=(n.title?n.title+' · ':'')+'Source transliteration: '+segment.text;
    n.classList.add('tibetan');
    if(displayMode==='tibetan')n.lang='bo';
   }
   paragraph.append(n);
  }
  reading.append(paragraph);
 }
 a.append(reading);
 const corrections=item.cross_references.filter(r=>r.resolution_evidence?.editorial_interpretation);
 if(corrections.length){
  const note=el('aside',undefined,'reference-note editorial-interpretation');note.append(el('h3','Editorial interpretation'));
  for(const ref of corrections){
   note.append(el('p',`The source prints “${ref.marker||''}${ref.wording}”. The arrow precedes the grammatical abbreviation. Reviewed interpretation: ${ref.resolution_evidence.editorial_interpretation}. The printed text is preserved; the link follows this separately recorded interpretation.`));
  }
  a.append(note);
 }
 const plurals=item.cross_references.filter(r=>Array.isArray(r.target_members));
 if(plurals.length){
  const note=el('aside',undefined,'reference-note');note.append(el('h3','Cross-reference coverage'));
  for(const ref of plurals){const resolved=ref.target_members.filter(m=>m.resolution_status==='resolved').length;
   note.append(el('p',`${ref.wording} — ${resolved} of ${ref.target_members.length} targets resolved (${ref.target_members_status}). The plural parent remains unresolved; use the individual targets in the text.`));}
  a.append(note);
 }
 const provenance=el('details',undefined,'provenance');provenance.append(el('summary','About this source witness'));
 provenance.append(el('p','This reading preserves its source witness. Editorial HTML and printed PDF evidence are separate layers; unresolved structure and citation ownership remain provisional.'));
 provenance.append(el('p','Source identity: '+item.inspection_id));
 for(const source of item.sources||[]){provenance.append(el('p','SHA-256: '+source.sha256));if(source.original_url)provenance.append(sourceLink(source.original_url,'Original BAdW PDF'));}
 a.append(provenance);
 document.title=entryLabel(item)+' · WTS reader';
 document.querySelector('#selection-status').textContent='Selected: '+entryLabel(item);
 syncIndexSelection(item.id);
 for(const link of document.querySelectorAll('#entries a')){if(link.hash==='#'+encodeURIComponent(item.id))link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
 const active=document.querySelector('#entries [aria-current]'),list=document.querySelector('#entries');
 if(active&&(active.offsetTop<list.scrollTop+list.offsetTop||active.offsetTop+active.offsetHeight>list.scrollTop+list.offsetTop+list.clientHeight))list.scrollTop=active.offsetTop-list.offsetTop;
}
async function navigate(focus=false){
 const version=++navigationVersion;
 let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{ id=null; }
 if(!location.hash&&orderedEntries.length){id=orderedEntries[0].id;history.replaceState(null,'','#'+encodeURIComponent(id));}
 let item=byEntry.get(id);
 if(item){
  try{
   if(sharded){
    if(!loadedEntries.has(id)){
     document.querySelector('#article').replaceChildren(el('p','Loading source witness…'));
     const response=await fetch(item.path);if(!response.ok)throw Error('Entry file unavailable');
     const bytes=await response.arrayBuffer();
     const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
     if(hash!==item.sha256)throw Error('Entry integrity check failed');
     const full=JSON.parse(new TextDecoder().decode(bytes));if(full.id!==id)throw Error('Entry identity mismatch');
     loadedEntries.set(id,full);if(loadedEntries.size>24)loadedEntries.delete(loadedEntries.keys().next().value);
    }
    item=loadedEntries.get(id);
   }
   if(version!==navigationVersion)return;
   show(item);
  }catch(error){if(version!==navigationVersion)return;document.querySelector('#selection-status').textContent='Entry unavailable';for(const link of document.querySelectorAll('#entries a'))link.removeAttribute('aria-current');document.querySelector('#article').replaceChildren(el('h2','Entry could not be loaded'),el('p',error.message+'. Reload to retry.'));}
 }
 else {const a=document.querySelector('#article');a.replaceChildren(el('h2','Entry unavailable'),el('p','This address is not part of this collection. Choose an entry from the index.'));document.querySelector('#selection-status').textContent='No entry selected';for(const link of document.querySelectorAll('#entries a'))link.removeAttribute('aria-current');}
 if(focus){const heading=document.querySelector('#article h2');heading.tabIndex=-1;heading.focus({preventScroll:true});heading.scrollIntoView({block:'start'});}
}
if(typeof document!=='undefined'&&typeof fetch==='function'){
 document.querySelector('.skip-link')?.addEventListener('click',event=>{event.preventDefault();const article=document.querySelector('#article');article.tabIndex=-1;article.focus();});
 for(const kind of ['citation','reference'])document.querySelector('#'+kind+'-dialog-close')?.addEventListener('click',()=>document.querySelector('#'+kind+'-detail').close());
 fetch('data.json').then(r=>{if(!r.ok)throw Error('Cannot load dictionary data');return r.json();}).then(d=>{
 orderedEntries=d.entries;preview=d.preview||{};sharded=!!d.sharded;byEntry=new Map(d.entries.map(e=>[e.id,e]));
 const modeControl=document.querySelector('#script-mode');
 if(modeControl&&preview.loc_experiment){
  modeControl.closest('.script-setting').hidden=false;
  modeControl.addEventListener('change',()=>{displayMode=modeControl.value;if(currentEntry)show(currentEntry);});
 }
 document.querySelector('#scope').textContent=`${d.entries.length.toLocaleString('en')} source witnesses · ${sharded?'complete acquired corpus':'limited demonstration collection'}`;
 if(sharded)document.querySelector('.collection-guide > p').textContent=preview.scope+' Links with a dotted underline explain uncertainty; citations open bibliographic details. Source witnesses are available beside each heading.';
 document.querySelector('#ordering').textContent=preview.ordering||'Catalogue order, then homonym and source identity.';
 const examples=document.querySelector('#suggestions');for(const e of preview.suggested_entries||[]){const a=el('a',typeof e.label==='string'?e.label:e.label.loc);a.href='#'+encodeURIComponent(e.id);examples.append(a);}
 const search=document.querySelector('#search'),list=document.querySelector('#entries');
 let page=0,items=d.entries;const pageSize=100;
 const pages=el('div',undefined,'entry-pager');list.after(pages);
 function filter(reset=true){if(reset){page=0;const key=normalizeSearchKey(search.value);items=rankSearchResults(d.entries,key);}list.replaceChildren();pages.replaceChildren();document.querySelector('#count').textContent=`${items.length} of ${d.entries.length} entries · ${items.length? page*pageSize+1:0}–${Math.min((page+1)*pageSize,items.length)} shown`;for(const e of items.slice(page*pageSize,(page+1)*pageSize)){const link=el('a',entryLabel(e));link.href='#'+encodeURIComponent(e.id);const tibetan=el('span',e.headword.tibetan||'','index-tibetan');tibetan.lang='bo';link.append(tibetan,el('small',e.source_kind==='html'?'Editorial':'Print','index-witness'));if(link.hash===location.hash)link.setAttribute('aria-current','page');list.append(link);}if(!items.length)list.append(el('p','No matching headword. Try a shorter LoC or Tibetan form.'));for(const [delta,label] of [[-1,'Previous results'],[1,'Next results']]){if(page+delta<0||(page+delta)*pageSize>=items.length)continue;const button=el('button',label);button.type='button';button.addEventListener('click',()=>{page+=delta;filter(false);list.querySelector('a')?.focus();});pages.append(button);}}
 syncIndexSelection=id=>{const selectedPage=Math.floor(items.findIndex(e=>e.id===id)/pageSize);if(selectedPage>=0&&selectedPage!==page){page=selectedPage;filter(false);}};
 search.addEventListener('input',filter);
 let composing=false;
 search.addEventListener('compositionstart',()=>{composing=true;});
 search.addEventListener('compositionend',()=>{composing=false;});
 search.addEventListener('keydown',event=>{
  // Some input methods omit isComposing on their confirmation keydown.
  if(event.isComposing||composing||event.keyCode===229)return;
  if(event.key==='ArrowDown'){event.preventDefault();list.querySelector('a')?.focus();}
  else if(event.key==='Enter'&&items.length){
   event.preventDefault();const destination='#'+encodeURIComponent(items[0].id);
   if(location.hash===destination)navigate(true);else location.hash=destination;
  }
 });
 list.addEventListener('keydown',event=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;const links=[...list.querySelectorAll('a')];const i=links.indexOf(document.activeElement);const next=event.key==='Home'?0:event.key==='End'?links.length-1:i+(event.key==='ArrowDown'?1:-1);if(links[next]){event.preventDefault();links[next].focus();}});
 window.addEventListener('hashchange',()=>navigate(true));filter();navigate();
 }).catch(e=>document.querySelector('#article').replaceChildren(el('p','The reader could not load: '+e.message+'. Serve this directory over HTTP using the documented preview command.')));
}
if(typeof module!=='undefined')module.exports={searchMatchRank,rankSearchResults,normalizeSearchKey,entrySearchKeys,matchesSearchKey,citationDetailModel,openCitationDetail,headerFieldsModel,renderHeaderFields,entryMatchesSearch,referenceForSegment,renderReference,referenceExplanation,sourceTextParts,displayForm};
