const test=require('node:test');
const assert=require('node:assert/strict');
const {citationDetailModel,openCitationDetail}=require('../scripts/badw_dictionary_prototype/app.js');
const sample=require('../scripts/badw_dictionary_prototype/data.json');

class Node {
 constructor(tag='node'){this.tag=tag;this.children=[];this.textContent='';this.attrs={};this.className='';this.open=false;this.classList={add:()=>{}};}
 append(...nodes){this.children.push(...nodes)}
 replaceChildren(...nodes){this.children=[...nodes]}
 setAttribute(k,v){this.attrs[k]=v}
 addEventListener(){}
 showModal(){this.open=true;this.openCount=(this.openCount||0)+1}
}
function findEntry(prefix){return sample.entries.find(e=>e.headword.loc===prefix)}

test('curated sample retains HTML/PDF, unresolved citations, examples, xrefs and source relationships',()=>{
 assert.equal(sample.entries.length,5);
 assert(sample.entries.some(e=>e.id.startsWith('badw:entry:')));
 assert(sample.entries.some(e=>e.id.startsWith('badw:pdf:')));
 assert(sample.entries.some(e=>e.citations.some(c=>!c.bibliography.length)));
 assert(sample.entries.some(e=>e.display_blocks.some(b=>b.kind==='example')));
 assert(sample.entries.some(e=>e.cross_references.length));
 assert(findEntry('chos ’khor').relationships.some(r=>r.type==='citation_of'));
});

test('detail model keeps occurrence, accepted authorities and passage relation distinct',()=>{
 const entry=findEntry('chos ’khor');
 const relation=entry.relationships.find(r=>r.type==='citation_of');
 const citation=entry.citations.find(c=>c.component_id===relation.from_id);
 const model=citationDetailModel(citation,entry);
 assert.equal(model.literal,entry.components.find(c=>c.id===citation.component_id).source_form);
 assert(model.passages.length>0);
 assert(model.passages.some(p=>p.includes('chos kyi ’khor lo')));
 assert(citation.bibliography.length>0);
 assert.equal(citation.ownership,'reviewed');
});

test('unresolved and partial bibliography statuses remain explicit',()=>{
 const entry=findEntry('bkri');
 const partial=entry.citations.find(c=>c.bibliography.length>1);
 const model=citationDetailModel(partial,entry);
 assert.equal(model.bibliography.length,2);
 assert(model.bibliography.every(b=>b.coverage_status==='matched_components_only_not_complete_citation_resolution'));
 const unresolved=entry.citations.find(c=>!c.bibliography.length);
 const unresolvedModel=citationDetailModel(unresolved,entry);
 assert.equal(unresolvedModel.status,'unresolved');
 assert.equal(unresolvedModel.bibliography.length,0);
});

test('opening successive citation details replaces one reusable view',()=>{
 const dialog=new Node('dialog'),body=new Node('div');
 global.document={createElement:tag=>new Node(tag),querySelector:s=>s==='#citation-detail'?dialog:body};
 const entry=findEntry('bkri');
 openCitationDetail(entry.citations[0],entry);
 const first=body.children;
 openCitationDetail(entry.citations[1],entry);
 assert.equal(dialog.openCount,1);
 assert.notEqual(body.children,first);
 assert.equal(body.children.filter(n=>n.tag==='section').length,2);
 assert.equal(body.children.filter(n=>n.tag==='h2').length,1);
 delete global.document;
});

test('reader presentation does not mutate source citation or passage strings',()=>{
 const entry=findEntry('bkri');
 const before=JSON.stringify({citations:entry.citations,components:entry.components,relationships:entry.relationships});
 for(const c of entry.citations)citationDetailModel(c,entry);
 assert.equal(JSON.stringify({citations:entry.citations,components:entry.components,relationships:entry.relationships}),before);
});
