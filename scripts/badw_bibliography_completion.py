"""Reviewed apparatus reconciliation in the existing bibliography database.

Source authorities and occurrences remain immutable; membership records carry
reviewed work identities without changing citation resolution or edition claims.
"""
from collections import Counter, defaultdict
import hashlib
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

def validate_accounting(zones, accounting, records):
    """Require a complete, contiguous source-bound partition of every zone page."""
    expected = {(z['zone_id'], page) for z in zones
                for page in range(int(z['start_scan_page']), int(z['end_scan_page']) + 1)}
    seen = set()
    record_ids = {r['id'] for r in records}
    zone_by_id = {z['zone_id']: z for z in zones}
    for row in accounting:
        key = (row['zone_id'], row['scan_page'])
        if key in seen or key not in expected:
            raise ValueError('Duplicate or unexpected accounting page')
        seen.add(key)
        if hashlib.sha256(''.join(p['raw_text'] for p in row['parts']).encode()).hexdigest() != row['page_text_sha256']:
            raise ValueError('Accounting page text changed')
        zone = zone_by_id[row['zone_id']]
        if any(row[k] != zone[k] for k in ('source_label', 'pdf_sha256', 'ocr_sha256')):
            raise ValueError('Stale accounting provenance')
        if row['unresolved_residuals'] or not row['parts']:
            raise ValueError('Unaccounted apparatus residual')
        end = row['parts'][0]['start']
        for part in row['parts']:
            if part['start'] != end or part['end']-part['start'] != len(part['raw_text']):
                raise ValueError('Accounting partition gap or overlap')
            if not part['classification'] or not set(part['record_ids']) <= record_ids:
                raise ValueError('Unclassified text or missing record')
            end = part['end']
    if seen != expected:
        raise ValueError('Missing apparatus accounting page')
    return len(seen)


def ingest(db, rows, printed, publication_relations):
    records = [p['review'] for p in printed if 'zone_id' in p['candidate']]
    if not records or any("reconciliation_disposition" not in r for r in records):
        return None
    zones=list(csv.DictReader((ROOT/'data/bibliography_apparatus_zones.tsv').open(),delimiter='\t'))
    accounting=[json.loads(l) for l in (ROOT/'data/bibliography_apparatus_accounting.jsonl').read_text().splitlines()]
    validate_accounting(zones,accounting,records)
    authority = {r[0]: json.loads(r[1]) for r in db.execute('SELECT id,record_json FROM authority')}
    online = {r['id']: r for r in rows if r['scope'] == 'badw_online'}
    work_labels = {a['label']: i for i,a in authority.items() if a['kind'] == 'work' and a['scope'] == 'badw_online'}
    # Explicitly reviewed alternate sigla; never infer equivalence by edit distance.
    aliases = {'HMrg': 'HMṛg', 'Samdhi': 'Saṃdhi', 'PārSa': 'PārSa', 'Debn': 'Debṅ', 'Vḍn': 'Vḍṅ'}
    members = {i: i for i,a in authority.items() if a['kind'] == 'work'}
    excluded = set()
    for r in records:
        if r['reconciliation_disposition'] == 'composite_bibliographic_cross_reference' and r['authority_id']:
            excluded.add(r['authority_id'])
        target = work_labels.get(aliases.get(r['label'], ''))
        if target and r['authority_id'] and r['authority_id'] != target:
            members[r['authority_id']] = target
    for i in excluded:
        members.pop(i, None)
    # Bibliographic publications denote an authored bibliographic work in their
    # own right. A Tibetan work edited inside one is a separate entity.
    pub_parent = {i:i for i,a in authority.items() if a['kind']=='publication'}
    def root(i):
        while pub_parent[i] != i:
            i = pub_parent[i]
        return i
    for e in publication_relations:
        if e['status']=='reviewed' and e['relation_type'] in {'reprint_of','different_edition'}:
            a,b=root(e['source_id']),root(e['target_id'])
            pub_parent[a]=b
    publication_work = {i:'work-of-'+root(i) for i in pub_parent}
    db.executescript('''
    CREATE TABLE IF NOT EXISTS canonical_membership(authority_id TEXT PRIMARY KEY REFERENCES authority(id), canonical_id TEXT NOT NULL, relationship TEXT NOT NULL, record_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS authority_history(canonical_id TEXT PRIMARY KEY, record_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS apparatus_annotation(id TEXT PRIMARY KEY, record_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS apparatus_summary(id TEXT PRIMARY KEY, record_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS canonical_siglum(id TEXT PRIMARY KEY, record_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS apparatus_reference(occurrence_id TEXT NOT NULL, ordinal INTEGER NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(occurrence_id,ordinal));
    ''')
    with db:
        for i,c in {**members,**publication_work}.items():
            relation = 'publication_of_bibliographic_work' if i in publication_work else 'same_work'
            db.execute('INSERT INTO canonical_membership VALUES(?,?,?,?)',(i,c,relation,dump({'authority_id':i,'canonical_id':c,'relationship':relation,'evidence':'Reviewed apparatus identity, or explicit reviewed edition/reprint statement; publication work remains separate from any contained Tibetan work.'})))
    histories=defaultdict(list)
    sigla=defaultdict(list)
    for r in records:
        i=r['authority_id']
        if i and i not in excluded:
            histories[members.get(i,i)].append(r)
        elif r['reconciliation_disposition'] == 'work_or_collection_level_source':
            # Reviewed literal collection identities; these are not single works.
            histories['collection-'+r['label']].append(r)
        for siglum in r['sigla_as_printed'] or ([r['label']] if r['kind'] in {'work','abbreviation'} and r['apparatus_role']=='dictionary_source' and r['reconciliation_disposition']!='composite_bibliographic_cross_reference' else []):
            sigla[siglum].append(r['id'])
        if r['reconciliation_disposition'] in {'composite_bibliographic_cross_reference','work_or_collection_level_source'}:
            # Explicit source pointers remain relationships, not author authorities.
            refs=[]
            for siglum in re.findall(r'\[([^\]]+)\]', r['verified_transcription']):
                for token in re.split(r'[,;]',siglum):
                    token=token.strip()
                    refs.append({'literal_pointer':token,'work_id':work_labels.get(token),'status':'explicit_siglum_pointer' if token in work_labels else 'literal_scope_pointer','evidence_occurrence_id':r['id']})
            if not refs:
                refs=[{'literal_pointer':r['verified_transcription'],'status':'explicit_collection_or_publication_reference','evidence_occurrence_id':r['id'],'limitation':'Collection/reference scope preserved; no inferred edition identity.'}]
            with db:
                for n,e in enumerate(refs):
                    db.execute('INSERT INTO apparatus_reference VALUES(?,?,?)',(r['id'],n,dump(e)))
    for r in rows:
        if r['kind']=='work':
            sigla[r['label']].append(r['occurrence_id'])
        elif r['kind']=='abbreviation':
            sigla[r['label']].append(r['occurrence_id'])
        for s in r.get('associated_sigla',[]):
            if isinstance(s,str): sigla[s].append(r['occurrence_id'])
    with db:
        for label,occurrences in sorted(sigla.items()):
            db.execute('INSERT INTO canonical_siglum VALUES(?,?)',(label,dump({'literal_siglum':label,'occurrence_ids':sorted(set(occurrences)), 'work_ids':sorted({members.get(r['authority_id'],r['authority_id']) for r in records if r['id'] in occurrences and r['authority_id'] and r['kind']=='work' and r['authority_id'] not in excluded} | {r['id'] for r in rows if r['kind']=='work' and r['occurrence_id'] in occurrences}), 'scope':'Literal spelling preserved; abbreviation grammar and source sigla remain distinguishable through source occurrences.'})))
    # Project source bibliographic pointers without promoting candidate edition identities.
    reference_residuals=[]
    online_references=[]
    for occurrence_id, ordinal, record_json in db.execute('SELECT occurrence_id,ordinal,record_json FROM relation'):
        ref=json.loads(record_json)
        pointer={'type':'online_bibliographic_pointer','source_relation':ref,
                 'limitation':'Literal source bibliographic reference; candidate publications are not accepted edition identities.'}
        online_references.append(pointer)
        db.execute('INSERT INTO apparatus_reference VALUES(?,?,?)',(occurrence_id,ordinal,dump(pointer)))
        if ref['status']=='unmatched':
            reference_residuals.append({'id':occurrence_id+':'+str(ordinal),
                'reason':'Online Bca source description cites Vaidya 1960b, which has no independent bibliography target. Retained as an unresolved reference; no year-suffix substitution.',
                'source_relation':ref})
    for identity in set(members.values()) | set(pub_parent):
        histories.setdefault(identity, [])
    history_rows=[]
    for i,rr in sorted(histories.items()):
        rr.sort(key=lambda r:(r['chronology']['delivery_range'],r['id']))
        independent=[r for r in rr if not r.get('manifestation_of')]
        first=independent[0]['chronology']['delivery_range'] if independent else None
        ids={r['authority_id'] for r in rr} | {i}
        h={'canonical_id':i,'occurrences':[{'id':r['id'],'zone_id':r['zone_id'],'chronology':r['chronology'],'manifestation_of':r.get('manifestation_of'),'variants':r['variants']} for r in rr], 'earliest_observed_occurrence_ids':[r['id'] for r in independent if r['chronology']['delivery_range']==first], 'online_occurrence_ids':[r['occurrence_id'] for r in rows if r['id'] in ids], 'first_occurrence_basis':'Earliest among the four registered PDFs, ordered by delivery range. Bound-volume range does not establish the original delivery of introduction; no inferred publication date.'}
        history_rows.append(h)
        with db: db.execute('INSERT INTO authority_history VALUES(?,?)',(i,dump(h)))
    # Aggregate publication editions under their separately reviewed bibliographic work.
    grouped=defaultdict(list)
    for h in history_rows:
        if h['canonical_id'] in publication_work:
            grouped[publication_work[h['canonical_id']]].append(h)
    for work_id, editions in sorted(grouped.items()):
        occurrences=[o for h in editions for o in h['occurrences']]
        occurrences.sort(key=lambda o:(o['chronology']['delivery_range'],o['id']))
        independent=[o for o in occurrences if not o['manifestation_of']]
        first=independent[0]['chronology']['delivery_range'] if independent else None
        h={'canonical_id':work_id,'publication_ids':[e['canonical_id'] for e in editions],
           'occurrences':occurrences,
           'earliest_observed_occurrence_ids':[o['id'] for o in independent if o['chronology']['delivery_range']==first],
           'online_occurrence_ids':sorted({o for e in editions for o in e['online_occurrence_ids']}),
           'first_occurrence_basis':'Earliest registered evidence, delivery-range order; editions remain distinct.'}
        history_rows.append(h)
        db.execute('INSERT INTO authority_history VALUES(?,?)',(work_id,dump(h)))
    # Exhaustive definition search in the completed apparatus, plus all three
    # online lists and editorial classifications. Lexical use is separate.
    editorial=[json.loads(l) for l in (ROOT/'data/bibliography_apparatus_editorial_pages.jsonl').read_text().splitlines()]
    corpus=[(r['id'],r['verified_transcription']) for r in records]+[(r['occurrence_id'],r['label']+' '+r['text']) for r in rows if r['scope']=='badw_online']
    corpus += [(str(e.get('zone_id'))+':'+str(e.get('scan_page')),dump(e)) for e in editorial]
    pattern=re.compile(r'(?<![A-Za-z])Mim\s*(?:II?|[12lⅠⅡ])(?![A-Za-z])',re.I)
    hits=[{'source_id':i,'text':t} for i,t in corpus if pattern.search(t)]
    if hits:
        raise ValueError('Mim apparatus hits require individual definition review: '+dump(hits))
    note={'id':'wts-undefined-mim1-mim2','type':'reviewed_editorial_omission','finding':'WTS uses Mim1 and Mim2 without an identifiable definition in the bibliographic/siglum/editorial apparatus of the four registered PDFs or the three pinned online lists.', 'clarification':{'Mim1':'BDSN','Mim2':'CDSN'},'provenance':'Externally reviewed Mimaki evidence in bibliography_external_publications.tsv and bibliography_alias_reviews.tsv; digital-edition scholarly clarification, not expansions supplied by WTS.', 'definition_search':{'pattern':pattern.pattern,'sources_searched':len(corpus),'hits':hits},'citation_links':'Existing 382 reviewed links unchanged; no new edition claim.'}
    corrections=list(csv.DictReader((ROOT/'data/bibliography_citation_claim_reviews.tsv').open(),delimiter='\t'))
    maurer={'id':'maurer-reviewed-year-correction','type':'reviewed_source_year_correction','literal_year':'2000','reviewed_year':'2001','evidence':[r for r in corrections if r['status']=='reviewed_year_correction'],'limitation':'Author confirmation reported by user; cited pages not verified.'}
    errors=[{'occurrence_id':r['id'],'variant':v} for r in records for v in r['variants'] if v['reviewed_category']=='probable_source_error']
    unresolved=[{'id':r['id'],'label':r['label'],'literal':r['verified_transcription'],'reason':r['reconciliation_note'] if 'reconciliation_note' in r else r['evidence_note']} for r in records if r['reconciliation_disposition']=='unresolved_edition_relationship']
    unresolved += reference_residuals
    unresolved += [{'id':e['id'],'reason':e['evidence_note']} for e in publication_relations if e['status']=='candidate']
    categories=Counter(v['reviewed_category'] for r in records for v in r['variants'])
    print_ids={r['authority_id'] for r in records if r['authority_id'] and r['authority_id'] not in excluded}
    online_ids=set(online)
    canonical_print_ids={members.get(i,i) for i in print_ids}
    canonical_online_ids={members.get(i,i) for i in online_ids}
    external_publications={i for i,a in authority.items() if a['kind']=='publication' and a['scope'] not in {'badw_online','wts_print'}}
    unresolved_ids={r['authority_id'] for r in records if r['reconciliation_disposition']=='unresolved_edition_relationship'}
    summary={'scope':'Four registered PDFs plus three hash-pinned BAdW lists; external publications separately identified.', 'apparatus_zones':len(list(__import__('csv').DictReader((ROOT/'data/bibliography_apparatus_zones.tsv').open(),delimiter='\t'))), 'print_occurrences':len(records),'reviewed_online_crosswalks':sum(bool(r.get('online_crosswalk')) for r in records),'canonical_source_works':len(set(members.values())), 'canonical_bibliographic_works':len(set(publication_work.values())), 'canonical_publications':len(pub_parent), 'publications_by_scope':dict(Counter(authority[i]['scope'] for i in pub_parent)), 'canonical_collections_or_composite_sources':len({r['label'] for r in records if r['reconciliation_disposition']=='work_or_collection_level_source'}),'canonical_sigla_and_abbreviations':len(sigla), 'variant_sets':sum(bool(r['variants']) for r in records),'variants_by_category':dict(categories),'substantive_discrepancy_authorities':len({r['authority_id'] for r in records if any(v['substantive'] for v in r['variants'])}), 'substantive_variant_fields':sum(v['substantive'] for r in records for v in r['variants']), 'print_only_authorities':len(canonical_print_ids-canonical_online_ids-unresolved_ids), 'unresolved_print_counterpart_authorities':len(unresolved_ids), 'online_authorities_without_reviewed_print_counterpart':len(canonical_online_ids-canonical_print_ids),'exact_duplicate_scan_manifestations':sum(bool(r.get('manifestation_of')) for r in records),'repeated_published_occurrences':sum(max(0,len([r for r in rr if not r.get('manifestation_of')])-1) for rr in histories.values()),'dispositions':dict(Counter(r['reconciliation_disposition'] for r in records)),'print_only_authority_ids':sorted(canonical_print_ids-canonical_online_ids-unresolved_ids), 'online_without_reviewed_print_authority_ids':sorted(canonical_online_ids-canonical_print_ids), 'online_bibliographic_pointer_count':len(online_references), 'unresolved':unresolved,'probable_source_error_occurrences':errors,'editorial_omissions':[note], 'previously_reviewed_source_corrections':[maurer], 'count_limits':'Canonical totals include retained unresolved entities, which are never merged speculatively. Works are counted separately as dictionary-source works and authored bibliographic works: edited source containment is not same-work identity. Online-without-reviewed-print is an observed counterpart class, not a finding of error. Repeated records preserve all occurrences.'}
    with db:
        db.execute('INSERT INTO apparatus_annotation VALUES(?,?)',(note['id'],dump(note)))
        db.execute('INSERT INTO apparatus_annotation VALUES(?,?)',(maurer['id'],dump(maurer)))
        for error in errors:
            db.execute('INSERT INTO apparatus_annotation VALUES(?,?)',('probable-print-error-'+error['occurrence_id'],dump({'type':'probable_source_error',**error})))
        db.execute('INSERT INTO apparatus_summary VALUES(?,?)',('completed-registered-corpus',dump(summary)))
    return {'summary':summary,'histories':history_rows,'sigla':dict(sigla),'annotation':note}
