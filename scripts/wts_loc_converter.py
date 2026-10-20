"""Conservative, derived historical WTS LoC conversion experiment.

This is an inverse of reviewed WTS role mappings, not a Wylie converter.
Only securely attested onset and coda templates are recombined. Multiple
Unicode results and unsupported source characters cause abstention.
"""
import hashlib
import re

from build_tibetan_role_transcription_model import (
    ROLE_ORDER, authoritative_rules, compose, parse_tibetan_syllable, read, ROOT,
)


def held_out(tibetan):
    return int(hashlib.sha256(tibetan.encode()).hexdigest()[:8], 16) % 5 == 0


def role_rules():
    return authoritative_rules(read(ROOT/'data/tibetan_latin_role_mapping_candidates.tsv'))


class Converter:
    def __init__(self, pairs, rules=None):
        self.rules = rules if rules is not None else role_rules()
        self.onsets, self.codas = set(), set()
        self.training_syllables = set()
        for latin, tibetan in pairs:
            p = parse_tibetan_syllable(tibetan)
            rendered, _, missing = compose(p, self.rules)
            if missing or rendered != latin:
                continue
            self.onsets.add(tuple(p[r] for r in ROLE_ORDER[:4]))
            self.codas.add(tuple(p[r] for r in ROLE_ORDER[5:]))
            self.training_syllables.add(tibetan)
        self.inverse = {}
        vowels = {feature for role, feature in self.rules if role == 'vowel'}
        for onset in sorted(self.onsets):
            for vowel in sorted(vowels):
                for coda in sorted(self.codas):
                    p = dict(zip(ROLE_ORDER, (*onset, vowel, *coda)))
                    p['role_parse_status'] = 'fully_resolved'
                    latin, _, missing = compose(p, self.rules)
                    if missing:
                        continue
                    prefix, superscript, root, sub = onset
                    joined = lambda c: chr(ord(c)+0x50)
                    stack = superscript+joined(root) if superscript else root
                    text = prefix+stack+''.join(joined(c) for c in sub)
                    sign = {'a':'', 'i':'ི', 'u':'ུ', 'e':'ེ', 'o':'ོ'}.get(vowel)
                    if sign is None:
                        continue
                    text += sign+''.join(coda)
                    # Round-trip the independently parsed Unicode roles. Never
                    # resolve an ambiguous root by consulting the Latin input.
                    parsed = parse_tibetan_syllable(text)
                    if any(parsed[r] != p[r] for r in ROLE_ORDER):
                        continue
                    check, _, errors = compose(parsed, self.rules)
                    if errors or check != latin:
                        continue
                    self.inverse.setdefault(latin, set()).add(text)

    def syllable(self, literal):
        if not literal or not all(c.isalpha() or c == '’' for c in literal):
            return dict(status='unsupported_or_damaged', tibetan=None)
        candidates = sorted(self.inverse.get(literal, ()))
        if len(candidates) != 1:
            return dict(status='ambiguous' if candidates else 'unattested_structure', tibetan=None,
                        candidate_count=len(candidates))
        return dict(status='converted', tibetan=candidates[0])

    def convert(self, literal):
        # Preserve separator positions; do not repair spaces or apostrophes.
        parts = re.split(r'( +|[།༎༔])', literal)
        output = []
        converted = 0
        for part in parts:
            if not part:
                continue
            if part.isspace():
                output.append('་'+part[1:] if output and output[-1][-1] not in '།༎༔ ' else part)
            elif part in '།༎༔':
                output.append(part)
            else:
                result = self.syllable(part)
                if result['status'] != 'converted':
                    return dict(status=result['status'], tibetan=None, failed_syllable=part)
                output.append(result['tibetan'])
                converted += 1
        if not converted:
            return dict(status='unsupported_or_damaged', tibetan=None)
        text=''.join(output)
        if not text.endswith(('་', '།', '༎', '༔')):
            text+='་'
        return dict(status='converted', tibetan=text)
