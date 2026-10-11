"""Offline corpus structural diagnostics; candidates are not scholarly gold.

Replay immutable acquired HTML and verified PDF visual witnesses. Broad source
and sense containers never count as lexical accounting. Full projections/source
stay in ignored work; checked-in findings retain hashes and exact coordinates.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, re, sqlite3
from pathlib import Path
from build_badw_structural_review_packet import rows
from badw_article_parser import parse_database_article
from extract_badw_lexical_records import extract_article
from parse_badw_pdf_articles import reindex_article
from extract_badw_pdf_lexical_candidates import extract
from build_badw_pdf_nested_candidates import project as nested_project
from project_badw_structural_candidates import project, project_html
from resolve_badw_cross_references import EntryIndex
from badw_dictionary_entry_view import entry_view
from badw_bibliography import AuthorityResolver

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'badw-corpus-structural-health-v1'
DEFAULT_HTML = 'work/badw_stage_c13_20260928/parsed/database_articles.jsonl'
DEFAULT_PDF = 'work/badw_verified_rebuild_20261003/structure_replay_v2/pdf_article_structure.jsonl.gz'
DEFAULT_INDEX = 'work/badw_relationship_targets_20261005/actual_entry_index.jsonl'
DEFAULT_BIB = 'work/wts_apparatus_20261010/ingested_completed/bibliography.sqlite'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n')

def intervals(mask):
    runs=[]
    for i, yes in enumerate(mask):
        if yes:
            if runs and runs[-1][1]==i: runs[-1][1]=i+1
            else: runs.append([i,i+1])
    return runs

def accounting(text, nodes):
    cover=bytearray(len(text))
    for n in nodes:
        if n['kind'] not in {'sense','source_division'}:
            cover[n['start']:n['end']]=b'\1'*(n['end']-n['start'])
    gaps=intervals([not x for x in cover])
    lexical=[(a,b) for a,b in gaps if any(c.isalpha() for c in text[a:b])]
    return gaps,lexical,sum(c.isalpha() and not cover[i] for i,c in enumerate(text))

def packet(article,kind):
    text = article['article_source_text'] if kind=='html' else '\n'.join(l['text'] for l in article['visual_lines'])
    source = {k:article[k] for k in (('source_object','article_source_text','dom_full_text') if kind=='html' else ('source_objects','visual_lines','source_faithful_text'))}
    return dict(identity=article['source_identifier'] if kind=='html' else article['article_id'],source_kind=kind,source=source,group='corpus',stratum='corpus',split='diagnostic',review_text=text,review_text_sha256=digest(text.encode()))

# Indicators generate review candidates. They do not assert OCR corrections,
# wrong language, publication identity, or semantic ownership.
FAMILIES = {
 'pipeline_exception': ('parser','critical','Replay stage raises; source retained; isolate general failure'),
 'lexical_gap': ('parser','high','Alphabetic source outside every non-container component; delimit omitted clauses'),
 'definition_contains_later_structure': ('parser','high','Definition contains quote/Lex./later numbering; inspect boundary grammar'),
 'citation_owner_unresolved': ('model','high','Candidate containment/proximity is not reviewed ownership; express exact citable passages'),
 'citation_identity_unresolved': ('scholarly/source','medium','No accepted apparatus component; retain candidate/edition ambiguity'),
 'lex_clause_untyped': ('parser/model','high','Lex. marker has no following lexical_parallel component before next marker'),
 'language_evidence_untyped': ('parser/model','high','Explicit Sanskrit cue lacks nearby Sanskrit component; use contextual evidence'),
 'language_conflict': ('model','high','Contradictory Tibetan/Sanskrit component intervals'),
 'xref_unresolved': ('parser/source','medium','Exact URL absent or printed target not reviewed; no fuzzy linking'),
 'xref_component_missing': ('reader','medium','Reader reference has no source component despite retained reference'),
 'reader_integrity': ('reader','critical','Source/structure/accepted bibliography lost in projection'),
 'sense_numbering': ('parser/source','high','Repeated/non-monotonic Arabic labels; inspect source hierarchy'),
 'empty_component': ('parser','high','Component has whitespace only'),
 'crossing_components': ('parser/model','high','Non-container intervals cross instead of nesting'),
 'long_component': ('parser/model','medium','Definition >1200 or language span >400 characters; review envelope'),
 'ignored_citation_cue': ('parser','high','Author-year or numeric parenthesis outside extracted citation'),
 'ambiguous_reference_marker': ('source/parser','medium','Arrow outside cross-reference node; target extent needs evidence'),
 'pdf_unassigned_candidate': ('model/parser','high','Nested/adapted extraction leaves candidate explicitly unassigned'),
}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--html',default=DEFAULT_HTML,type=Path);ap.add_argument('--pdf',default=DEFAULT_PDF,type=Path)
    ap.add_argument('--index',default=DEFAULT_INDEX,type=Path);ap.add_argument('--bibliography',default=DEFAULT_BIB,type=Path)
    ap.add_argument('--cache',default='work/badw_source_cache',type=Path)
    ap.add_argument('--canonical',default='work/badw_verified_rebuild_20261003/canonical_v2',type=Path)
    ap.add_argument('--work',default='work/badw_corpus_structure',type=Path)
    ap.add_argument('--output',default='data/badw_corpus_structure',type=Path)
    args=ap.parse_args();args.work.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True)
    index=EntryIndex(rows(args.index)); by_identity={}
    for e in index.records.values():
        # Index IDs and witness source identities are separate entities.
        for span in e.get('source_spans',[]):
            if span.get('source_id'): by_identity[span['source_id']]=e
    db=sqlite3.connect(args.bibliography.resolve().as_uri()+'?mode=ro',uri=True)
    authorities=[json.loads(r[0]) for r in db.execute('select record_json from authority')]
    bibrows=[json.loads(r[0]) for r in db.execute('select record_json from occurrence')];db.close()
    resolver=AuthorityResolver(authorities,bibrows)
    refs_review={}
    replay=Path('work/badw_relationship_targets_20261005/cross_reference_replay.jsonl')
    if replay.exists():
        for r in rows(replay):
            ref=r['record'];review=ref.get('canonical_resolution',{}).get('target_review')
            if review:refs_review[ref['id']]=review
    # Exclude all prior review packets, golds, predictions and untouched holdouts.
    exclusion_paths=sorted(p for p in Path('work').glob('badw_*/*') if p.is_file() and p.parent!=args.work and p.suffix=='.jsonl' and any(w in p.name for w in ('packet','review','gold','holdout','challenge')))
    exclusion_paths += [Path('data/reviewed_badw_semantic_annotations.jsonl')]
    excluded=set()
    for path in exclusion_paths:
        for r in rows(path):
            for key in ('identity','article_id','source_article_id'):
                if isinstance(r.get(key),str):excluded.add(r[key])
    verified=set();counts=collections.Counter(); family_counts=collections.defaultdict(collections.Counter)
    family_entries=collections.defaultdict(set); examples=collections.defaultdict(list); metrics=[]; holdout_pools=collections.defaultdict(list)
    raw=(args.work/'projections.jsonl').open('w'); an=(args.work/'anomalies.jsonl').open('w')
    def emit(family,p,spans=(),details=None):
        counts['anomaly_occurrences']+=1;family_counts[family][p['source_kind']]+=1;family_entries[family].add(p['identity'])
        r=dict(family=family,identity=p['identity'],source_kind=p['source_kind'],text_sha256=p['review_text_sha256'],spans=list(spans),details=details)
        an.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
        if len(examples[family])<6: examples[family].append(r)
    for kind,path in [('html',args.html),('pdf',args.pdf)]:
        for i,original in enumerate(rows(path)):
            counts[kind+'_entries']+=1;p=packet(original,kind);text=p['review_text'];phase='source_verification'
            try:
                if kind=='html':
                    obj=original['source_object'];body=(args.cache/obj['object_path']).read_bytes()
                    if digest(body)!=obj['sha256']:raise ValueError('HTML hash mismatch')
                    article=parse_database_article(body,source_metadata=dict(obj,delivery_type='database_article',valid_resource=True))
                    if article['article_source_text']!=text:raise ValueError('HTML visible source changed')
                    phase='lexical_extraction';records=extract_article(article,snapshot_id='corpus-structural-health',extraction_run_id=VERSION)
                    phase='canonical_projection';pred=project_html(p,records,article)
                    entry=next(r for r in records if r['record_type']=='entry');references=[r for r in records if r['record_type']=='cross_reference']
                else:
                    for obj in original['source_objects']:
                        for target,sha in [(args.cache/'objects/sha256'/obj['pdf_sha256'][:2]/obj['pdf_sha256'],obj['pdf_sha256']), (args.canonical/obj['canonical_object'],obj['canonical_object_sha256'])]:
                            if str(target) not in verified:
                                if file_hash(target)!=sha:raise ValueError('PDF/canonical object hash mismatch: '+str(target))
                                verified.add(str(target))
                    phase='pdf_structure';article=reindex_article(original)
                    phase='lexical_extraction';lexical=extract(article)
                    phase='nested_model';nested=nested_project(article,lexical)
                    phase='canonical_projection';pred=project(p,nested,article)
                    # Keep actual entry identity; no invented headword target.
                    entry=by_identity.get(p['identity']) or dict(id=p['identity'],headword={'loc':article['loc_headword'],'tibetan':article.get('tibetan_headword')},homonym=article.get('homonym'))
                    references=[]
                    for j,c in enumerate(article['candidates'].get('cross_references',[])):
                        references.append(dict(record_type='cross_reference',id=p['identity']+':xref:'+str(j),marker=c.get('marker'),target_label=c.get('target_label_candidate',''),source_candidate=c,source_spans=[c]))
                nodes=pred['nodes'];citations=[n for n in nodes if n['kind']=='citation'];bibliography={};accepted=0
                phase='bibliography'
                for n in citations:
                    a,b=n['start'],n['end'];evidence=[]
                    if kind=='html':
                        for sig in article['sigla']:
                            loc=sig['locator'];s,e=loc['visible_text_start'],loc['visible_text_end']
                            if a<=s<e<=b:evidence.append(dict(start=s-a,end=e-a,label=text[s:e],expansion=sig['expanded_display_text']))
                    result=resolver.resolve_dom(text[a:b],evidence) if evidence else resolver.resolve(text[a:b],kind)
                    ids=sorted({aid for m in result['matches'] if m.get('target_status')=='accepted_identity' for aid in m['authority_ids']})
                    if ids:accepted+=1;bibliography[(p['identity'],n['id'])]=[resolver.by_id[x] for x in ids]
                    else:emit('citation_identity_unresolved',p,[[a,b]],dict(status=result['status']))
                resolved_refs=[];refstats=collections.Counter()
                for r in references:
                    rr=(index.resolve_source_candidate(r) if kind=='pdf' and r['id'] not in refs_review else index.resolve(r,reviewed_target=refs_review.get(r['id'])));resolved_refs.append(rr);status=rr['canonical_resolution']['status'];refstats[status]+=1
                    if status!='resolved':
                        candidates=sorted(index.labels.get(r.get('target_label',''),set()))
                        reason=('explicit_url_absent_from_acquired_index' if r.get('target_url') else 'printed_target_requires_review')
                        emit('xref_unresolved',p,details=dict(status=status,reason=reason,target=r.get('target_label'),exact_label_candidates=candidates))
                phase='reader';view=entry_view(dict(projection=pred,entry=entry,review_text=text,cross_references=resolved_refs),bibliography)
                if ''.join(s['text'] for s in view['segments'])!=text or len(view['citations'])!=len(citations) or sum(bool(c['bibliography']) for c in view['citations'])!=accepted or len(view['components'])!=len(nodes):emit('reader_integrity',p)
                for r in view['cross_references']:
                    if not r['component_id']:emit('xref_component_missing',p,details=dict(wording=r['wording']))
                gaps,lexgaps,unassigned=accounting(text,nodes)
                for a,b in lexgaps:emit('lexical_gap',p,[[a,b]],dict(alphabetic_characters=sum(c.isalpha() for c in text[a:b])))
                senses=[n for n in nodes if n['kind']=='sense'];defs=[n for n in nodes if n['kind']=='definition'];langs=[n for n in nodes if n['kind'] in ('tibetan','sanskrit')];lexnodes=[n for n in nodes if n['kind']=='lexical_parallel']
                for n in nodes:
                    a,b=n['start'],n['end'];literal=text[a:b]
                    if not literal.strip():emit('empty_component',p,[[a,b]],dict(kind=n['kind']))
                    if (n['kind']=='definition' and b-a>1200) or (n['kind'] in ('tibetan','sanskrit') and b-a>400):emit('long_component',p,[[a,b]],dict(kind=n['kind']))
                    if n['kind']=='definition' and re.search(r'Lex\.|„|(?:\n|\s)[2-9]\)',literal):emit('definition_contains_later_structure',p,[[a,b]])
                leaf=[n for n in nodes if n['kind'] not in ('source_division','sense')]
                for j,n in enumerate(leaf):
                    for m in leaf[j+1:]:
                        if n['start']<m['start']<n['end']<m['end'] or m['start']<n['start']<m['end']<n['end']:emit('crossing_components',p,[[n['start'],n['end']],[m['start'],m['end']]],dict(kinds=[n['kind'],m['kind']]))
                for j,n in enumerate(langs):
                    for m in langs[j+1:]:
                        if n['kind']!=m['kind'] and max(n['start'],m['start'])<min(n['end'],m['end']):emit('language_conflict',p,[[n['start'],n['end']],[m['start'],m['end']]])
                markers=list(re.finditer(r'\bLex\.',text))
                for j,m in enumerate(markers):
                    end=markers[j+1].start() if j+1<len(markers) else len(text)
                    if not any(m.start()<=n['start']<end for n in lexnodes):emit('lex_clause_untyped',p,[[m.start(),m.end()]])
                for m in re.finditer(r'\bskt\.',text):
                    if not any(m.end()<=n['start']<m.end()+100 and n['kind']=='sanskrit' for n in langs):emit('language_evidence_untyped',p,[[m.start(),min(len(text),m.end()+100)]])
                for m in re.finditer(r'\([^()\n]{0,90}\d[^()\n]{0,90}\)|\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+\s+(?:18|19|20)\d{2}[a-z]?',text):
                    if not any(n['start']<=m.start()<m.end()<=n['end'] for n in citations):emit('ignored_citation_cue',p,[[m.start(),m.end()]])
                for m in re.finditer('[↑↓→]',text):
                    if not any(n['kind']=='cross_reference' and n['start']<=m.start()<n['end'] for n in nodes):emit('ambiguous_reference_marker',p,[[m.start(),m.end()]])
                labels=[]
                for d in article.get('divisions',[]):
                    label=str(d.get('number',d.get('label','')))
                    if label.rstrip(').').isdigit():labels.append(int(label.rstrip(').')))
                if labels and any(a>=b for a,b in zip(labels,labels[1:])):emit('sense_numbering',p,details=dict(labels=labels))
                for n in citations:emit('citation_owner_unresolved',p,[[n['start'],n['end']]],dict(candidate_edges=sum(e.get('relation',e.get('type'))=='citation_of' for e in pred['edges'])))
                if kind=='pdf':
                    for u in pred.get('unassigned_source_candidates',[]):emit('pdf_unassigned_candidate',p,details=dict(kind=u.get('kind',u.get('type','candidate'))))
                stat=dict(identity=p['identity'],source_kind=kind,text_sha256=p['review_text_sha256'],characters=len(text),alphabetic_characters=sum(c.isalpha() for c in text),unassigned_characters=sum(b-a for a,b in gaps),unassigned_alphabetic=unassigned,lexical_gap_runs=len(lexgaps),nodes=len(nodes),senses=len(senses),definitions=len(defs),citations=len(citations),accepted_identity_citations=accepted,reviewed_owner_citations=0,lexical_parallels=len(lexnodes),language_spans=len(langs),cross_references=len(references),resolved_xrefs=refstats['resolved'],unresolved_xrefs=refstats['unresolved'],ambiguous_xrefs=refstats['ambiguous'])
                metrics.append(stat);counts[kind+'_parsed']+=1
                raw.write(json.dumps(dict(packet=p,projection=pred,entry=entry,reader=view,metrics=stat),ensure_ascii=False)+'\n')
                if p['identity'] not in excluded:
                    strata=['simple'] if len(text)<200 else []
                    if senses and len(senses)>=4:strata.append('many_sense')
                    if markers:strata.append('lex')
                    if any(n['kind']=='sanskrit' for n in langs) or 'skt.' in text:strata.append('sanskrit')
                    if len(citations)>=5:strata.append('citation')
                    if references:strata.append('xref')
                    if re.search(r'\b(?:vb\.|Verb|pf\.|imp\.)',text):strata.append('verb')
                    if kind=='pdf' and str(article.get('volume')) in ('3','4','volume_3','volume_4'):strata.append('later_volume')
                    for s in strata:holdout_pools[kind+':'+s].append((digest((VERSION+p['identity']).encode()),stat))
            except Exception as e:
                counts[kind+'_failures']+=1;emit('pipeline_exception',p,details=dict(phase=phase,error=type(e).__name__+': '+str(e)))
            if (i+1)%1000==0:print(kind,i+1,dict(counts),flush=True)
    raw.close();an.close()
    with (args.output/'entries.tsv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(metrics[0]),delimiter='\t');writer.writeheader();writer.writerows(metrics)
    summary=dict(version=VERSION,counts=dict(counts),totals={k:sum(r[k] for r in metrics) for k in metrics[0] if isinstance(metrics[0][k],int)},source_kinds={kind:{k:sum(r[k] for r in metrics if r['source_kind']==kind) for k in metrics[0] if isinstance(metrics[0][k],int)} for kind in ('html','pdf')},limitations=['Graph validity is not independently reviewed scholarly accuracy.','All new citation owners remain unresolved: candidate edges are not promoted. Existing bounded review overlays are counted separately, not extrapolated.','PDF visual witnesses are replayed; no new PDF decoding/OCR or lexical-page census.','Language/citation/swallowing heuristics flag candidates; source ambiguity is not a parser defect.'])
    write_json(args.output/'summary.json',summary)
    rank=[]
    for family,distribution in family_counts.items():
        layer,severity,action=FAMILIES[family];rank.append(dict(family=family,entries=len(family_entries[family]),occurrences=sum(distribution.values()),distribution=dict(distribution),layer=layer,severity=severity,recommended_action=action,examples=examples[family]))
    rank.sort(key=lambda r:({'critical':0,'high':1,'medium':2}[r['severity']],-r['entries'],r['family']))
    write_json(args.output/'families.json',rank)
    holdout=[];chosen=set()
    for stratum,pool in sorted(holdout_pools.items()):
        selected=0
        for _,stat in sorted(pool):
            if stat['identity'] in chosen:continue
            holdout.append(dict(stratum=stratum,metrics=stat,review_status='source_review_pending',accuracy_status='not_gold'));chosen.add(stat['identity']);selected+=1
            if selected==3:break
    write_json(args.output/'holdout.json',dict(seed=VERSION,excluded_identities=len(excluded),cases=holdout))
    inputs=[args.html,args.pdf,args.index,args.bibliography,Path('data/source_pdfs.tsv'),replay,*exclusion_paths]
    code=sorted(Path('scripts').glob('*badw*.py'))+[Path('scripts/benchmark_badw_structure.py')]
    manifest=dict(version=VERSION,input_sha256={str(p):file_hash(p) for p in inputs if p.exists()},code_sha256={str(p):file_hash(p) for p in code},verified_pdf_objects=len(verified),actual_entry_index_sha256=index.sha256,source_scope=dict(html=str(args.html),pdf=str(args.pdf)),outputs_sha256={str(p):file_hash(p) for p in sorted(args.output.glob('*')) if p.name!='manifest.json'},raw_projection_sha256=file_hash(args.work/'projections.jsonl'))
    write_json(args.output/'manifest.json',manifest);print(json.dumps(summary,sort_keys=True))

if __name__=='__main__':main()
