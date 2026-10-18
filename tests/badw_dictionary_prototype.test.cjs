const test=require('node:test');
const assert=require('node:assert/strict');
const {citationDetailModel,openCitationDetail,headerFieldsModel,renderHeaderFields,entryMatchesSearch}=require('../scripts/badw_dictionary_prototype/app.js');

// Small synthetic presentation fixture. Source-bearing development exports
// are generated locally under ignored work/ and are never test dependencies.
const sample={entries:[
 {id:'html:chos-khor',headword:{loc:'chos ’khor',tibetan:'ཆོས་འཁོར'},homonym:'',
  components:[{id:'c1',source_form:'(SOURCE 1985: 139)'},{id:'p1',source_form:'chos kyi ’khor lo'}],
  citations:[{component_id:'c1',bibliography:[{id:'auth1',label:'SOURCE',descriptions:['Collected essays, 1985.'],coverage_status:'complete',edition_status:'reviewed'}],bibliography_status:'accepted',ownership:'reviewed'}],
  relationships:[{type:'citation_of',from_id:'c1',to_ids:['p1']}],
  display_blocks:[{kind:'definition',segments:[{text:'wheel of doctrine',component_ids:[],types:[],languages:[]}]}],cross_references:[]},
 {id:'html:bkri',headword:{loc:'bkri',tibetan:'བཀྲི'},homonym:'',
  components:[{id:'c2',source_form:'(A 2001; B 2003)'},{id:'c3',source_form:'(UNKNOWN 2010)'},{id:'p2',source_form:'a source passage'}],
  citations:[{component_id:'c2',bibliography:[{id:'auth2',label:'A',descriptions:['A publication'],coverage_status:'matched_components_only_not_complete_citation_resolution',edition_status:'unreviewed'},{id:'auth3',label:'B',descriptions:['B publication'],coverage_status:'matched_components_only_not_complete_citation_resolution',edition_status:'unreviewed'}],bibliography_status:'partial',ownership:'reviewed'},
   {component_id:'c3',bibliography:[],bibliography_status:'unresolved',ownership:'unresolved'}],
  relationships:[],display_blocks:[{kind:'definition',segments:[{text:'to turn',component_ids:['c2'],types:[],languages:[]}]}],cross_references:[]},
 {id:'pdf:sample',headword:{loc:'example',tibetan:'དཔེ'},homonym:'',components:[],citations:[],relationships:[],
  display_blocks:[{kind:'example',segments:[{text:'Tibetan example — German translation',component_ids:[],types:[],languages:[]}]}],
  cross_references:[{component_id:'x1',target_entry_id:'html:chos-khor'}]}
]};

const headerEntries=[
 {id:'html:blon-che',headword:{loc:'blon che',tibetan:'བློན་ཆེ'},semantic_hierarchy:{header_fields:[
  ...['blon ce','blon po che','blon po che ba'].map((literal,i)=>({header_kind:'alternate_headword',form_span:{literal,span:{start:i*10,end:i*10+literal.length}}}))
 ]},display_blocks:[{kind:'definition',segments:[{text:'blon ce is also mentioned in prose',component_ids:[],types:[],languages:[]}]}]},
 {id:'html:bskrad',headword:{loc:'bskrad',tibetan:'བསྐྲད'},semantic_hierarchy:{header_fields:[
  {header_kind:'header_relation',literal:'pf. bzw. fut. zu ↑skrod',relation_type:'perfect_of',relation_types:['perfect_of','future_of'],target_span:{literal:'skrod',span:{start:76,end:81}}}
 ]}},
 {id:'html:blugs',headword:{loc:'blugs',tibetan:'བླུགས'},semantic_hierarchy:{header_fields:[
  {header_kind:'header_relation',literal:'pf. und imp. zu ↑blug',relation_type:'perfect_of',relation_types:['perfect_of','imperative_of'],target_span:{literal:'blug',span:{start:74,end:78}}}
 ]}},
 {id:'html:single',headword:{loc:'single',tibetan:'གཅིག'},semantic_hierarchy:{header_fields:[
  {header_kind:'header_relation',literal:'imp. zu ↑blug',relation_type:'imperative_of',target_span:{literal:'blug'}}
 ]}},
 {id:'html:empty',headword:{loc:'empty',tibetan:'དབེན'},semantic_hierarchy:{header_fields:[]},display_blocks:[{kind:'definition',segments:[{text:'blon po che ba',component_ids:[],types:[],languages:[]}]}]},
 {id:'html:no-header',headword:{loc:'plain',tibetan:'དཔེ'},display_blocks:[{kind:'definition',segments:[{text:'blon po che',component_ids:[],types:[],languages:[]}]}]}
];

class Node {
 constructor(tag='node'){this.tag=tag;this.children=[];this.textContent='';this.attrs={};this.className='';this.open=false;this.classList={add:()=>{}};}
 append(...nodes){this.children.push(...nodes)}
 replaceChildren(...nodes){this.children=[...nodes]}
 setAttribute(k,v){this.attrs[k]=v}
 addEventListener(){}
 showModal(){this.open=true;this.openCount=(this.openCount||0)+1}
}
function findEntry(prefix){return sample.entries.find(e=>e.headword.loc===prefix)}

test('presentation fixture covers HTML/PDF, unresolved citations, examples and xrefs',()=>{
 assert.equal(sample.entries.length,3);
 assert(sample.entries.some(e=>e.id.startsWith('html:')));
 assert(sample.entries.some(e=>e.id.startsWith('pdf:')));
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

test('accepted alternate headwords display exact forms and search returns their primary entry',()=>{
 const entry=headerEntries[0],before=JSON.stringify(entry.semantic_hierarchy.header_fields);
 const model=headerFieldsModel(entry);
 assert.deepEqual(model.alternatives.map(x=>x.literal),['blon ce','blon po che','blon po che ba']);
 for(const form of model.alternatives)assert.equal(entryMatchesSearch(entry,form.literal),true);
 assert.equal(entryMatchesSearch(entry,'blon che'),true);
 assert.deepEqual(headerEntries.filter(candidate=>entryMatchesSearch(candidate,'blon po che ba')).map(candidate=>candidate.id),['html:blon-che']);
 assert.deepEqual(model.relations,[]);
 assert.equal(JSON.stringify(entry.semantic_hierarchy.header_fields),before);
});

test('grouped grammatical relations remain one source construction with every type and exact target',()=>{
 for(const [entry,types,target] of [
  [headerEntries[1],['Perfect of','Future of'],'skrod'],
  [headerEntries[2],['Perfect of','Imperative of'],'blug']
 ]){
  const before=JSON.stringify(entry.semantic_hierarchy.header_fields);
  global.document={createElement:tag=>new Node(tag)};
  const section=renderHeaderFields(entry);
  assert.equal(section.tag,'section');
  assert.equal(section.children.filter(n=>n.className==='header-relation').length,1);
  const row=section.children[0];
  assert.equal(row.children.find(n=>n.className==='header-relation-types').textContent,types.join(' · '));
  assert.equal(row.children.find(n=>n.className==='header-target').textContent,` → ${target}`);
  assert.equal(row.children.find(n=>n.className==='header-source-literal').textContent,`Source: ${entry.semantic_hierarchy.header_fields[0].literal}`);
  assert.equal(row.children.some(n=>n.tag==='a'),false);
  assert.equal(entryMatchesSearch(headerEntries[0],target),false);
  assert.equal(JSON.stringify(entry.semantic_hierarchy.header_fields),before);
 }
 delete global.document;
});

test('singular relations render once and empty or missing header fields are harmless',()=>{
 global.document={createElement:tag=>new Node(tag)};
 const single=renderHeaderFields(headerEntries[3]);
 assert.equal(single.children.length,1);
 assert.equal(single.children[0].children.filter(n=>n.className==='header-relation-types').length,1);
 assert.equal(single.children[0].children.find(n=>n.className==='header-relation-types').textContent,'Imperative of');
 assert.deepEqual(headerFieldsModel(headerEntries[4]),{alternatives:[],relations:[]});
 assert.equal(renderHeaderFields(headerEntries[4]),null);
 assert.equal(renderHeaderFields(headerEntries[5]),null);
 assert.equal(entryMatchesSearch(headerEntries[4],'empty'),true);
 delete global.document;
});

test('definition prose and unresolved candidate forms do not become searchable aliases',()=>{
 const entry=headerEntries[0];
 entry.semantic_hierarchy.header_fields.push({header_kind:'candidate_headword',form_span:{literal:'not an alias'}});
 assert.equal(entryMatchesSearch(entry,'blon ce'),true);
 assert.equal(entryMatchesSearch(entry,'not an alias'),false);
 assert.equal(entryMatchesSearch(headerEntries[4],'blon po che ba'),false);
 assert.equal(entryMatchesSearch(headerEntries[5],'blon po che'),false);
});
