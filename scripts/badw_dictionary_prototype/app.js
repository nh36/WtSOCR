/* View only: no extraction, normalization or inferred association. */
"use strict";
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
let data, byEntry;
function details(title,value){const d=el('details');d.append(el('summary',title),el('pre',JSON.stringify(value,null,2)));return d;}
function show(item){
 const a=document.querySelector('#article');a.replaceChildren();
 const p=item.projection, entry=item.entry, nodes=p.nodes, byNode=new Map(nodes.map(n=>[n.id,n]));
 a.append(el('h2',`${entry.headword.loc||''} ${entry.homonym||''}`),el('p',entry.headword.tibetan||''));
 a.append(el('p',`${p.source_kind.toUpperCase()} · ${p.identity}`,'label'));
 const literal=el('details');literal.append(el('summary','Complete literal source reading'),el('div',item.review_text,'literal'));a.append(literal);
 const children=new Map();for(const n of nodes){const parent=n.parent||'';if(!children.has(parent))children.set(parent,[]);children.get(parent).push(n);}
 function render(n,ancestors){
  if(ancestors.has(n.id))return el('p','Invalid cyclic parent graph');
  const box=el('section',undefined,`component ${n.kind}`);box.id=n.id;
  box.append(el('div',`${n.kind} · ${n.id} · [${n.start}, ${n.end})`,'label'));
  const sourceText=Array.from(item.review_text).slice(n.start,n.end).join('');
  if((children.get(n.id)||[]).length&&['source_division','sense'].includes(n.kind)){const full=el('details');full.append(el('summary','Literal enclosing passage'),el('div',sourceText,'literal'));box.append(full);}
  else box.append(el('div',sourceText));
  const relations=(p.edges||[]).filter(e=>e.from===n.id||e.to===n.id);
  for(const e of relations){const target=el('a',`Candidate ${e.kind}: ${e.from} → ${e.to}`,'badge');target.href=`#${encodeURIComponent(p.identity)}`;target.onclick=event=>{event.preventDefault();document.getElementById(e.to)?.scrollIntoView();};box.append(target);}
  const reviewed=(p.semantic_relationships||[]).filter(r=>r.from?.node_id===n.id);
  for(const claim of reviewed){for(const t of claim.to||[]){const phrase=Array.from(item.review_text).slice(t.start,t.end).join('');box.append(el('p',`${claim.relation} (reviewed): “${phrase}”`,'reviewed'));}box.append(details('Relationship review and exact source evidence',claim));}
  if(n.kind==='citation'&&!reviewed.some(r=>r.relation==='citation_of')){box.append(el('span','Citation ownership not reviewed (candidate edges and containment are not accepted ownership)','badge unresolved'));}
  const next=new Set(ancestors);next.add(n.id);for(const child of children.get(n.id)||[])box.append(render(child,next));
  box.append(details('Exact component evidence',n));return box;
 }
 a.append(el('h3','Extracted source structure'));
 for(const n of children.get('')||[])a.append(render(n,new Set()));
 a.append(el('h3','Reviewed annotations and passage relationships'));
 for(const claim of [...(p.semantic_annotations||[]),...(p.citable_passages||[]),...(p.semantic_relationships||[])]){if(claim.kind==='language_span'){a.append(el('p',`Reviewed language ${claim.claim.language}: ${(claim.ranges||[]).map(r=>r.literal).join(' / ')} (source tags retained unchanged)`,'reviewed'));}a.append(details(`${claim.kind||claim.relation||'Reviewed claim'} · ${claim.status||'see review'}`,claim));}
 if(!(p.semantic_relationships||[]).length)a.append(el('p','No reviewed semantic relationship overlay for this entry.','label'));
 a.append(el('h3','Dictionary references'));
 for(const r of item.cross_references){const row=el('p',`${r.marker||''} ${r.target_label||''} `),resolution=r.canonical_resolution;
  if(resolution?.status==='resolved'){const target=byEntry.get(resolution.target_entry_id);if(target){const link=el('a','Open linked entry');link.href='#'+encodeURIComponent(target.projection.identity);row.append(link);}else{row.append(el('span','Resolved entry is outside this frozen subset','badge'));}}
  else row.append(el('span',resolution?.status||'unresolved','badge unresolved'));
  if(r.target_url){const link=el('a',' BAdW source');if(/^https:\/\/wts-digital\.badw\.de\//.test(r.target_url)){link.href=r.target_url;link.rel='noreferrer';row.append(link);}}
  row.append(details('Literal reference and resolution provenance',r));a.append(row);
 }
 a.append(details('Full immutable projection, source locations and review provenance',p));
}
function navigate(){const id=decodeURIComponent(location.hash.slice(1));const item=data.entries.find(e=>e.projection.identity===id);if(item)show(item);}
fetch('data.json').then(r=>{if(!r.ok)throw Error('Cannot load frozen data');return r.json();}).then(d=>{
 data=d;byEntry=new Map(d.entries.map(e=>[e.entry.id,e]));
 const search=document.querySelector('#search'), list=document.querySelector('#entries');
 function filter(){list.replaceChildren();const q=search.value.toLowerCase();const items=d.entries.filter(e=>`${e.entry.headword.loc||''} ${e.entry.headword.tibetan||''}`.toLowerCase().includes(q));document.querySelector('#count').textContent=`${items.length} / ${d.entries.length} entries`;for(const e of items){const link=el('a',`${e.entry.headword.loc} ${e.entry.homonym||''}`);link.href='#'+encodeURIComponent(e.projection.identity);list.append(link);}}
 search.addEventListener('input',filter);window.addEventListener('hashchange',navigate);filter();navigate();
}).catch(e=>document.querySelector('#article').replaceChildren(el('p',e.message)));
