"""Complete corpus diagnostics with existing reviewed relationships and identities.

Offline only. Exact physical occurrence bridges preserve reviewed bibliography
links; no nearest-owner or fuzzy-target assertion is made. This second streaming
pass can be rerun without replaying the entire extractor.
"""
import collections, csv, gzip, json, re, sqlite3
from pathlib import Path
from audit_badw_corpus_structure import (FAMILIES, VERSION, rows, file_hash, write_json, accounting)
from badw_reader_bibliography import pdf_occurrence_bridge
from badw_dictionary_entry_view import entry_view
from badw_semantic_store import create, ingest
from badw_semantic_annotations import validate, apply_validated_annotations, PACKET_VERSION
from resolve_badw_cross_references import EntryIndex
from badw_bibliography import AuthorityResolver
from badw_bibliography_aliases import load_reviews
from badw_semantic_hierarchy import VERSION as SEMANTIC_VERSION

OUT=Path('data/badw_corpus_structure'); WORK=Path('work/badw_corpus_structure')
BIB=Path('work/wts_apparatus_20261010/ingested_completed')
CACHE=Path('work/badw_source_cache'); CANON=Path('work/badw_verified_rebuild_20261003/canonical_v2')
STAGING=Path('work/badw_verified_rebuild_20261003/staging.sqlite')
INDEX=Path('work/badw_relationship_targets_20261005/actual_entry_index.jsonl')

def prior_review_exclusions():
    paths=sorted(p for root in Path('work').glob('badw_*') if root.is_dir() and root!=WORK
                 for p in root.rglob('*') if p.is_file() and p.suffix in ('.jsonl','.tsv','.json')
                 and any(s in p.name for s in ('packet','gold','holdout','challenge','reviewed','review')))
    paths+=sorted(Path('data').glob('*badw*review*.tsv'))+[Path('data/reviewed_badw_semantic_annotations.jsonl')]
    # Development candidates are reviewed evidence, even when stored as a JSON
    # array in this run's work directory. Never sample them as fresh validation.
    paths+=sorted(WORK.glob('*review*.json'))
    excluded={'badw:https://wts-digital.badw.de/lemma/ka%20chen/1', 'badw:https://wts-digital.badw.de/lemma/kos%20s%C3%B1u%E1%B9%85/1'}; valid=[]
    for p in paths:
        try:
            if p.suffix=='.json':
                payload=json.loads(p.read_text())
                iterator=payload if isinstance(payload,list) else payload.get('cases',[])
                if not isinstance(iterator,list):iterator=[]
            else:
                iterator=rows(p) if p.suffix=='.jsonl' else csv.DictReader(p.open(),delimiter='\t')
            for r in iterator:
                if not isinstance(r,dict):continue
                for record in [r]+[r[k] for k in ('packet','projection','metrics') if isinstance(r.get(k),dict)]:
                    for k in ('identity','article_id','source_article_id'):
                        if isinstance(record.get(k),str):excluded.add(record[k])
            valid.append(p)
        except (ValueError,KeyError):
            raise ValueError('unreadable previous-review artifact: '+str(p))
    return excluded,valid

def main():
    global OUT, WORK
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--contextual-semantics', action='store_true', help='Derive exact inline citations with the registered bibliography grammar')
    parser.add_argument('--baseline-store', type=Path)
    parser.add_argument('--baseline-commit', help='Commit of the supplied frozen baseline store')
    parser.add_argument('--holdout-manifest', type=Path, help='Replay a previously selected source-review sample without resampling')
    parser.add_argument('--citation-reviews', type=Path, help='Exact source-bound scholarly identity reviews; unmatched occurrences only')
    args = parser.parse_args()
    OUT, WORK = args.output, args.work
    frozen_sample=json.loads(args.holdout_manifest.read_text()) if args.holdout_manifest else None
    frozen_ids={c['metrics']['identity'] for c in frozen_sample['cases']} if frozen_sample else set()
    baseline_path=args.baseline_store or (Path('work/badw_semantic_hierarchy/semantic.sqlite') if WORK.name=='badw_relationship_closure' else None)
    baseline_store=sqlite3.connect('file:'+str(baseline_path)+'?mode=ro',uri=True) if baseline_path else None
    contextual_records=[];contextual_counts=collections.Counter()
    frozen_residue=collections.defaultdict(list)
    if args.contextual_semantics:
        for a in rows(Path('work/badw_contextual_semantics/residue_packets.jsonl')):
            frozen_residue[a['packet']['identity']]=a['residue']
    store=create(WORK/'semantic.sqlite')
    index=EntryIndex(rows(INDEX)); db=sqlite3.connect(BIB/'bibliography.sqlite')
    authorities=[json.loads(x[0]) for x in db.execute('select record_json from authority')]
    print_rows=[dict(id=r[0], occurrence_id=r[1], source_sha256=r[2], label=r[3]['authority']['label']) for r in ((a, o, h, json.loads(j)) for a,o,h,j in db.execute('select authority_id,id,pdf_sha256,record_json from print_occurrence where authority_id is not null')) if r[3].get('authority')];db.close()
    source_rows=list(rows(BIB/'source_rows.jsonl'))
    from badw_bibliography_external import load_publications
    from badw_bibliography_citation_reviews import CitationReviews
    external=load_publications(Path('data/bibliography_external_publications.tsv'),CACHE)
    existing={r['id'] for r in authorities}
    authorities.extend(r for r in external if r['id'] not in existing)
    existing_occ={r['occurrence_id'] for r in source_rows}
    source_rows.extend(r for r in external if r['occurrence_id'] not in existing_occ)
    citation_reviews=CitationReviews(args.citation_reviews,source_rows,CACHE,Path('data/source_pdfs.tsv'))
    aliases=load_reviews(Path('data/bibliography_alias_reviews.tsv'),source_rows,Path('data/source_pdfs.tsv'),CACHE)
    resolver=AuthorityResolver(authorities,source_rows,aliases,print_rows)
    links={r['citation_id']:r['resolution'] for r in rows(BIB/'citation_links.jsonl')}
    annotations=list(rows(Path('data/reviewed_badw_semantic_annotations.jsonl')))
    grouped=collections.defaultdict(list)
    for a in annotations:grouped[a['identity']].append(a)
    oldrefs=collections.defaultdict(list)
    for r in rows(Path('work/badw_relationship_targets_20261005/cross_reference_replay.jsonl')):
        if r['source_kind']=='pdf':oldrefs[r['identity']].append(r['record'])
    excluded,exclusion_paths=prior_review_exclusions(); pools=collections.defaultdict(list)
    metrics=[]; extra=[]; counts=collections.Counter(); overlay=[]; bib_bridge=collections.Counter(); xref_reasons=collections.Counter(); holdout_candidates={}
    residue=[]; residue_counts=collections.Counter(); evidence_counts=collections.Counter()
    for i,r in enumerate(rows(WORK/'projections.jsonl')):
        p=r['packet'];p['contract_version']=PACKET_VERSION;pred=r['projection'];text=p['review_text'];kind=p['source_kind'];identity=p['identity'];stat=r['metrics'];nodes=pred['nodes']
        if identity in grouped:
            try:
                validated=validate([p],grouped[identity],cache=CACHE,canonical_root=CANON)
                pred=apply_validated_annotations(p,pred,validated);nodes=pred['nodes']
                overlay.append(dict(identity=identity,status='applied',annotations=len(validated),relationships=len(pred['semantic_relationships'])))
            except ValueError as e:
                overlay.append(dict(identity=identity,status='source_or_endpoint_conflict',reason=str(e)))
        from badw_pdf_structure_recovery import recover
        pred=recover(pred,text);nodes=pred['nodes']
        bridge={}
        if kind=='pdf':
            bridge,diagnostics=pdf_occurrence_bridge([{**pred,'source':p['source']}],STAGING)
            bib_bridge.update(d['status'] for d in diagnostics)
        baseline_citations={json.loads(row[0])['component_id']:json.loads(row[0]) for row in baseline_store.execute('SELECT record_json FROM citation WHERE entry=?',(identity,))} if baseline_store else {}
        baseline_by_span={(c['source_span']['start'],c['source_span']['end']):c for c in baseline_citations.values()}
        additions=[]
        if args.contextual_semantics:
            from badw_contextual_semantics import augment_citations
            pred,additions=augment_citations(pred,text,resolver);nodes=pred['nodes']
        bibliography={};accepted=0;known_residual=0
        for n in nodes:
            if n['kind']!='citation':continue
            literal=text[n['start']:n['end']]
            old=links.get(n.get('lexical_record_id')) if kind=='html' else links.get(bridge.get((identity,n['id'])))
            # Legacy occurrence literal must agree; DOM baseline is retained.
            if old and old['text']!=literal:
                counts['legacy_literal_mismatch']+=1;old=None
            ids=set()
            # Node order is the reader contract; offsets distinguish equal literals.
            ci=[x for x in pred['nodes'] if x['kind']=='citation'].index(n)
            original=[x for x in r['projection']['nodes'] if x['kind']=='citation']
            baseline=r['reader']['citations'][ci] if ci<len(original) and original[ci]['start']==n['start'] and original[ci]['end']==n['end'] else None
            if baseline:ids.update(baseline['accepted_authority_ids'])
            prior=baseline_by_span.get((n['start'],n['end']))
            if prior:ids.update(prior['accepted_authority_ids'])
            result=old or resolver.resolve(literal,kind)
            result=citation_reviews.apply_source(kind,identity,text,n['start'],n['end'],result)
            resolver.component_contract(result)
            ids.update(aid for m in result['matches'] if m.get('target_status')=='accepted_identity' for aid in m['authority_ids'])
            if ids:accepted+=1;bibliography[(identity,n['id'])]=[resolver.by_id[a] for a in sorted(ids)]
            else:known_residual+=1
        refs=[]
        if kind=='html':
            # Already exactly resolved against the same pinned entry index.
            refs=[x for x in pred.get('original_records',[]) if x.get('record_type')=='cross_reference']
            refs=[index.resolve_manifestation(x) for x in refs]
        else:
            for j,c in enumerate(pred['original_structure']['candidates']['cross_references']):
                label=c.get('target_label_candidate',''); ref=dict(marker=c.get('marker'),target_label=label,source_candidate=c)
                reviewed=None
                for old in oldrefs[identity]:
                    ss=old['source_spans']; review=old['canonical_resolution'].get('target_review')
                    if review and all(s['source_sha256']==p['review_text_sha256'] and text[s['start']:s['end']]==old['target_label'] for s in ss) and old['target_label']==label and sum(o['target_label']==label for o in oldrefs[identity])==1 and sum(ca.get('target_label_candidate')==label for ca in pred['original_structure']['candidates']['cross_references'])==1:
                        base={k:v for k,v in old.items() if k!='canonical_resolution'}
                        reviewed=index.resolve(base,reviewed_target=review);break
                if reviewed:ref=dict(reviewed, source_candidate=c)
                else:ref=index.resolve_source_candidate(ref, structure=pred['original_structure'], text=text)
                refs.append(ref)
        resolved=sum(x.get('canonical_resolution',{}).get('status')=='resolved' for x in refs)
        for ref in refs:
            if ref.get('canonical_resolution',{}).get('status')=='resolved':continue
            label=ref.get('target_label',''); candidates=sorted(index.labels.get(label,set()))
            reason=ref.get('canonical_resolution',{}).get('residual_reason') or ('explicit_url_absent_from_acquired_index' if ref.get('target_url') else 'exact_label_unique_requires_span_review' if len(candidates)==1 else 'exact_label_ambiguous' if candidates else 'no_exact_label_in_acquired_index')
            xref_reasons[kind+':'+reason]+=1
            extra.append(dict(family='xref_unresolved',identity=identity,source_kind=kind,text_sha256=p['review_text_sha256'],spans=[],details=dict(reason=reason,target=label,exact_label_candidates=candidates)))
        view=entry_view(dict(projection=pred,entry=r['entry'],review_text=text,cross_references=refs),bibliography)
        if len(r['reader']['citations'])+len(additions) != len(view['citations']) or len(r['reader']['cross_references']) != len(view['cross_references']):
            raise ValueError('relationship occurrence count changed: '+identity)
        new_by_id={c['component_id']:c for c in view['citations']}
        for raw_old in r['reader']['citations']:
            new=new_by_id[raw_old['component_id']]
            old=baseline_citations.get(raw_old['component_id'],raw_old)
            if old['ownership'] != 'unresolved':
                if new['ownership'] == 'unresolved' or old['supports'] != new['supports'] or old.get('sense_node_id') != new.get('sense_node_id'):
                    raise ValueError('accepted citation ownership changed: '+identity)
                counts['baseline_citation_owners_preserved']+=1

            if old['ownership'] != 'unresolved':continue
            family=new['source_structural_family']
            residue_counts['citation:'+kind+':'+family]+=1
            residue.append(dict(kind='citation',identity=identity,source_kind=kind,
                text_sha256=p['review_text_sha256'],component_id=new['component_id'],
                source_span=new['source_span'],family=family,after=new['ownership'],
                evidence=new.get('ownership_evidence_class'),reason=new.get('ownership_residual_reason')))
        for old, new in zip(r['reader']['cross_references'], view['cross_references']):
            if old['status']=='resolved':
                if new['status'] != 'resolved' or (old.get('target_entry_id') and old['target_entry_id'] not in new['candidate_entry_ids']):
                    raise ValueError('accepted cross-reference changed: '+identity)
                counts['baseline_resolved_xrefs_preserved']+=1
                continue
            parsed=new.get('parsed_target') or {}
            family=('ambiguous_exact_label' if old['candidate_entry_ids'] else
                    parsed.get('shape') or ('linked_HTML_target' if new.get('source_url') else 'unlinked_HTML_target'))
            residue_counts['xref:'+kind+':'+family]+=1
            residue.append(dict(kind='xref',identity=identity,source_kind=kind,
                text_sha256=p['review_text_sha256'],component_id=new['component_id'],
                source_span=new['source_span'],literal=new['wording'],family=family,
                original_candidates=old['candidate_entry_ids'],after=new['status'],
                parsed_target=parsed,reason=new.get('residual_reason'),
                candidate_entry_ids=new['candidate_entry_ids']))
        for citation in view['citations']:
            evidence_counts[kind+':'+citation.get('ownership_evidence_class','unresolved')]+=1
        if args.contextual_semantics:
            from badw_contextual_semantics import classify_residue
            classified=classify_residue(pred,text,view,frozen_residue.get(identity,[]),additions,baseline_by_span)
            contextual_records.extend(classified)
            for rec in classified:
                contextual_counts[rec['baseline_family']+':'+kind+':'+rec['classification']]+=1
                if rec['baseline_family'] in ('language_evidence_untyped','ignored_citation_cue') and rec['outcome']=='unresolved':
                    extra.append(dict(family=rec['baseline_family'],identity=identity,source_kind=kind,text_sha256=rec['text_sha256'],spans=rec['source_spans'],details=dict(classification=rec['classification'],literal=rec['literal'])))
        ingest(store,view)
        owner=sum(c['ownership']!='unresolved' for c in view['citations'])
        counts['reader_checked']+=1;counts['reader_integrity_failures']+=int(''.join(s['text'] for s in view['segments'])!=text or len(view['citations'])!=sum(n['kind']=='citation' for n in nodes) or sum(bool(c['accepted_authority_ids']) for c in view['citations'])!=accepted)
        counts['accepted_identity_reader_loss']+=sum(set(c['accepted_authority_ids'])!={a['id'] for a in bibliography.get((identity,n['id']),[])} for n,c in zip((n for n in nodes if n['kind']=='citation'),view['citations']))
        for n,c in zip((n for n in nodes if n['kind']=='citation'),view['citations']):
            f=None
            if c['ownership']=='unresolved':f='citation_owner_unresolved'
            if f:extra.append(dict(family=f,identity=identity,source_kind=kind,text_sha256=p['review_text_sha256'],spans=[[n['start'],n['end']]],details=dict(accepted_identity=bool(c['accepted_authority_ids']),candidate_containment_not_ownership=True)))
            if not c['accepted_authority_ids']:extra.append(dict(family='citation_identity_unresolved',identity=identity,source_kind=kind,text_sha256=p['review_text_sha256'],spans=[[n['start'],n['end']]],details=dict(bridge='unbridged_or_unresolved')))
        for ref in view['cross_references']:
            if not ref['component_id']:extra.append(dict(family='xref_component_missing',identity=identity,source_kind=kind,text_sha256=p['review_text_sha256'],spans=[],details=dict(wording=ref['wording'])))
        stat.update(citations=len(view['citations']),accepted_identity_citations=accepted,reviewed_owner_citations=sum(c["ownership"]=="reviewed" for c in view["citations"]),resolved_xrefs=resolved,unresolved_xrefs=len(refs)-resolved)
        semantic=view['semantic_hierarchy']
        stat.update(lex_blocks=len(semantic['lex_blocks']),lex_items=len(semantic['lex_items']),
                    lex_sense_owned=sum(x['ownership']=='sense' for x in semantic['lex_items']),
                    lex_entry_owned=sum(x['ownership']=='entry' for x in semantic['lex_items']),
                    lex_owner_unresolved=sum(x['ownership']=='unresolved' for x in semantic['lex_items']),
                    passage_owned_citations=sum(any(pid in {p['id'] for p in semantic['citable_passages']} for pid in c.get('supports',[])) for c in view['citations']),
                    owned_citations=owner,
                    sense_owned_citations=sum(bool(c.get('sense_node_id')) for c in view['citations']),
                    entry_only_citations=sum(c.get('container_ownership')=='entry' for c in view['citations']),
                    unresolved_owner_citations=len(view['citations'])-owner,
                    effective_language_conflicts=sum(x['language']=='unresolved' for x in semantic['effective_language_spans']),
                    citable_passages=len(semantic['citable_passages']))
        if args.contextual_semantics:
            stat.update(contextual_sanskrit_forms=len(semantic['sanskrit_forms']),sanskrit_correspondences=len(semantic['sanskrit_correspondences']),new_inline_citations=len(additions))
        if args.contextual_semantics:
            stat.update(untyped_explicit_language_indicators=sum(r['baseline_family']=='language_evidence_untyped' and r['outcome']=='unresolved' for r in classified), ignored_citation_cues=sum(r['baseline_family']=='ignored_citation_cue' and r['outcome']=='unresolved' for r in classified))
        metrics.append(stat)
        # Audit duplicate numbers inside a level, not nested label reuse.
        ds=pred.get('original_structure',{}).get('divisions',[])
        labels=[str(d.get('label','')) for d in ds]
        counts[kind+'_entries_no_sense']+=int(stat['senses']==0)
        counts[kind+'_entries_multiple_reader_sense_containers']+=int(len(view['senses'])>stat['senses'] and stat['senses']>0)
        if identity not in excluded:
            strata=[]
            if args.contextual_semantics:
                if additions:strata.append('inline_citation')
                if semantic['sanskrit_correspondences']:strata.append('Sanskrit_correspondence')
                if 'skt.' in text:strata.append('explicit_skt')
                if re.search(r'\(\d+[^)]*\)',text):strata.append('numeric_control')
            if len(text)<200:strata.append('simple')
            if stat['senses']>=4:strata.append('many_sense')
            if 'Lex.' in text:strata.append('lex')
            if 'skt.' in text or any(n['kind']=='sanskrit' for n in nodes):strata.append('sanskrit')
            if stat['citations']>=5:strata.append('citation')
            if refs:strata.append('xref')
            if any(x.get('canonical_resolution',{}).get('parsed_target',{}).get('shape') in ('wrapped_italic_target','raised_homonym_and_wrapped_target') for x in refs):strata.append('wrapped_xref')
            if any(x.get('canonical_resolution',{}).get('parsed_target',{}).get('homonym') for x in refs):strata.append('homonym_xref')
            if any(x['status']=='ambiguous' for x in view['cross_references']):strata.append('ambiguous_xref')
            if any(x['status']=='unresolved' for x in view['cross_references']):strata.append('absent_xref')
            if any(c.get('ownership_evidence_class')=='PDF_example_quotation' for c in view['citations']):strata.append('PDF_quotation')
            if any(c.get('ownership_evidence_class')=='definition_comparison_clause' for c in view['citations']):strata.append('definition_citation')
            if any(len(p['citation_node_ids'])>1 for p in view['semantic_hierarchy']['citable_passages']):strata.append('grouped_citations')
            if any(c['ownership']=='unresolved' for c in view['citations']):strata.append('negative_ownership')
            if args.contextual_semantics:strata=[s for s in strata if s in ('inline_citation','Sanskrit_correspondence','explicit_skt','numeric_control')]
            if re.search(r'\b(?:vb\.|Verb|pf\.|imp\.)',text):strata.append('verb')
            if kind=='pdf' and any('badw-v3-' in o['page_id'] or 'badw-v4-' in o['page_id'] for o in p['source']['source_objects']):strata.append('later_volume')
            import hashlib
            for s in strata:
                key=hashlib.sha256((VERSION+identity).encode()).hexdigest();pool=pools[kind+':'+s];pool.append((key,stat))
                pool.sort(key=lambda v:v[0]);del pool[12:]
            if strata and any(identity==st['identity'] for pool in pools.values() for _,st in pool):
                holdout_candidates[identity]=dict(packet=p,projection=pred,reader=view,metrics=stat)
        if identity in frozen_ids:
            holdout_candidates[identity]=dict(packet=p,projection=pred,reader=view,metrics=stat)
        if (i+1)%500==0:
            retained={st['identity'] for pool in pools.values() for _,st in pool}
            holdout_candidates={k:v for k,v in holdout_candidates.items() if k in retained or k in frozen_ids}
        if (i+1)%5000==0:print('finalize',i+1,dict(counts),flush=True)
    store.commit();store.close()
    if args.contextual_semantics:
        with gzip.GzipFile(filename=str(OUT/'contextual_classification.jsonl.gz'),mode='wb',mtime=0) as f:
            for rec in contextual_records:f.write((json.dumps(rec,ensure_ascii=False,sort_keys=True)+'\n').encode())
        write_json(OUT/'contextual_classification.json',dict(counts=dict(contextual_counts)))
    citation_reviews.finish()
    if baseline_store:baseline_store.close()
    holdout=[];chosen=set()
    for s,pool in sorted(pools.items()):
        for _,stat in pool:
            if stat['identity'] in chosen:continue
            holdout.append(dict(stratum=s,metrics=stat,review_status='source_review_pending',accuracy_status='not_independent_gold'));chosen.add(stat['identity'])
            if sum(x['stratum']==s for x in holdout)==2:break
    if frozen_sample:
        if frozen_ids-set(holdout_candidates):raise ValueError('Frozen holdout witness missing from replay')
        holdout=[dict(c,metrics=holdout_candidates[c['metrics']['identity']]['metrics']) for c in frozen_sample['cases']]
        chosen=frozen_ids
    with (WORK/'holdout_packets.jsonl').open('w') as f:
        for identity in sorted(chosen):f.write(json.dumps(holdout_candidates[identity],ensure_ascii=False)+'\n')
    write_json(OUT/'holdout.json',dict(seed=VERSION,excluded_identities=len(excluded),exclusion_paths_sha256={str(p):file_hash(p) for p in exclusion_paths},cases=holdout))
    write_json(OUT/'integration.json',dict(counts=dict(counts),bibliography_bridge=dict(bib_bridge),semantic_overlays=overlay,xref_reasons=dict(xref_reasons)))
    with gzip.GzipFile(filename=str(OUT/'baseline_residue.jsonl.gz'),mode='wb',mtime=0) as f:
        for item in residue:f.write((json.dumps(item,ensure_ascii=False,sort_keys=True)+'\n').encode())
    write_json(OUT/'relationships.json',dict(baseline_residue_families=dict(residue_counts),ownership_evidence=dict(evidence_counts)))
    # Replace baseline findings for relationships with integrated results.
    replaced={'citation_owner_unresolved','citation_identity_unresolved','xref_unresolved','xref_component_missing'}
    if args.contextual_semantics:replaced|={'language_evidence_untyped','ignored_citation_cue'}
    allrows=[a for a in rows(WORK/'anomalies.jsonl') if a['family'] not in replaced]+extra
    byfamily=collections.defaultdict(list)
    for a in allrows:byfamily[a['family']].append(a)
    rank=[]
    for family,aa in byfamily.items():
        layer,severity,action=FAMILIES[family]
        rank.append(dict(family=family,entries=len({a['identity'] for a in aa}),occurrences=len(aa),distribution=dict(collections.Counter(a['source_kind'] for a in aa)),layer=layer,severity=severity,recommended_action=action,classification='indicator_requires_review' if family not in replaced|{'pipeline_exception','reader_integrity'} else 'measured_contract_state',examples=aa[:6]))
    rank.sort(key=lambda r:({'critical':0,'high':1,'medium':2}[r['severity']],-r['entries'],r['family']))
    write_json(OUT/'families.json',rank)
    with gzip.GzipFile(filename=str(OUT/'anomalies.jsonl.gz'),mode='wb',mtime=0) as f:
        for a in allrows:f.write((json.dumps(a,ensure_ascii=False,sort_keys=True)+'\n').encode())
    with (OUT/'entries.tsv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(metrics[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(metrics)
    summary=json.loads((OUT/'summary.json').read_text())
    summary['totals']={k:sum(r[k] for r in metrics) for k,v in metrics[0].items() if isinstance(v,int)}
    summary['source_kinds']={kind:{k:sum(r[k] for r in metrics if r['source_kind']==kind) for k,v in metrics[0].items() if isinstance(v,int)} for kind in ('html','pdf')}
    summary['integration']=dict(counts);summary['counts']['anomaly_occurrences']=len(allrows)
    summary['limitations'][1]='Ownership uses exact Lex./HTML attestation, balanced PDF expression–quoted-gloss–citation envelopes, or unmixed source definition clauses. Candidate edges alone and generic proximity remain insufficient.'
    summary['entry_anomaly_distribution']={str(k):v for k,v in sorted(collections.Counter(collections.Counter(a['identity'] for a in allrows).values()).items())}
    fragments=Path('work/badw_verified_rebuild_20261003/article_witnesses/unassigned_page_fragments.jsonl.gz')
    if fragments.exists():summary['unassigned_pdf_page_fragments']=sum(1 for _ in rows(fragments))
    write_json(OUT/'summary.json',summary)
    manifest=json.loads((OUT/'manifest.json').read_text());manifest['integration_inputs_sha256']={str(p):file_hash(p) for p in [STAGING,INDEX,Path('data/reviewed_badw_semantic_annotations.jsonl'),Path('data/bibliography_alias_reviews.tsv'),BIB/'citation_links.jsonl',BIB/'source_rows.jsonl',Path('data/bibliography_occurrence_aliases.tsv'),Path('data/badw_language_glyph_reviews.jsonl'),fragments] if p.exists()}
    for evidence in (args.citation_reviews,Path('data/bibliography_external_publications.tsv')):
        if evidence:manifest['integration_inputs_sha256'][str(evidence)]=file_hash(evidence)
    manifest['outputs_sha256']={str(p):file_hash(p) for p in sorted(OUT.glob('*')) if p.name not in ('manifest.json','anomalies.jsonl')}
    for code in (Path('scripts/finalize_badw_corpus_structure.py'),Path('scripts/badw_semantic_hierarchy.py'),Path('scripts/badw_bounded_passages.py'),Path('scripts/badw_lex_assertions.py'),Path('scripts/badw_comparison_clauses.py'),Path('scripts/badw_reference_runs.py'),Path('scripts/badw_header_assertions.py'),Path('scripts/badw_source_assertions.py'),Path('scripts/badw_assertion_layout.py'),Path('scripts/badw_semantic_store.py'),Path('scripts/badw_dictionary_entry_view.py'),Path('scripts/resolve_badw_cross_references.py'),Path('scripts/verify_badw_semantic_replay.py'),Path('scripts/badw_header_structure.py'),Path('scripts/badw_pdf_structure_recovery.py'),Path('scripts/badw_pdf_mixed_clauses.py'),Path('scripts/badw_pdf_quotation_recovery.py'),Path('scripts/badw_recovered_fragment_integrity.py'),Path('scripts/badw_bibliography_citation_reviews.py'),Path('scripts/badw_bibliography_external.py')):
        manifest['code_sha256'][str(code)]=file_hash(code)
    manifest['semantic_store_sha256']=file_hash(WORK/'semantic.sqlite')
    if WORK.name=='badw_relationship_closure':
        manifest['baseline_commit']='e53176838a'
        manifest['baseline_store_sha256']=file_hash(Path('work/badw_semantic_hierarchy/semantic.sqlite'))
        manifest['semantic_contract_version']='badw-semantic-hierarchy-v2'
    if args.contextual_semantics:
        manifest['baseline_commit']=args.baseline_commit or ('252f90d0d4' if WORK.name=='badw_semantic_residue' else '0e4c724e21')
        manifest['baseline_store_sha256']=file_hash(baseline_path)
        manifest['contextual_semantics']=True
        manifest['code_sha256']['scripts/badw_contextual_semantics.py']=file_hash(Path('scripts/badw_contextual_semantics.py'))
        manifest['semantic_contract_version']=SEMANTIC_VERSION
    write_json(OUT/'manifest.json',manifest)
    print(json.dumps(summary,sort_keys=True))

if __name__=='__main__':main()
