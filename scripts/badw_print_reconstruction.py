"""Coordinate-based reconstruction, NOT scholarly identity or attachment authority.

The QA and embedded PDF OCR are two fallible readings of the same scan, not
independent scholarly witnesses. Agreement can establish a reproducible OCR
observation. It cannot turn that observation into a verified printed reading.
"""
from bisect import bisect_right
from collections import Counter
import unicodedata
import json
import re
from statistics import median

from badw_print_structure import boundary, box, source_barriers, clip_at_unlocated_heading, heading_layout


def column_model(rows, geometry):
    """Cluster repeated body-line left edges, never split at the media-box midpoint.

    Wide/short lines and page furniture do not vote. A cluster must have at least
    eight substantial lines. Missing or irregular layouts remain ambiguous.
    """
    width, height = geometry['width'], geometry['height']
    edges = sorted(b[0] for r in rows.values() if (b := box(r)) and
                   .12*height < b[1] < .93*height and .12*width < b[2]-b[0] < .55*width)
    groups = []
    for x in edges:
        if not groups or x - groups[-1][-1] > .035*width:
            groups.append([x])
        else:
            groups[-1].append(x)
    centres = [median(g) for g in groups if len(g) >= 8]
    separated = all(b-a > .12*width for a,b in zip(centres, centres[1:]))
    # Orientation alone establishes neither a spread nor its column count.
    # Repeated left edges support a multi-column hypothesis; page-side identity
    # remains a separate, unverified destination observation below.
    reliable = 2 <= len(centres) <= 4 and separated and not geometry['rotation']
    return dict(centres=centres, status='coordinate_clusters' if reliable else 'ambiguous_columns',
                observed_columns=len(centres), observations=len(edges),
                coordinate_coverage=round(sum(bool(box(r)) for r in rows.values())/max(1,len(rows)),6))


def column_of(b, model):
    if not b or model['status'] != 'coordinate_clusters':
        return None
    centres = model['centres']
    i = min(range(len(centres)), key=lambda i: abs(b[0]-centres[i]))
    # Headings/short indented text may start to the right of the body edge, but
    # a line spanning two body columns has no unique column membership.
    if b[0] < centres[i]-18 or (i+1<len(centres) and b[2] > centres[i+1]+10):
        return None
    return i


def numeral_before_loc(text, loc):
    """Observe a numeral only in the heading prefix, never after the LoC form.

    Punctuation resembling a superscript is NOT converted to a numeral. A
    numeral embedded in damaged Tibetan OCR is not a standalone numeral.
    """
    text = unicodedata.normalize('NFKC', text)
    loc = unicodedata.normalize('NFKC', loc)
    hits = list(re.finditer(r'(?<![\w])' + re.escape(loc) + r'(?![\w])', text))
    if not hits or hits[0].start() > 50:
        return dict(status='unread', number=None)
    prefix = text[:hits[0].start()].strip()
    nums = re.findall(r'(?<![\w:])([1-9])(?![\w:])', prefix)
    if len(nums) == 1:
        return dict(status='explicit_ocr_number', number=nums[0])
    if nums:
        return dict(status='ambiguous_numerals', number=None)
    # Only intact Tibetan plus whitespace can establish OCR-visible absence.
    # Quotes, question marks and degree signs often stand for unread numbers.
    clean = bool(prefix) and all('\u0f00' <= c <= '\u0fff' or c.isspace() for c in prefix)
    return dict(status='unnumbered_complete_qa_heading' if clean else 'unread', number=None)


def homonym_evidence(start, model):
    locs = sorted({s for s in start.get('loc_forms', []) if s}, key=lambda x:(-len(x),x))
    common = dict(qa_reading=start['text'],
                  embedded_reading=(start.get('coordinate') or {}).get('embedded_text'),
                  authority='source-bound OCR observation; not visual certification')
    if not locs:
        return dict(common,status='unread',number=None)
    loc = locs[0]
    qa = numeral_before_loc(start['text'], loc)
    pdf = numeral_before_loc(common['embedded_reading'] or '',loc)
    a,b=qa['number'],pdf['number']
    if a and b and a != b:
        status='conflicting_ocr_number';number=None
    elif a and a == b:
        status='explicit_number_ocr_agreement';number=a
    elif a or b:
        status='explicit_number_single_ocr';number=a or b
    elif qa['status']=='unnumbered_complete_qa_heading':
        status='unnumbered_qa_heading_assessable';number=None
    else:
        status='unread';number=None
    return dict(common,status=status,number=number,qa=qa,embedded=pdf,loc=loc)


def page_destination(rows, geometry, model, reviewed):
    result = dict(source_sha256=geometry['source_sha256'],physical_page=geometry['physical_page'],
                  rotation=geometry['rotation'], reviewed=reviewed,
                  printed_folio_status='reviewed' if reviewed else 'unresolved', candidates=[])
    if reviewed:
        result['geometry_status']='reviewed_certificate'
        return result
    if geometry['rotation']:
        result['geometry_status']='rotation_requires_review'
    elif not geometry['landscape']:
        result['geometry_status']='single_page_mediabox'
        result['candidates']=[dict(side='single',crop=geometry['mediabox'])]
    elif model['status']=='coordinate_clusters' and len(model['centres']) == 4:
        # Content-derived inter-page whitespace, not 50% of physical width.
        left = [box(r)[2] for r in rows.values() if column_of(box(r),model) == 1]
        right = [box(r)[0] for r in rows.values() if column_of(box(r),model) == 2]
        lo,hi = max(left,default=0), min(right,default=0)
        if 8 < hi-lo < geometry['width']*.18:
            gutter=round((lo+hi)/2,4)
            x0,y0,x1,y1=geometry['mediabox']
            result['geometry_status']='content_gap_candidate; margins/folio unverified'
            result['candidates']=[dict(side='left',crop=[x0,y0,gutter,y1]),
                                  dict(side='right',crop=[gutter,y0,x1,y1])]
            result['gutter_evidence']=[lo,hi]
        else:
            result['geometry_status']='no_secure_inter_page_gap'
    else:
        result['geometry_status']='spread_columns_unresolved'
    # Folio candidates are observations, never an extrapolated pagination offset.
    result['folio_ocr_candidates']=[dict(line=n,text=r['line_text'],box=box(r)) for n,r in rows.items()
        if box(r) and (box(r)[1]<geometry['height']*.12 or box(r)[1]>geometry['height']*.93)
        and re.fullmatch(r'\s*\d{1,4}\s*',r['line_text'])]
    return result


def reconstruct(db, reviewed_pages, witnesses):
    """Persist source reading positions and bounded-by-heading article alternatives.

    All family coordinates are indexed once. No 48-line window. A located start
    can extend across columns/pages until the next plausible start. Incomplete
    coordinates or weak boundaries explicitly prevent a complete-extent claim.
    Unlocated lines use the old local uncertain fallback at matching time.
    """
    db_reconstruction_locs={sid:[w['headword'].get('loc','')] for sid,w in witnesses.items()}
    counts=Counter(); families={}
    for (family,) in db.execute('SELECT DISTINCT family FROM pages ORDER BY family').fetchall():
        fc=Counter(); ordered=[]; models={}; geometries={}; starts={}; barriers={}; unlocated={}
        for page,features in db.execute('SELECT page,features FROM pages WHERE family=? ORDER BY page',(family,)).fetchall():
            geometry=json.loads(features); geometries[page]=geometry
            rows={n:json.loads(b) for n,b in db.execute('SELECT line,body FROM lines WHERE family=? AND page=?',(family,page))}
            layout=json.loads(db.execute('SELECT body FROM layouts WHERE family=? AND page=?',(family,page)).fetchone()[0])
            layout_rows={i:dict(coordinate=dict(box=r['box']),line_text=r['text']) for i,r in enumerate(layout)}
            model=column_model(layout_rows,geometry)
            model['coordinate_coverage']=round(sum(bool(box(r)) for r in rows.values())/max(1,len(rows)),6)
            models[page]=model
            destination=page_destination(layout_rows,geometry,model,reviewed_pages.get((family,page),[]))
            fc[model['status']]+=1;fc['geometry:'+destination['geometry_status']]+=1
            db.execute('INSERT INTO reading_pages VALUES (?,?,?)',(family,page,json.dumps(dict(model=model,destination=destination),sort_keys=True)))
            for n,row in rows.items():
                col=column_of(box(row),model)
                if col is not None:
                    ordered.append(((page,col,box(row)[1],box(row)[0],n),n,row))
            page_starts=[]
            for n,b in db.execute('SELECT line,body FROM starts WHERE family=? AND page=?',(family,page)):
                st=json.loads(b)
                st['loc_forms']=sorted({w for sid in st['matches'] for w in db_reconstruction_locs.get(sid,[])})
                starts[page,n]=st
                page_starts.append((n,st))
            source_layout=heading_layout(rows, lambda b: column_of(b,model))
            page_barriers=source_barriers(rows,page_starts,geometry['height'],source_layout)
            fc['lines_with_column_baseline']+=len(source_layout)
            for _,st in page_barriers:
                for reason in st['source_observation']['reasons']:
                    fc['heading_feature:'+reason]+=1
            for n,st in page_barriers:
                barriers[page,n]=st
                # A recovered box is insufficient when its physical column is
                # unresolved. Such a heading must still interrupt ownership.
                if column_of(box(st),model) is None:
                    unlocated.setdefault(page,[]).append((page,n))
            fc['source_boundary_hypotheses']+=len(page_barriers)
            fc['unlocated_boundary_hypotheses']+=len(unlocated.get(page,[]))
        ordered.sort(key=lambda x:x[0]); positions={}; boundaries=[]
        for i,(key,n,row) in enumerate(ordered):
            page,col=key[:2]; positions[page,n]=i
            db.execute('INSERT INTO reading_lines VALUES (?,?,?,?,?)',(family,page,n,i,json.dumps(dict(column=col,box=box(row)),sort_keys=True)))
            start=barriers.get((page,n))
            if start:
                # Top furniture cannot become a boundary merely through C6/QA.
                if box(row)[1] >= .09*geometries[page]['height']:
                    boundaries.append(i)
        for (page,n),start in starts.items():
            i=positions.get((page,n)); hom=homonym_evidence(start,models[page]);fc['homonym:'+hom['status']]+=1
            if i is None:
                extent=dict(status='unlocated_start',homonym_observation=hom)
            elif box(start)[1] < geometries[page]['height']*.09:
                extent=dict(status='top_furniture_candidate',homonym_observation=hom)
            else:
                end=bisect_right(boundaries,i); stop=boundaries[end] if end<len(boundaries) else len(ordered)
                # End-of-family without a following heading is always open.
                selected=ordered[i:stop] if stop<len(ordered) else ordered[i:i+1]
                # Entire physical span, including pages with no located lines.
                last_page=ordered[stop][0][0] if stop<len(ordered) else page
                relevant_pages=range(page,last_page+1)
                selected,interruptions=clip_at_unlocated_heading(selected,page,n,
                    [b for p in relevant_pages for b in unlocated.get(p,[])],end_page=last_page)
                pages={k[0] for k,_,_ in selected}
                complete=(not interruptions and stop<len(ordered) and all(models[p]['coordinate_coverage']>=.95 for p in pages)
                          and i in boundaries)
                # A weak / missing heading can be a missed boundary. Preserve as
                # an alternative rather than treating all text as owned evidence.
                refs=[[k[0],ln] for k,ln,_ in selected]
                if len(refs)>2048:
                    refs=[];complete=False
                extent=dict(status='coordinate_bounded' if complete else 'coordinate_extent_alternative',
                    refs=refs,unlocated_boundary_alternatives=[dict(family=family,page=p,line=ln) for p,ln in interruptions],
                    next_anchor=barriers.get((ordered[stop][0][0],ordered[stop][1]),{}).get('anchor') if stop<len(ordered) else None,
                    next_boundary=dict(family=family,page=ordered[stop][0][0],line=ordered[stop][1],
                        observation=barriers.get((ordered[stop][0][0],ordered[stop][1]),{}).get('source_observation')) if stop<len(ordered) else None,
                    homonym_observation=hom,position=list(ordered[i][0][:3]),
                    crosses_columns=len({(k[0],k[1]) for k,_,_ in selected})>1,
                    coverage_by_page={str(p):models[p]['coordinate_coverage'] for p in sorted(pages)},
                    ownership='proposed interval between plausible source headings; not independently verified')
                fc['cross_column_or_page']+=extent['crosses_columns']
                fc['interval_interrupted_by_unlocated_heading']+=bool(interruptions)
            extent['evidence_states']=dict(
                coordinates_recovered=extent['status']=='coordinate_bounded',
                reading_order='geometric_hypothesis' if extent.get('position') else 'unlocated',
                interval='plausible_heading_interval' if extent.get('refs') else 'unbounded',
                lexical_boundaries='unverified', definition_ownership='unverified')
            fc['extent:'+extent['status']]+=1
            db.execute('INSERT INTO extents VALUES (?,?)',(start['anchor'],json.dumps(extent,sort_keys=True)))
        families[family]=dict(fc);counts.update(fc)
    return dict(counts=dict(counts),by_family=families)


def homonym_dispute(risks):
    return any(r.startswith('homonym_') or r in ('printed_homonym_conflict','verified_printed_homonym_conflict') for r in risks)


def bracket_candidates(candidates, anchors, ranks, max_pages=10):
    """Rerank close lexical alternatives between two distinctive neighbours.

    Coordinates and *other* witnesses supply the brackets. A chain never creates
    a lexical candidate, removes a conflict, or supplies definition evidence.
    Unbracketed/weak alternatives retain their local score.
    """
    result=[]
    for p in candidates:
        q=dict(p); pos=p.get('reconstruction',{}).get('position')
        proof=p['definition_evidence']
        before=[];after=[]
        if pos and len(proof['rare_definition_tokens'])>=2 and not homonym_dispute(p['risks']):
            for a in anchors:
                ap=a['reconstruction']['position']
                if a['sid']==p['sid'] or a['family']!=p['family'] or abs(ap[0]-pos[0])>max_pages:
                    continue
                if ap<pos: before.append(a)
                if ap>pos: after.append(a)
        left=max(before,key=lambda a:a['reconstruction']['position'],default=None)
        right=min(after,key=lambda a:a['reconstruction']['position'],default=None)
        supported=bool(left and right and ranks[left['sid']]<ranks[p['sid']]<ranks[right['sid']])
        q['sequence_ranking']=dict(status='distinctive_neighbour_bracket' if supported else 'local_fallback',
            anchors=[left['anchor'],right['anchor']] if supported else [],
            anchor_witnesses=[dict(source_id=a['sid'], anchor=a['anchor'], local_score=a['score'], position=a['reconstruction']['position'], authority='provisional machine-selected witness') for a in (left,right)] if supported else [],
            local_score=p['score'],bonus=1 if supported else 0,
            authority='ranking evidence only; no identity or publication authority')
        q['score']=round(p['score']+(1 if supported else 0),6)
        result.append(q)
    return result


def sequence_rerank(db,witnesses, enabled=True):
    ranks={sid:w['order'] for sid,w in witnesses.items()}
    anchors=[];total=changed=boosted=0
    # Distinctive, unambiguous local identities alone can anchor another witness.
    for (sid,) in db.execute('SELECT DISTINCT sid FROM proposals ORDER BY sid').fetchall():
        rows=db.execute('SELECT body FROM proposals WHERE sid=? ORDER BY score DESC,aid LIMIT 2',(sid,)).fetchall()
        ps=[json.loads(r[0]) for r in rows]; p=ps[0]
        if (ranks[sid] is not None and p.get('reconstruction',{}).get('position') and
            len(p['definition_evidence']['rare_definition_tokens'])>=2 and
            {'leading_tibetan_exact','loc_exact'}<=set(p['heading_evidence']) and
            (len(ps)==1 or p['score']-ps[1]['score']>=2) and
            not homonym_dispute(p['risks']) and
            not set(p['risks'])&{'printed_homonym_conflict','neighbouring_compound_heading',
                'same_spelling_heading_repeated_on_page','displaced_or_incidental_heading'}):
            anchors.append(p)
    by_section={}
    for a in anchors:
        by_section.setdefault((a['family'],a['physical_page']//10),[]).append(a)
    for (sid,) in db.execute('SELECT DISTINCT sid FROM proposals ORDER BY sid').fetchall():
        ps=[json.loads(r[0]) for r in db.execute('SELECT body FROM proposals WHERE sid=? ORDER BY score DESC,aid',(sid,))]
        original=ps[0]['anchor']; updated=[]
        local_ranks={p['anchor']:i+1 for i,p in enumerate(ps)}
        for p in ps:
            bucket=p['physical_page']//10
            neighbours=[a for b in (bucket-1,bucket,bucket+1) for a in by_section.get((p['family'],b),[])]
            updated.extend(bracket_candidates([p],neighbours,ranks))
        for p in updated:
            p['sequence_ranking']['enabled']=enabled
            p['sequence_ranking']['adjusted_score']=p['score']
            p['sequence_ranking']['local_rank']=local_ranks[p['anchor']]
        adjusted=sorted(updated,key=lambda p:(-p['score'],p['anchor']))
        for i,p in enumerate(adjusted):
            p['sequence_ranking']['adjusted_rank']=i+1
            if not enabled:
                p['score']=p['sequence_ranking']['local_score']
        updated.sort(key=lambda p:(-p['score'],p['anchor']))
        changed+=updated[0]['anchor']!=original
        for p in updated:
            total+=1;boosted+=bool(p['sequence_ranking']['bonus'])
            db.execute('UPDATE proposals SET score=?,body=? WHERE sid=? AND aid=?',
                (p['score'],json.dumps(p,ensure_ascii=False,sort_keys=True),sid,p['anchor']))
    return dict(enabled=enabled,anchors=len(anchors),proposals=total,bracket_supported=boosted,changed_top_predictions=changed,
                maximum_bracket_distance_physical_pages=10,publication_authority=False)
