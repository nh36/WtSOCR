"""Source-bound OCR reconciliation. Alignment aids never replace source readings.

A page-sized character-gram index proposes spatially adjacent OCR line spans.
Distinctive matches anchor bounded monotone alignment; ambiguous repeated text
is retained as alternatives. Both OCR readings derive from the SAME scan.
"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import unicodedata

VERSION = 'qa-pdf-spatial-sequence-v1'


def geometric_lines(layout):
    """Join adjacent fragments sharing a baseline, retaining original PDF IDs.

    Poppler sometimes emits one word per line, in reverse horizontal order.
    Only close fragments with overlapping vertical boxes can be joined. A
    column gutter is never bridged merely because two lines share a baseline.
    """
    groups=[]
    for i,row in sorted(enumerate(layout),key=lambda x:(x[1]['box'][1],x[1]['box'][0],x[0])):
        x,y,r,b=row['box']; height=b-y
        choices=[]
        for j,g in enumerate(groups):
            a,c,d,e=g['box']; overlap=min(b,e)-max(y,c)
            gap=max(0,x-d,a-r)
            if overlap>=.65*min(height,e-c) and gap<=max(5,.7*min(height,e-c)):
                choices.append((gap,j))
        if choices:
            g=groups[min(choices)[1]];g['ids'].append(i)
            g['box']=union_box(layout,g['ids'])
        else:groups.append(dict(ids=[i],box=list(row['box'])))
    for g in groups:
        g['ids'].sort(key=lambda i:(layout[i]['box'][0],i))
        g['text']=' '.join(layout[i]['text'] for i in g['ids'])
    return sorted(groups,key=lambda g:(g['box'][1],g['box'][0],g['ids']))


def normal(text):
    # NFC retains accents/Tibetan structure. Spacing, punctuation and line-end
    # hyphens are ignored only in this comparison key, never in source records.
    return ''.join(c for c in unicodedata.normalize('NFC', text).casefold()
                   if unicodedata.category(c)[0] in 'LNM')


def grams(text):
    return {text[i:i+4] for i in range(max(0,len(text)-3))}


def union_box(layout, ids):
    boxes=[layout[i]['box'] for i in ids]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def spatial_runs(layout):
    """Neighbours must overlap horizontally; PDF extraction order is not order.

    No presumed two/four column count, landscape split, or universal gutter.
    Wide lines crossing columns cannot join short body lines in another column.
    """
    below={}
    for i,a in enumerate(layout):
        ax,ay,ar,ab=a['box']; width=ar-ax; candidates=[]
        for j,b in enumerate(layout):
            if i==j: continue
            bx,by,br,bb=b['box']; bw=br-bx
            overlap=max(0,min(ar,br)-max(ax,bx))
            if by>=ab-2 and by-ay>2 and by-ab < max(28,3*(ab-ay)) and overlap>=.65*max(1,min(width,bw)) and max(width,bw)<2.2*max(1,min(width,bw)):
                candidates.append((by,abs(bx-ax),j))
        if candidates: below[i]=min(candidates)[2]
    runs=set()
    for i in range(len(layout)):
        run=[i];runs.add(tuple(run))
        for _ in range(2):
            nxt=below.get(run[-1])
            if nxt is None or nxt in run:break
            run.append(nxt);runs.add(tuple(run))
    return sorted(runs)


def reconcile(rows, layout):
    """Return one record per QA line, with unique/ambiguous/unmatched states.

    A unique approximate span needs >=.9 character agreement and .12 margin
    against disjoint regions. Short lines need exact, unique text. Context may
    resolve repetitions only between two independent distinctive text anchors
    in one spatial run. It never invents coordinates for unmatched text.
    """
    original=layout
    # Keep original lines as alternatives: a baseline join must never erase a
    # good original OCR reading or force a bridge across an unknown gutter.
    joined=[g for g in geometric_lines(original) if len(g['ids'])>1]
    layout=[dict(r,ids=[i]) for i,r in enumerate(original)]+joined
    keys=[normal(r['text']) for r in layout]
    inv=defaultdict(set)
    runs=spatial_runs(layout)
    # Extraction-contiguous fragments are candidates only when their union is
    # spatially compact. Reversed fragments use the baseline-joined alternative.
    for i in range(len(original)):
        for size in (2,3):
            ids=tuple(range(i,min(i+size,len(original))))
            b=union_box(layout,ids)
            if len(ids)==size and b[3]-b[1]<=65 and b[2]-b[0]<=max(250,2*(original[i]['box'][2]-original[i]['box'][0])):
                runs.append(ids)
    members=defaultdict(list)
    for ids in runs:
        for i in ids:members[i].append(ids)
    for i,key in enumerate(keys):
        for g in grams(key):inv[g].add(i)
    results=[]; candidates_by_line=[]
    for row in rows:
        key=normal(row['line_text']); gs=grams(key)
        votes=Counter(i for g in gs for i in inv[g])
        spans={ids for i,_ in sorted(votes.items(),key=lambda x:(-x[1],x[0]))[:8] for ids in members[i]}
        candidates=[]
        for ids in spans:
            target=''.join(keys[i] for i in ids)
            if not target or not key:continue
            ratio=SequenceMatcher(None,key,target,autojunk=False).ratio()
            # A QA line can be a proper part of one OCR line, or cover several.
            # Exact containment must include at least 10 significant characters.
            exact=key==target or (len(key)>=10 and key in target)
            if exact:ratio=1.
            if ratio>=.72:
                candidates.append(dict(score=round(ratio,6),pdf_lines=[j for i in ids for j in layout[i]['ids']],box=union_box(layout,ids),
                                       embedded_text='\n'.join(layout[i]['text'] for i in ids),exact=exact))
        # Prefer the smallest extent when equivalent windows include extra text.
        candidates.sort(key=lambda c:(-c['score'],len(c['pdf_lines']),c['pdf_lines']))
        unique=[]
        for c in candidates:
            if not any(set(c['pdf_lines'])&set(a['pdf_lines']) for a in unique):unique.append(c)
        best=unique[0] if unique else None
        margin=best['score']-(unique[1]['score'] if len(unique)>1 else 0) if best else 0
        sufficient=bool(best and ((len(key)>=10 and best['score']>=.9) or (len(key)>=4 and best['exact'])))
        located=sufficient and margin>=.12
        status='unique' if located else 'ambiguous' if sufficient else 'unmatched'
        candidates_by_line.append(unique)
        results.append(dict(status=status,coordinate=dict(best,method=VERSION,margin=round(margin,6)) if located else None,
                            alternatives=unique[:3] if not located else [],normalized_length=len(key),
                            authority='dependent OCR text alignment; not visual verification'))
    # Explicit monotone context: the immediate unique neighbours must constrain
    # a repeated exact line to one column, without crossing a furniture gap.
    for n,r in enumerate(results):
        if r['status']!='ambiguous':continue
        left=next((i for i in range(n-1,max(-1,n-7),-1) if results[i]['status']=='unique'),None)
        right=next((i for i in range(n+1,min(len(rows),n+7)) if results[i]['status']=='unique'),None)
        if left is None or right is None:continue
        a=results[left]['coordinate']['box'];b=results[right]['coordinate']['box']
        if b[1]<=a[1] or abs(a[0]-b[0])>25 or b[1]-a[1]>150:continue
        valid=[c for c in candidates_by_line[n] if c['score']>=.9 and a[1]<=c['box'][1]<=b[1]
               and abs(c['box'][0]-a[0])<=25]
        if len(valid)==1:
            r.update(status='unique_context',coordinate=dict(valid[0],method=VERSION,
                     context_qa_lines=[int(rows[i]['line']) for i in (left,right)]),alternatives=[])
    return align_between_anchors(rows, original, results)


def align_between_anchors(rows, original, results):
    """Bounded character-sequence alignment, including many:many line breaks.

    Both endpoints must already have distinctive unique text matches. Interior
    matches require 90% exact character coverage, not interpolated coordinates.
    SequenceMatcher matching blocks are a deterministic monotone edit alignment;
    uncertain substitutions/deletions remain unlocated. No cross-column bridge.
    """
    anchors=[i for i,r in enumerate(results) if r['status']=='unique' and
             r['normalized_length']>=16 and r['coordinate']['score']>=.94]
    for left,right in zip(anchors,anchors[1:]):
        if not 1 < right-left <= 12:continue
        a,b=results[left]['coordinate']['box'],results[right]['coordinate']['box']
        if not 0 < b[1]-a[1] <= 220 or abs(a[0]-b[0])>20:continue
        ids=[i for i,r in enumerate(original) if a[1]-2<=r['box'][1]<=b[3]+2
             and abs(r['box'][0]-a[0])<=25 and r['box'][2]<=max(a[2],b[2])+25]
        ids.sort(key=lambda i:(original[i]['box'][1],original[i]['box'][0],i))
        target='';owners=[]
        for i in ids:
            key=normal(original[i]['text']);target+=key;owners.extend([i]*len(key))
        source='';spans=[]
        for n in range(left,right+1):
            key=normal(rows[n]['line_text']);spans.append((len(source),len(source)+len(key)));source+=key
        if not source or not target:continue
        blocks=SequenceMatcher(None,source,target,autojunk=False).get_matching_blocks()
        for n in range(left+1,right):
            if results[n]['status'].startswith('unique'):continue
            lo,hi=spans[n-left];length=hi-lo
            if length<10:continue
            matched=[];positions=[]
            for block in blocks:
                start,end=max(lo,block.a),min(hi,block.a+block.size)
                if start<end:
                    ts=block.b+start-block.a;te=ts+end-start
                    matched.extend(owners[ts:te]);positions.extend(range(ts,te))
            coverage=len(matched)/length
            if coverage<.9 or not positions or max(positions)-min(positions)+1>1.3*length:continue
            pdf_ids=sorted(set(matched));bounds=union_box(original,pdf_ids)
            if bounds[3]-bounds[1]>75:continue
            results[n].update(status='unique_sequence',alternatives=[],coordinate=dict(
                pdf_lines=pdf_ids,box=bounds,embedded_text='\n'.join(original[i]['text'] for i in pdf_ids),
                score=round(coverage,6),method=VERSION,context_qa_lines=[int(rows[i]['line']) for i in (left,right)],
                alignment='bounded monotone character blocks; exact character coverage',exact=coverage==1))
    return results
