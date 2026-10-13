"""Rebuildable canonical hierarchy store; source caches stay outside Git.

Examples:
  python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite lex --siglum Dagy
  python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite passages --authority AUTHORITY_ID
  python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite citations --sense NODE --entry ID
  python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite xrefs --target ID
"""
import argparse
import json
import sqlite3

SCHEMA = '''
CREATE TABLE structural_fragment(id TEXT PRIMARY KEY, entry TEXT, kind TEXT, record_json TEXT);
CREATE TABLE header_field(id TEXT PRIMARY KEY, entry TEXT, kind TEXT, record_json TEXT);
CREATE INDEX header_entry ON header_field(entry);
CREATE TABLE language_form(id TEXT PRIMARY KEY, entry TEXT, lex_item TEXT, language TEXT, record_json TEXT);
CREATE TABLE language_effective(id TEXT PRIMARY KEY, entry TEXT, language TEXT, record_json TEXT);
CREATE TABLE language_correspondence(id TEXT PRIMARY KEY, entry TEXT, lex_item TEXT, form TEXT, record_json TEXT);
CREATE TABLE language_indicator(id TEXT PRIMARY KEY, entry TEXT, family TEXT, record_json TEXT);
CREATE TABLE language_conflict(id TEXT PRIMARY KEY, entry TEXT, record_json TEXT);
CREATE TABLE lex_item(id TEXT PRIMARY KEY, entry TEXT, sense TEXT, ownership TEXT, sanskrit INTEGER, record_json TEXT);
CREATE TABLE lex_siglum(item TEXT, siglum TEXT, PRIMARY KEY(item,siglum));
CREATE TABLE passage(id TEXT PRIMARY KEY, entry TEXT, sense TEXT, type TEXT, record_json TEXT);
CREATE TABLE citation(id TEXT PRIMARY KEY, entry TEXT, sense TEXT, ownership TEXT, record_json TEXT);
CREATE TABLE citation_passage(citation TEXT REFERENCES citation(id), passage TEXT REFERENCES passage(id), PRIMARY KEY(citation,passage));
CREATE TABLE citation_authority(citation TEXT, authority TEXT, PRIMARY KEY(citation,authority));
CREATE TABLE xref(id TEXT PRIMARY KEY, entry TEXT, target TEXT, entity TEXT, status TEXT, record_json TEXT);
CREATE INDEX lex_entry ON lex_item(entry);
CREATE INDEX passage_entry ON passage(entry);
CREATE INDEX citation_entry ON citation(entry);
CREATE INDEX xref_target ON xref(target);
'''


def create(path):
    # Rebuild only this derived database. Never an authority/source store.
    if path.exists():path.unlink()
    db=sqlite3.connect(path);db.execute('PRAGMA foreign_keys=ON');db.executescript(SCHEMA)
    return db


def ingest(db,view):
    encode=lambda r:json.dumps(r,ensure_ascii=False,sort_keys=True)
    identity=view['inspection_id'];semantic=view['semantic_hierarchy']
    for component in view.get('components', []):
        if component.get('structural_recovery'):
            db.execute('INSERT INTO structural_fragment VALUES(?,?,?,?)', (component['id'], identity, component['type'], encode(component)))
    for field in semantic.get('header_fields', []):
        db.execute('INSERT INTO header_field VALUES(?,?,?,?)',(field['id'],identity,field['header_kind'],encode(field)))
    for form in semantic.get('sanskrit_forms', []):
        db.execute('INSERT INTO language_form VALUES(?,?,?,?,?)',(form['id'],identity,form.get('lex_item_id'),form['language'],encode(form)))
    for span in semantic.get('effective_language_spans', []):
        db.execute('INSERT INTO language_effective VALUES(?,?,?,?)',(span['id'],identity,span['language'],encode(span)))
    for relation in semantic.get('sanskrit_correspondences', []):
        db.execute('INSERT INTO language_correspondence VALUES(?,?,?,?,?)',(relation['id'],identity,relation['lex_item_id'],relation['sanskrit_form_id'],encode(relation)))
    for marker in semantic.get('language_indicators', []):
        db.execute('INSERT INTO language_indicator VALUES(?,?,?,?)',(identity+':'+str(marker['start']),identity,marker['family'],encode(marker)))
    for conflict in semantic.get('source_language_conflicts', []):
        db.execute('INSERT INTO language_conflict VALUES(?,?,?)',(conflict['id'],identity,encode(conflict)))
    for item in semantic['lex_items']:
        db.execute('INSERT INTO lex_item VALUES(?,?,?,?,?,?)',(item['id'],identity,item['sense_node_id'],item['ownership'],bool(item['fields']['sanskrit']),encode(item)))
        # Sigla are observations, not bibliography identity assertions.
        for siglum in {s['literal'] for s in item['sigla']}:
            db.execute('INSERT INTO lex_siglum VALUES(?,?)',(item['id'],siglum))
    for passage in semantic['citable_passages']:
        db.execute('INSERT INTO passage VALUES(?,?,?,?,?)',(passage['id'],identity,passage['sense_node_id'],passage['passage_type'],encode(passage)))
    passage_ids={p['id'] for p in semantic['citable_passages']}
    for c in view['citations']:
        db.execute('INSERT INTO citation VALUES(?,?,?,?,?)',(c['component_id'],identity,c.get('sense_node_id'),c['ownership'],encode(c)))
        for pid in c.get('supports',[]):
            if pid not in passage_ids:continue  # Reviewed component relationships are not passage objects.
            db.execute('INSERT INTO citation_passage VALUES(?,?)',(c['component_id'],pid))
        for aid in c['accepted_authority_ids']:db.execute('INSERT INTO citation_authority VALUES(?,?)',(c['component_id'],aid))
    for x in view['cross_references']:
        if not x['component_id']:raise ValueError('unbound xref cannot enter canonical store')
        entity=(x.get('target_lexical_entity') or {}).get('id')
        db.execute('INSERT INTO xref VALUES(?,?,?,?,?,?)',(x['component_id'],identity,x['target_entry_id'],entity,x['status'],encode(x)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    fragments=sub.add_parser('fragments');fragments.add_argument('--kind')
    headers=sub.add_parser('headers');headers.add_argument('--kind')
    lex=sub.add_parser('lex');lex.add_argument('--siglum');lex.add_argument('--sanskrit',action='store_true')
    passage=sub.add_parser('passages');passage.add_argument('--authority')
    citation=sub.add_parser('citations');citation.add_argument('--unresolved',action='store_true');citation.add_argument('--sense');citation.add_argument('--passage');citation.add_argument('--evidence');citation.add_argument('--entry-level',action='store_true')
    xref=sub.add_parser('xrefs');xref.add_argument('--target');xref.add_argument('--unresolved',action='store_true');xref.add_argument('--status');xref.add_argument('--reason');xref.add_argument('--cross-manifestation',action='store_true')
    language=sub.add_parser('language');language.add_argument('--conflicts',action='store_true');language.add_argument('--effective',action='store_true');language.add_argument('--correspondences',action='store_true');language.add_argument('--indicators',action='store_true');language.add_argument('--unresolved',action='store_true');language.add_argument('--lex',action='store_true');language.add_argument('--siglum');language.add_argument('--tibetan')
    for child in (fragments,headers,lex,passage,citation,xref,language):child.add_argument('--entry');child.add_argument('--limit',type=int,default=50)
    a=p.parse_args()
    if a.command=='language':
        if sum((a.conflicts,a.effective,a.correspondences,a.indicators))>1:
            p.error('choose one language representation')
        if (a.lex or a.siglum) and (a.conflicts or a.effective or a.indicators):
            p.error('Lex. filters require forms or correspondences')
        if a.tibetan and not a.correspondences:
            p.error('--tibetan requires --correspondences')
        if a.unresolved and a.correspondences:
            p.error('unresolved indicators are queried with --indicators --unresolved')
    db=sqlite3.connect('file:'+a.db+'?mode=ro',uri=True)
    table={'fragments':'structural_fragment','headers':'header_field','lex':'lex_item','passages':'passage','citations':'citation','xrefs':'xref','language':'language_form'}[a.command]
    if a.command=='language':
        table='language_conflict' if a.conflicts else 'language_effective' if a.effective else 'language_correspondence' if a.correspondences else 'language_indicator' if a.indicators else 'language_form'
    conditions=[];values=[]
    if a.entry:conditions.append('entry=?');values.append(a.entry)
    if a.command=='language':
        if a.unresolved and a.conflicts:conditions.append("json_extract(record_json,'$.effective_resolution') IS NULL")
        elif a.unresolved:conditions.append("family IN ('unresolved_source_syntax','source_decoding_corruption')" if a.indicators else "language='unresolved'")
        if a.lex:conditions.append('lex_item IS NOT NULL')
        if a.siglum:conditions.append('lex_item IN (SELECT item FROM lex_siglum WHERE siglum=?)');values.append(a.siglum)
        if a.tibetan:conditions.append("json_extract(record_json,'$.tibetan_span.literal')=?");values.append(a.tibetan)
    if a.command in ('headers','fragments') and a.kind:conditions.append('kind=?');values.append(a.kind)
    if a.command=='lex':
        if a.siglum:conditions.append('id IN (SELECT item FROM lex_siglum WHERE siglum=?)');values.append(a.siglum)
        if a.sanskrit:conditions.append('sanskrit=1')
    if a.command=='passages' and a.authority:
        conditions.append('id IN (SELECT passage FROM citation_passage JOIN citation_authority USING(citation) WHERE authority=?)');values.append(a.authority)
    if a.command=='citations':
        if a.unresolved:conditions.append("ownership='unresolved'")
        if a.sense:conditions.append('sense=?');values.append(a.sense)
        if a.passage:conditions.append('id IN (SELECT citation FROM citation_passage WHERE passage=?)');values.append(a.passage)
        if a.evidence:conditions.append("json_extract(record_json,'$.ownership_evidence_class')=?");values.append(a.evidence)
        if a.entry_level:conditions.append("json_extract(record_json,'$.container_ownership')='entry'")
    if a.command=='xrefs':
        if a.target:conditions.append('(target=? OR entity=?)');values.extend([a.target,a.target])
        if a.unresolved:conditions.append("status!='resolved'")
        if a.status:conditions.append('status=?');values.append(a.status)
        if a.reason:conditions.append("json_extract(record_json,'$.residual_reason')=?");values.append(a.reason)
        if a.cross_manifestation:conditions.append("json_extract(record_json,'$.resolution_evidence.method')='exact_anchor_identity_other_manifestation'")
    sql='SELECT record_json FROM '+table+(' WHERE '+' AND '.join(conditions) if conditions else '')+' ORDER BY id LIMIT ?'
    for row in db.execute(sql,values+[a.limit]):print(row[0])

if __name__=='__main__':main()
