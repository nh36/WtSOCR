"""Publish checksum-bound machine suggestions separately from print certificates.

Offline only: consumes paid observations, rechecks their bindings and retains every
exception. Whole physical scans avoid inventing printed folios or spread sides.
"""
import argparse
from collections import Counter, defaultdict
import copy
import csv
import json
from pathlib import Path
import shutil
import time

import badw_campaign_review as review
import badw_model_worker as w
from badw_html_print_facsimiles import reviewed_records, REVIEWS

DATA = w.DATA/'badw_html_print_provisional.generated.json'
POLICY = 'two-source-readings-provisional-v1'
LABEL = 'Suggested original printed page — automatically matched, not yet verified.'


def eligibility(row, second, body):
    if row['already_certified']:
        return 'already_certified'
    if row['previous_decisions']:
        return 'previous_decision'
    if row['state'] != 'model-source-reviewed':
        return 'disputed' if row['state'] == 'exception' else 'review_pending'
    headings = [row['heading']] + [i for i in second['inventory']['items']
                                  if i['item_id'] in row['second_item_ids']]
    key = w.a.proof_key(body['headword']['loc'])
    if not any(w.a.proof_key(i['heading_loc']) == key for i in headings):
        return 'heading_mismatch'
    # Editorial /1 can correspond to an unnumbered print heading; any printed
    # numeral must agree explicitly. Missing numerals are retained as a risk.
    if any(i['printed_homonym'] is not None and
           str(i['printed_homonym']) != str(body['homonym']) for i in headings):
        return 'homonym_mismatch'
    return 'eligible'


def deduplicate(rows):
    """Conflicts include unsuccessful competing proposals, not only survivors."""
    assignments = defaultdict(set)
    for row in rows:
        assignments[row['source_url']].add(row['page'])
    selected, seen = [], set()
    for row in rows:
        if row['disposition'] != 'eligible':
            continue
        if len(assignments[row['source_url']]) != 1:
            row['disposition'] = 'competing_pages'
        elif row['source_url'] in seen:
            row['disposition'] = 'duplicate'
        else:
            seen.add(row['source_url']); selected.append(row)
            row['disposition'] = 'published_provisional'
    return selected


def export(root, output=DATA):
    started = time.monotonic()
    root = w.private(root)
    cfg = review.c.config(review.c.database(root))
    resources = w.authoritative(Path(cfg['bodies']))
    bodies, registry = resources[1], resources[4]
    pages, rows, failures = {}, [], []
    # Verify registered originals once per export, not once per article.
    verified = set()
    for path in sorted(root.glob('pages/*/match.json')):
        directory = path.parent
        try:
            pack, inv, match = review.load_page(directory, resources, cfg['model'], verified)
            source = registry[pack['source']]
            physical = pack['physical_page']
            if not 1 <= physical <= int(source['pages']):
                raise ValueError('physical page outside registered source')
            if pack['input_hashes'] != resources[0]['inputs']:
                raise ValueError('stale corpus inputs')
            blind = copy.deepcopy(pack)
            blind.pop('inventory', None); blind.pop('match_images', None)
            spec = w.request_spec('source_review', blind, cfg['model'], cfg['detail'], cfg['max_output_tokens'])
            cache = directory/'cache'/(w.a.object_digest(spec)+'.json')
            second = None
            if cache.exists():
                cached = w.load(cache)
                # execute is deliberately not called: this command cannot buy work.
                if cached.get('status') == 'rejected model response; no evidence authority':
                    second = review.recover_review(cached, spec, blind)
                else:
                    if (cached.get('request') != spec or cached.get('request_sha256') != w.a.object_digest(spec)
                            or cached.get('result_sha256') != w.a.object_digest(cached.get('result'))):
                        raise ValueError('corrupt blind review cache')
                    w.validate('source_review', cached['result'], blind)
                    second = cached
            packet = review.packet(pack, inv, match, second, resources, directory)
            key = directory.name
            pages[key] = dict(source=pack['source'], source_sha256=pack['source_sha256'],
                physical_page=physical, image=pack['image'], geometry=pack['geometry'],
                inventory_sha256=inv['result_sha256'], match_sha256=match['result_sha256'],
                inventory_request_sha256=inv['request_sha256'], match_request_sha256=match['request_sha256'],
                second_observation_sha256=packet['second_observation_sha256'],
                second_request_sha256=packet['second_request_sha256'], model=cfg['model'],
                first_recovery=match.get('recovery',[]),
                census=dict(Counter(i['classification'] for i in inv['result']['items'])),
                inputs=pack['input_hashes'])
            for row in packet['associations']:
                body = bodies[row['source_id']]
                if (row['html_sha256'] != body['sources'][0]['sha256'] or
                        row['source_url'] != body['source_url'] or body['source_kind'] != 'html'):
                    raise ValueError('exact HTML source binding failed')
                other = None
                if second:
                    other = dict(inventory=[i for i in second['result']['inventory']['items'] if i['item_id'] in row['second_item_ids']],
                        matching=[m for m in second['result']['matching']['matches'] if m['item_id'] in row['second_item_ids']])
                # Keep observations, not the bulk acquired component text.
                record = {k:v for k,v in row.items() if k not in ('component','publication_eligible')}
                record.update(page=key, headword=body['headword']['loc'], homonym=body['homonym'],
                    second_reading=other, disposition=eligibility(row, second['result'] if second else None, body))
                rows.append(record)
        except (ValueError, KeyError) as exc:
            failures.append(dict(page=directory.name, reason=str(exc)))
    selected = deduplicate(rows)
    result = dict(version=1, policy=POLICY, label=LABEL, certified=False,
        registry_sha256=w.a.digest(w.DATA/'source_pdfs.tsv'),
        certified_ledger_sha256=w.a.digest(w.a.GENERATED),
        manual_ledger_sha256=w.a.digest(REVIEWS), pages=pages,
        witnesses=selected, review_queue=[r for r in rows if r['disposition']!='published_provisional'],
        failures=failures, summary=dict(Counter(r['disposition'] for r in rows)))
    w.write(output, result)
    print(json.dumps(dict(summary=result['summary'],failed_pages=failures,
                         elapsed_seconds=round(time.monotonic()-started,2)),ensure_ascii=False),flush=True)
    return result


def validate_dataset(data):
    if data['policy'] != POLICY or data['certified'] is not False:
        raise ValueError('suggestions cannot claim certification')
    for key, path in [('registry_sha256',w.DATA/'source_pdfs.tsv'),
                      ('certified_ledger_sha256',w.a.GENERATED),('manual_ledger_sha256',REVIEWS)]:
        if data[key] != w.a.digest(path):
            raise ValueError('stale provisional dataset: '+key)
    accepted, _ = reviewed_records(REVIEWS)
    certified = {r['source_url'] for r in accepted['witnesses']}
    seen = set()
    registry = {r['label']:r for r in csv.DictReader((w.DATA/'source_pdfs.tsv').open(),delimiter='\t')}
    for row in data['witnesses']:
        if row['source_url'] in certified or row['source_url'] in seen:
            raise ValueError('duplicate or certified suggested identity')
        seen.add(row['source_url'])
        page = data['pages'][row['page']]; source = registry[page['source']]
        if (page['source_sha256'] != source['sha256'] or
                not 1 <= page['physical_page'] <= int(source['pages']) or
                row['disposition']!='published_provisional' or row['state']!='model-source-reviewed' or
                not page['second_observation_sha256']):
            raise ValueError('invalid provisional source assignment')
        if (row['already_certified'] or row['previous_decisions'] or not row['second_reading']
                or row['first_matching']['outcome'] != 'supported'
                or row['first_matching']['source_id'] != row['source_id']
                or not any(m['source_id'] == row['source_id'] and m['outcome']=='supported'
                           for m in row['second_reading']['matching'])):
            raise ValueError('invalid provisional identity evidence')


def prepare(dataset, output):
    """Lossless whole-page derivatives, shared per physical scan."""
    from pypdf import PdfReader, PdfWriter
    data = w.load(dataset); validate_dataset(data)
    output = w.private(output); output.mkdir(parents=True,exist_ok=True)
    registry = {r['label']:r for r in csv.DictReader((w.DATA/'source_pdfs.tsv').open(),delimiter='\t')}
    readers, derivatives = {}, {}
    for key in sorted({r['page'] for r in data['witnesses']}):
        row = data['pages'][key]; source = registry[row['source']]
        if row['source'] not in readers:
            original = w.a.ROOT/source['filename']
            if w.a.digest(original) != row['source_sha256']:
                raise ValueError('original scan checksum mismatch')
            readers[row['source']] = PdfReader(original)
        page = readers[row['source']].pages[row['physical_page']-1]
        name = w.a.object_digest([POLICY,row['source_sha256'],row['physical_page']])+'.pdf'
        writer = PdfWriter(); writer.add_page(page)
        with (output/name).open('wb') as stream: writer.write(stream)
        derivatives[key] = dict(path=name,sha256=w.a.digest(output/name))
    w.write(output/'manifest.json',dict(dataset_sha256=w.a.digest(dataset),dataset=str(Path(dataset).resolve()),pages=derivatives))
    return output/'manifest.json'


class Suggestions:
    def __init__(self, manifest, output):
        self.manifest = Path(manifest); self.prepared = w.load(manifest)
        self.data = w.load(self.prepared['dataset']); validate_dataset(self.data)
        if w.a.digest(self.prepared['dataset']) != self.prepared['dataset_sha256']:
            raise ValueError('prepared suggestions differ from dataset')
        self.rows = {(r['source_url'],r['html_sha256']):r for r in self.data['witnesses']}
        self.output, self.used, self.attached = Path(output), set(), set()

    def attach(self, entry):
        if entry['source_kind'] != 'html' or any(s.get('print_provenance') for s in entry['sources']):
            return
        row = self.rows.get((entry['source_url'],entry['sources'][0]['sha256']))
        if row is None: return
        if entry['headword']['loc'] != row['headword'] or str(entry['homonym']) != str(row['homonym']):
            raise ValueError('suggested HTML identity changed')
        page = self.data['pages'][row['page']]; derivative = self.prepared['pages'][row['page']]
        source = self.manifest.parent/derivative['path']
        if row['page'] not in self.used:
            if w.a.digest(source) != derivative['sha256']:
                raise ValueError('suggested derivative changed')
            destination = self.output/'sources'/'print'; destination.mkdir(exist_ok=True)
            shutil.copyfile(source,destination/source.name); self.used.add(row['page'])
        entry['sources'].append(dict(url='sources/print/'+source.name+'#page=1&view=Fit',
            label=LABEL,sha256=derivative['sha256'],suggested_print_provenance=dict(
                source=page['source'],source_sha256=page['source_sha256'],physical_page=page['physical_page'],
                policy=POLICY,printed_folio=None,side=None,evidence='provisional_print_links.json',
                source_id=row['source_id'],page=row['page'])))
        self.attached.add(row['source_url'])


def refresh_reader(manifest, reader):
    """Update only suggestion sources in an already complete reader milestone."""
    reader=w.private(reader)
    metadata=w.load(reader/'manifest.json')
    catalog_data=w.load(reader/'data.json')
    catalog=catalog_data['entries']
    if metadata.get('entries')!=29878 or len(catalog)!=29878:
        raise ValueError('suggestion refresh requires a complete reader')
    suggestions=Suggestions(manifest,reader)
    changed=0
    for entry in catalog:
        path=reader/entry['path']; body=w.load(path)
        before=copy.deepcopy(body)
        body['sources']=[s for s in body['sources'] if not s.get('suggested_print_provenance')]
        suggestions.attach(body)
        # Only sources may change; lexical text and every reference are retained.
        if {k:v for k,v in before.items() if k!='sources'}!={k:v for k,v in body.items() if k!='sources'}:
            raise ValueError('suggestion refresh changed witness body')
        if body!=before:
            w.write(path,body);changed+=1
            entry['sha256']=w.a.digest(path)
    if len(suggestions.attached)!=len(suggestions.rows):
        raise ValueError('not all provisional identities attached to reader')
    w.write(reader/'provisional_print_links.json',suggestions.data)
    w.write(reader/'data.json',catalog_data)
    metadata['catalog_sha256']=w.a.digest(reader/'data.json')
    metadata['provisional_print_links']=dict(count=len(suggestions.attached),
        dataset_sha256=w.a.digest(suggestions.prepared['dataset']),policy=POLICY)
    w.write(reader/'manifest.json',metadata)
    return dict(witnesses=29878,changed_source_lists=changed,suggested_links=len(suggestions.attached))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--campaign',type=Path)
    ap.add_argument('--dataset',type=Path,default=DATA)
    ap.add_argument('--prepare',type=Path)
    ap.add_argument('--refresh-reader',type=Path,help='Refresh suggestions only in an existing complete reader; requires --prepare')
    args=ap.parse_args()
    if args.campaign: export(args.campaign,args.dataset)
    if args.prepare: print(prepare(args.dataset,args.prepare))
    if args.refresh_reader:
        if not args.prepare: ap.error('--refresh-reader requires --prepare')
        print(json.dumps(refresh_reader(args.prepare/'manifest.json',args.refresh_reader)))
    if not args.campaign and not args.prepare: ap.error('supply --campaign or --prepare')


if __name__=='__main__': main()
