#!/usr/bin/env python3
"""Preserve forensic residue with bounded diagnostic classifications, never new owners."""
import argparse, collections, gzip, json, re, sqlite3
from pathlib import Path

def source_reason(literal, context, source_kind, family):
    """Diagnostic source grammar; never changes the accounting or semantic role."""
    if family == 'other_heading_source_text':
        if re.search(r'\b(?:alttib\.|resp\.|honor|prn\.|postpos\.|adv\.)', literal):
            return 'register_or_grammatical_label', 'Register/grammatical wording has no complete accepted field grammar.'
        if re.search(r'\b(?:bzw\.|oder|und|Nf\.|Nebenf|zu|für)\b', literal):
            return 'shared_or_composite_heading_syntax', 'Shared/composite heading connector lacks a complete independently delimited target list.'
        return 'unregistered_heading_wording', 'Heading wording is preserved; its full field or target-list syntax is not established.'
    if family != 'lexical_prose_without_proven_boundary':
        return family, None
    if re.search(r'\b(?:fut|pf|imp|Kurzf)\b', literal):
        return 'fragmented_header_marker', 'Fragmented header marker has no complete target envelope.'
    if re.search(r'\bauch\b', context) and literal.lstrip().startswith(','):
        return 'body_or_header_alias_continuation', 'List continuation may be a body construction; header position and member boundary are not established.'
    if re.search(r'\b(?:s\.\s*v\.|vgl\.)', context):
        return 'reference_target_or_comparison_continuation', 'Comparison/reference structure lacks an independently bounded target or clause.'
    if '~' in literal or re.search(r';\s*~', context):
        return 'lexical_substitution_clause', 'Substitution syntax is visible, but typography does not establish a complete form/gloss production.'
    if any(c in context for c in '„“'):
        return 'quotation_adjacent_unbounded_fragment', 'Adjacent quotation does not establish whether the residual is an example, gloss or surrounding definition.'
    if re.search(r'\b(?:der|die|das|eine|einer|eines|ein|einen|und|oder|als|von|mit|für|eine[rmsn]?|sein|werden|Beiname|Art)\b', literal):
        return 'mixed_or_Roman_clause_without_syntactic_closure', 'German clause material is present but a complete syntactic/typographic envelope is not established.'
    if '\n' in literal:
        return 'wrapped_form_or_clause_without_role_boundary', 'Physical wrapping does not establish the lexical role or a unique continuation boundary.'
    return 'isolated_form_or_clause_fragment', 'Fragment has no complete source marker/typography production establishing its role.'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,default=Path('work/badw_forensic_structure'));ap.add_argument('--output',type=Path,default=Path('data/badw_forensic_structure'));a=ap.parse_args()
    db=sqlite3.connect('file:'+str(a.work/'semantic.sqlite')+'?mode=ro',uri=True)
    owners=collections.defaultdict(list)
    for entry,raw in db.execute("select entry,record_json from citation where ownership='unresolved'"):
        owners[entry].append(json.loads(raw))
    gaps={}
    with gzip.open(a.output/'header_accounting.jsonl.gz','rt') as f:
        for line in f:
            r=json.loads(line);gaps[r['identity']]=r
    reasons_count=collections.Counter();counts=collections.Counter();families=collections.Counter();glyphs=collections.Counter()
    with gzip.open(a.output/'ownership_residue.jsonl.gz','wt') as out, gzip.open(a.output/'pending_structure.jsonl.gz','wt') as pending:
        for line in (a.work/'projections.jsonl').open():
            row=json.loads(line);p=row['packet'];text=p['review_text'];identity=p['identity']
            for r in owners.get(identity,[]):
                span=r['source_span'];r['context']=text[max(0,span['start']-180):min(len(text),span['end']+180)]
                r['source_kind']=p['source_kind'];counts[(p['source_kind'],r['source_structural_family'])]+=1
                out.write(json.dumps(r,ensure_ascii=False)+'\n')
            for g in gaps.get(identity,{}).get('gaps',[]):
                if not g['alphabetic_characters']:continue
                literal=text[g['start']:g['end']]
                if g['family']=='source_decoding_residue':
                    glyphs.update(re.findall(r'⟦UNKNOWN:[^⟧]+⟧',literal))
                if g['family'] not in ('source_heading_pending_type','unparsed_lexical_prose_pending_review'):continue
                # Candidate labels express source grammar, not an accepted interpretation.
                if re.search(r'\b(?:pf\.|fut\.|imp\.|imper\.|Kurzf\.)',literal):family='header_form_or_relation_candidate'
                elif re.search(r'\bauch\b',literal) or (g['start']<20 and literal.lstrip().startswith(',')):family='alias_list_or_header_continuation_candidate'
                elif re.search(r'\b(?:vgl\.|s\.\s*v\.|Abt\.)',literal):family='reference_clause_candidate'
                elif '„' in literal or '“' in literal:family='quotation_or_gloss_candidate'
                elif g['family']=='source_heading_pending_type':family='other_heading_source_text'
                else:family='lexical_prose_without_proven_boundary'
                families[(p['source_kind'],family)]+=g['alphabetic_characters']
                reasons = {
                    'header_form_or_relation_candidate': 'Explicit header marker remains, but complete target/style continuity is not established by the accepted heading grammar.',
                    'alias_list_or_header_continuation_candidate': 'Auch/list syntax alone does not distinguish a header alias from body prose or establish the complete member boundary.',
                    'reference_clause_candidate': 'Reference connective/key text lacks an independently bounded canonical clause; existing citations are preserved separately.',
                    'quotation_or_gloss_candidate': 'Quote punctuation does not establish a unique example/gloss role and source envelope.',
                    'other_heading_source_text': 'Heading text lacks a complete accepted marker/target or grammatical-field production.',
                    'lexical_prose_without_proven_boundary': 'No accepted typography/header or explicit hyphen-continuation production establishes the lexical role and boundary.',
                }
                context=text[max(0,g['start']-100):min(len(text),g['end']+100)]
                reason_family, detailed_reason=source_reason(literal,context,p['source_kind'],family)
                reasons_count[(p['source_kind'],reason_family)]+=g['alphabetic_characters']
                nearby = [dict(id=n['id'],kind=n['kind'],start=n['start'],end=n['end'])
                          for n in row['projection']['nodes']
                          if n['start'] < g['end']+60 and g['start']-60 < n['end']]
                pending.write(json.dumps(dict(identity=identity,source_sha256=p['review_text_sha256'],start=g['start'],end=g['end'],literal=literal,family=family,alphabetic_characters=g['alphabetic_characters'],status='diagnostic_candidate_not_semantic_claim',source_grammar_family=reason_family,unresolved_reason=detailed_reason or reasons[family],source_kind=p['source_kind'],context=context,nearby_components=nearby),ensure_ascii=False)+'\n')
    result=dict(pending_source_grammar_reasons=[dict(source_kind=k[0],family=k[1],count=v) for k,v in sorted(reasons_count.items())],ownership_families=[dict(source_kind=k[0],family=k[1],count=v) for k,v in sorted(counts.items())],pending_alphabetic_families=[dict(source_kind=k[0],family=k[1],count=v) for k,v in sorted(families.items())],unknown_glyph_signatures=dict(glyphs),policy='No owner or decoding mapping inferred from diagnostic family; literal spans preserved.')
    (a.output/'forensic_residue.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
