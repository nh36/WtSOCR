/* Rendering only. Language, ownership and resolved targets are data facts. */
"use strict";
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
let byEntry, inspection;
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
 const sameSourceBinding=(a,b)=>!a||!b||(a.identity===b.identity&&a.text_sha256===b.text_sha256);
 const grammaticalLabels=fields.filter(f=>f?.header_kind==='grammatical_label'&&typeof f.literal==='string')
  .filter(label=>!verbForms.some(form=>form.labelSpan&&label.start===form.labelSpan.start&&label.end===form.labelSpan.end&&label.literal===form.label&&sameSourceBinding(label.source_binding,form.sourceBinding)))
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
function entryMatchesSearch(item,query){
 const q=String(query||'').toLowerCase();
 const primary=`${item?.headword?.loc||''} ${item?.headword?.tibetan||''}`;
 const aliases=headerFieldsModel(item).alternatives.map(form=>form.literal);
 return [primary,...aliases].some(value=>value.toLowerCase().includes(q));
}
function citationDetailModel(citation,entry){
 const component=entry.components.find(c=>c.id===citation.component_id);
 const related=entry.relationships.filter(r=>r.type==='citation_of'&&(r.from_id===citation.component_id||r.to_ids.includes(citation.component_id)));
 const passageIds=new Set(related.flatMap(r=>r.from_id===citation.component_id?r.to_ids:[r.from_id]));
 const passages=entry.components.filter(c=>passageIds.has(c.id)).map(c=>c.source_form);
 return {literal:component?.source_form||citation.source_form||'',bibliography:citation.bibliography||[],status:citation.bibliography_status||'unresolved',ownership:citation.ownership||'unresolved',passages};
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
 if(!dialog.open)dialog.showModal();
}
function show(item){
 const a=document.querySelector('#article');a.replaceChildren();
 a.append(el('h2',`${item.headword.loc||''} ${item.homonym||''}`),el('p',item.headword.tibetan||'','heading-tibetan'));
 const header=renderHeaderFields(item);if(header)a.append(header);
 const reading=el('div',undefined,'reading');
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
    const labels=citation.bibliography.map(b=>`${b.label}: ${b.descriptions?.[0]||'bibliographic record'}`);
    n.title=labels.length?labels.join(' · '):'Bibliographic identity unresolved';
    n.setAttribute('aria-label',`${segment.text}. ${labels.length?labels.join('; '):'Bibliographic identity unresolved'}. Open citation details.`);
    n.addEventListener('click',()=>openCitationDetail(citation,item));
   }else if(reference){
    if(reference.target_entry_id&&byEntry.has(reference.target_entry_id)){n=el('a',segment.text);n.href='#'+encodeURIComponent(reference.target_entry_id);}
    else if(reference.target_entry_id&&reference.source_url){n=sourceLink(reference.source_url,segment.text);n.title='Resolved entry outside the development subset';}
    else if(reference.target_entry_id)n.title='Resolved target outside the development subset';
    else n.title='Cross-reference target unresolved';
   }
   for(const language of (segment.effective_languages||segment.languages))n.classList.add('lang-'+language);
   if((segment.effective_languages||segment.languages).length>1)n.title=(n.title||'')+' · overlapping source/review language claims';
   if(segment.types.includes('lexical_parallel')||(segment.semantic_item_ids||[]).length)n.classList.add('lexical');
   paragraph.append(n);
  }
  reading.append(paragraph);
 }
 a.append(reading);
 const reviewed=item.relationships.filter(r=>r.type==='citation_of');
 const debug=el('details',undefined,'inspection');debug.append(el('summary','Source / debug'));
 if(reviewed.length){const d=el('details');d.append(el('summary','Reviewed citation associations'));for(const r of reviewed){const from=item.components.find(c=>c.id===r.from_id);const targets=r.to_ids.map(id=>item.components.find(c=>c.id===id)?.source_form||'');d.append(el('p',`${from?.source_form||''} supports: ${targets.join(' / ')}`));}debug.append(d);}
 debug.addEventListener('toggle',async()=>{if(!debug.open||debug.dataset.loaded)return;try{inspection ||= await fetch('inspection.json').then(r=>r.json());const row=inspection.entries.find(e=>e.projection.identity===item.inspection_id);debug.append(sourceLink(item.source_url,'BAdW source'),el('pre',JSON.stringify(row,null,2)));debug.dataset.loaded='yes';}catch(e){debug.append(el('p',e.message));}});
 a.append(debug);
}
function navigate(){const item=byEntry.get(decodeURIComponent(location.hash.slice(1)));if(item)show(item);}
if(typeof document!=='undefined'&&typeof fetch==='function'){
 document.querySelector('#citation-dialog-close')?.addEventListener('click',()=>document.querySelector('#citation-detail').close());
 fetch('data.json').then(r=>{if(!r.ok)throw Error('Cannot load dictionary data');return r.json();}).then(d=>{
 byEntry=new Map(d.entries.map(e=>[e.id,e]));
 const search=document.querySelector('#search'),list=document.querySelector('#entries');
 function filter(){list.replaceChildren();const q=search.value;const items=d.entries.filter(e=>entryMatchesSearch(e,q));document.querySelector('#count').textContent=`${items.length} / ${d.entries.length} entries`;for(const e of items){const link=el('a',`${e.headword.loc} ${e.homonym||''}`);link.href='#'+encodeURIComponent(e.id);list.append(link);}}
 search.addEventListener('input',filter);window.addEventListener('hashchange',navigate);filter();navigate();
 }).catch(e=>document.querySelector('#article').replaceChildren(el('p',e.message)));
}
if(typeof module!=='undefined')module.exports={citationDetailModel,openCitationDetail,headerFieldsModel,renderHeaderFields,entryMatchesSearch};
