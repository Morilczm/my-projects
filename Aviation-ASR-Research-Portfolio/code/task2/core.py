"""Task-two text contract, conservative renderer, gate, and corpus metrics.

No ML imports. All call-sign mappings must be mined from the supplied train.
The strict gate admits only representational edits explained by this renderer.
It is deliberately an initial, restrictive policy, not a semantic verifier.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from vendor.legacy_normalizer import clean_reference_text, normalize_eval, levenshtein
from vendor.legacy_restoration import restore as legacy_restore

PROMPT = ('Convert the aviation spoken-form transcript to canonical written text. '
          'Preserve unsupported words and do not invent entities.\nInput: {text}\nOutput:')
INPUT_SHA = {
    'train_pairs_raw.csv': '833247da65e969b7e91f1ee8b7a92a86a7a2b0108c52a8195532dace96e808d1',
    'dev_task2_inputs_raw.csv': '43dc0e0dcd5c4da953827d7cd0c537a87ca40b03926d74d93af39e4546f2be24',
}
MODES = {'oracle': 'transcription_n', 'baseline_asr': 'baseline_hypothesis', 'task1_asr': 'task1_hypothesis'}
DIGITS = dict(zip('zero one two three four five six seven eight nine'.split(), '0123456789'))
DIGITS.update(tree='3', fife='5', niner='9')
SMALL = dict(zip('ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(), range(10, 20)))
TENS = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))
TENS['fourty'] = 40
SCALES = {'hundred': 100, 'thousand': 1000, 'tousand': 1000, 'tauzend': 1000}
NUMWORDS = set(DIGITS) | set(SMALL) | set(TENS) | set(SCALES)
PREFIXES = ('air cruiser', 'blue nova', 'chase air', 'china star', 'exo', 'kingfisher', 'orbit air', 'ornate', 'zenith')
NATO = dict(zip('alpha bravo charlie delta echo foxtrot golf hotel india juliett kilo lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu'.split(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
NATO['juliet'] = 'J'
NATO['alfa'] = 'A'
TOKEN = re.compile(r"\d+\.\d+|[A-Za-z]+(?:['’][A-Za-z]+)*|\d+|[^\w\s]", re.UNICODE)
SIDE = {'left': 'L', 'right': 'R', 'center': 'C', 'centre': 'C'}
UNITS = {'meter': 'm', 'meters': 'm', 'metre': 'm', 'metres': 'm', 'm': 'm',
         'foot': 'ft', 'feet': 'ft', 'ft': 'ft', 'knot': 'kt', 'knots': 'kt', 'kt': 'kt',
         'kilometer': 'km', 'kilometers': 'km', 'km': 'km', 'mile': 'miles', 'miles': 'miles', 'nm': 'nm'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read_inputs(folder, split):
    name = 'train_pairs_raw.csv' if split == 'train' else 'dev_task2_inputs_raw.csv'
    path = Path(folder) / name
    if split not in {'train', 'dev'} or sha(path) != INPUT_SHA[name]:
        raise ValueError('Unexpected split or input fingerprint: ' + str(path))
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) != (12000 if split == 'train' else 1200) or any(r['split'] != split for r in rows):
        raise ValueError('Incorrect input coverage/split')
    return rows


def canonical_target(text):
    # Preserve decimals, leading zeroes, letter codes, and case in model labels.
    # Reuse the five-placeholder allowlist and slash handling exactly as v6.
    return re.sub(r'\s+', ' ', clean_reference_text(text).replace('’', "'")).strip(' ,;')


def number(words):
    """Strict nonnegative digit/cardinal parser; reject malformed full runs."""
    if not words:
        return None
    if all(w in DIGITS or w.isdigit() for w in words):
        return ''.join(DIGITS.get(w, w) for w in words)
    words = ['thousand' if w in {'tousand', 'tauzend'} else w for w in words]

    def under100(items):
        if len(items) == 1:
            w = items[0]
            if w in DIGITS:
                return int(DIGITS[w])
            return SMALL.get(w, TENS.get(w))
        if len(items) == 2 and items[0] in TENS and items[1] in DIGITS and DIGITS[items[1]] != '0':
            return TENS[items[0]] + int(DIGITS[items[1]])
        return None

    def under1000(items):
        if not items:
            return 0
        if items.count('hundred') == 1:
            i = items.index('hundred')
            if i != 1 or items[0] not in DIGITS or DIGITS[items[0]] == '0':
                return None
            rest = under100(items[i+1:]) if items[i+1:] else 0
            return None if rest is None else int(DIGITS[items[0]]) * 100 + rest
        return under100(items)

    if words.count('thousand') == 1:
        i = words.index('thousand')
        front = words[:i]
        if front and all(w in DIGITS for w in front):
            left = int(''.join(DIGITS[w] for w in front))
        else:
            left = under1000(front)
        right = under1000(words[i+1:])
        if left is not None and right is not None and 0 < left < 1000:
            return str(left * 1000 + right)
        return None
    value = under1000(words)
    return None if value is None else str(value)


def train_callsign_config(rows):
    """Unanimous prefix/code evidence, counted by distinct train text pairs."""
    votes = {p: Counter() for p in PREFIXES}
    seen = set()
    for row in rows:
        pair = (row['transcription_n'], row['excel_original_text'])
        if pair in seen:
            continue
        seen.add(pair)
        source = row['transcription_n'].lower()
        gold = re.findall(r'\b([A-Z]{3})(\d{2,5})\b', row['excel_original_text'])
        for prefix in PREFIXES:
            for match in re.finditer(r'\b' + re.escape(prefix) + r'\s+((?:(?:' + '|'.join(DIGITS) + r'|\d+)\b\s*)+)', source):
                digits = number(match[1].split())
                codes = {code for code, value in gold if value == digits and code not in {'QNH'}}
                if len(codes) == 1:
                    votes[prefix][next(iter(codes))] += 1
    stable = {p: {'code': next(iter(c)), 'unique_pair_support': sum(c.values())}
              for p, c in votes.items() if len(c) == 1 and sum(c.values()) >= 2}
    return {'stable_callsign_prefixes': stable,
            'all_train_votes': {p: dict(c) for p, c in votes.items()},
            'policy': 'only unanimous code mappings with >=2 distinct train text-pair evidence; conflicts copied',
            'test_used': False, 'train_rows': len(rows)}


def safe_rule(text, config, with_trace=False):
    """Replace only parsed spans; keep all other source characters unchanged."""
    text = str(text or '')
    matches = list(TOKEN.finditer(text))
    toks = [m[0].lower() for m in matches]
    edits = []
    i = 0

    def digits_at(start):
        end = start
        while end < len(toks) and (toks[end] in DIGITS or toks[end].isdigit()):
            end += 1
        if end < len(toks) and toks[end] in NUMWORDS:
            while end < len(toks) and (toks[end] in NUMWORDS or toks[end].isdigit()):
                end += 1
            return None, end
        return number(toks[start:end]), end

    def emit(start, end, rendered, kind):
        edits.append({'start': matches[start].start(), 'end': matches[end-1].end(),
                      'source': text[matches[start].start():matches[end-1].end()],
                      'output': rendered, 'kind': kind})

    while i < len(toks):
        converted = False
        for prefix, item in sorted(config.get('stable_callsign_prefixes', {}).items(), key=lambda p: -len(p[0])):
            words = prefix.split()
            if toks[i:i+len(words)] == words:
                value, end = digits_at(i+len(words))
                if value and 2 <= len(value) <= 5:
                    emit(i, end, item['code'] + value, 'callsign')
                    i = end
                    converted = True
                    break
        if converted:
            continue
        # Unknown/conflicting call-sign prefixes: copy the whole digit span.
        for prefix in PREFIXES:
            words = prefix.split()
            if toks[i:i+len(words)] == words:
                _, end = digits_at(i+len(words))
                i = max(end, i+len(words))
                converted = True
                break
        if converted:
            continue
        contexts = [(('runway',), 'RWY ', 'runway', 1, 2),
                    (('rwy',), 'RWY ', 'runway', 1, 2),
                    (('runway','in','use'), 'runway in use ', 'runway', 1, 2),
                    (('heading',), 'heading ', 'heading', 3, 3),
                    (('flight','level'), 'FL', 'flight_level', 2, 3),
                    (('qnh',), 'QNH ', 'qnh', 4, 4),
                    (('squawk',), 'squawk ', 'squawk', 4, 4),
                    (('pob',), 'POB ', 'pob', 1, 4)]
        for words, prefix, kind, minimum, maximum in contexts:
            if toks[i:i+len(words)] != list(words):
                continue
            value, end = digits_at(i+len(words))
            if not value or not minimum <= len(value) <= maximum:
                continue
            if kind == 'runway':
                if not 1 <= int(value) <= 36:
                    continue
                value = value.zfill(2)
                if end < len(toks) and toks[end] in SIDE:
                    value += SIDE[toks[end]]
                    end += 1
            if kind == 'heading' and int(value) > 360:
                continue
            if kind == 'squawk' and any(x not in '01234567' for x in value):
                continue
            emit(i, end, prefix + value, kind)
            i = end
            converted = True
            break
        if converted:
            continue
        if toks[i] in NATO:
            value, end = digits_at(i+1)
            if value and 1 <= len(value) <= 3 and i and toks[i-1] in {'taxiway','route','via','stand','bay'}:
                emit(i, end, NATO[toks[i]] + value, 'letter_number')
                i = end
                continue
        if toks[i] in NUMWORDS or toks[i].isdigit():
            end = i
            while end < len(toks) and (toks[end] in NUMWORDS or toks[end].isdigit()):
                end += 1
            value = number(toks[i:end])
            if value is None:
                i = end  # preserve the entire ambiguous/malformed run
                continue
            if end < len(toks) and toks[end] == 'decimal':
                right, right_end = digits_at(end+1)
                if right and 1 <= len(right) <= 3 and 2 <= len(value) <= 3:
                    emit(i, right_end, value + '.' + right, 'decimal')
                    i = right_end
                    continue
                i = max(right_end, end+1)
                continue
            if end < len(toks) and toks[end] == 'utc':
                if len(value) == 4 and int(value[:2]) < 24 and int(value[2:]) < 60:
                    emit(i, end+1, value + ' UTC', 'time')
                    i = end+1
                else:
                    i = end
                continue
            if end < len(toks) and toks[end] in UNITS:
                unit = UNITS[toks[end]]
                emit(i, end+1, value + (' ' if unit in {'miles','nm'} else '') + unit, 'number_unit')
                i = end+1
                continue
            # Generic digit/cardinal runs are evidence for a number. A singleton
            # homophone or pronoun is copied unless a typed context matched.
            if end-i > 1 or toks[i] in SMALL or toks[i] in TENS or toks[i].isdigit():
                emit(i, end, value, 'number')
            i = end
            continue
        i += 1
    result = text
    for edit in reversed(edits):
        result = result[:edit['start']] + edit['output'] + result[edit['end']:]
    return (result, edits) if with_trace else result


def atoms(text, config):
    """Case/punctuation/spacing-independent content atoms, decimals intact."""
    value = safe_rule(text, config).lower().replace('’', "'")
    value = re.sub(r'\bflight\s+level\b', 'fl', value)
    value = re.sub(r'\brunway\b', 'rwy', value)
    value = re.sub(r'\b(?:meters?|metres?)\b', 'm', value)
    value = re.sub(r'\b(?:knots?)\b', 'kt', value)
    value = re.sub(r'\b(?:feet|foot)\b', 'ft', value)
    value = re.sub(r'\bkilometers?\b', 'km', value)
    # Preserve arithmetic signs, slash units and ranges. Ordinary hyphenated
    # words remain formatting variants, while -270 is not equivalent to 270.
    value = re.sub(r'(?<!\d)-(?=[a-z])', ' ', value)
    return re.findall(r"\d+\.\d+|[a-z]+(?:'[a-z]+)*|\d+|[-+/%°]", value)


def gate(source, candidate, config, force_reason=None):
    fallback = safe_rule(source, config)
    reason = force_reason
    if reason is None:
        if not str(candidate).strip():
            reason = 'empty_output'
        elif len(candidate) > max(80, 3 * len(source)) or len(candidate) > 1500:
            reason = 'overlong_output'
        elif any(c.isalnum() and not c.isascii() for c in candidate):
            reason = 'unsupported_non_ascii_content'
        elif re.search(r'(?:^|\n)\s*(?:output|explanation|here is|the (?:answer|canonical text)|as an ai)\b|```|\{\s*"', candidate, re.I):
            reason = 'explanation_or_structured_output'
        elif atoms(source, config) != atoms(candidate, config):
            reason = 'unsupported_content_or_entity_change'
        elif entities(candidate) != entities(fallback):
            reason = 'entity_values_or_coverage_changed'
    return {'accepted': reason is None, 'reason': reason or 'accepted',
            'text': candidate.strip() if reason is None else fallback,
            'policy': 'ordered-content-equivalence-v1'}


ENTITY_PATTERNS = {
    'callsign': r'\b[A-Z]{3}\d{2,5}\b',
    'runway': r'\b(?:RWY|runway(?:\s+in\s+use)?)\s*\d{1,2}[LRC]?\b',
    'heading': r'\bheading\s*\d{3}\b',
    'flight_level': r'\b(?:FL|flight\s+level)\s*\d{2,3}\b',
    'altitude_m': r'\b\d{1,5}\s*(?:m|meters?)\b(?!\s*(?:/|per)\s*s)',
    'altitude_ft': r'\b\d{1,5}\s*(?:ft|feet|foot)\b',
    'frequency': r'\b\d{2,3}\.\d{1,3}\b',
    'squawk': r'\bsquawk\s*\d{4}\b',
    'speed': r'\b\d{1,3}\s*(?:kt|knots?)\b',
    'time_utc': r'\b\d{4}\s*UTC\b',
    'pob': r'\bPOB\s*\d{1,4}\b',
    'qnh': r'\bQNH\s*\d{4}\b',
    'distance': r'\b\d{1,5}\s*(?:km|kilometers?|nm|nautical\s+miles?|miles?)\b',
}


def entities(text):
    cleaned = clean_reference_text(text or '')
    result = set()
    for kind, pattern in ENTITY_PATTERNS.items():
        for match in re.finditer(pattern, cleaned, re.I):
            value = match[0].upper()
            if kind == 'callsign' and value[:3] in {'QNH', 'RWY', 'POB'}:
                continue
            value = re.sub(r'RUNWAY\s+IN\s+USE|RUNWAY', 'RWY', value)
            value = re.sub(r'FLIGHT\s+LEVEL', 'FL', value)
            value = re.sub(r'NAUTICAL\s+MILES?|MILES?', 'NM', value)
            value = re.sub(r'KILOMETERS?', 'KM', value)
            value = re.sub(r'METERS?', 'M', value)
            value = re.sub(r'FEET|FOOT', 'FT', value)
            value = re.sub(r'KNOTS?', 'KT', value)
            result.add((kind, re.sub(r'\s+', '', value)))
    return result


def rates(tp, fp, fn):
    return {'tp': tp, 'fp': fp, 'fn': fn, 'support': tp+fn,
            'precision': tp/(tp+fp) if tp+fp else None,
            'recall': tp/(tp+fn) if tp+fn else None,
            'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def score(records):
    """All rows, corpus denominators, entity sets matched within each row."""
    count = Counter()
    by_type = {k: Counter() for k in ENTITY_PATTERNS}
    reasons = Counter()
    for r in records:
        ref, pred = normalize_eval(r['reference']), normalize_eval(r['prediction'])
        count['rows'] += 1
        count['reference_words'] += len(ref.split())
        count['word_errors'] += levenshtein(ref.split(), pred.split())
        count['exact'] += ref == pred
        count['surface_exact'] += canonical_target(r['reference']).lower() == canonical_target(r['prediction']).lower()
        count['empty'] += not pred
        g, p, s = entities(r['reference']), entities(r['prediction']), entities(r['source_evidence'])
        for kind in by_type:
            gt, pt = {x for x in g if x[0] == kind}, {x for x in p if x[0] == kind}
            by_type[kind].update(tp=len(gt & pt), fp=len(pt-gt), fn=len(gt-pt))
        count['source_entities'] += len(s)
        count['source_deleted'] += len(s-p)
        count['introduced'] += len(p-s)
        count['wrong_introduced'] += len(p-s-g)
        if r.get('fallback_reason'):
            reasons[r['fallback_reason']] += 1
        count['technical_failures'] += bool(r.get('error'))
    totals = Counter()
    for values in by_type.values():
        totals.update(values)
    micro = rates(totals['tp'], totals['fp'], totals['fn'])
    return {**dict(count), 'corpus_wer': count['word_errors']/count['reference_words'] if count['reference_words'] else None,
            'exact_rate': count['exact']/count['rows'] if count['rows'] else None,
            'surface_exact_rate': count['surface_exact']/count['rows'] if count['rows'] else None,
            'entity_micro': micro, 'entity_per_type': {k: rates(v['tp'],v['fp'],v['fn']) for k,v in by_type.items()},
            'gold_entity_deletion_rate': micro['fn']/micro['support'] if micro['support'] else None,
            'gold_entity_false_discovery_rate': micro['fp']/(micro['tp']+micro['fp']) if micro['tp']+micro['fp'] else None,
            'source_entity_deletion_rate': count['source_deleted']/count['source_entities'] if count['source_entities'] else None,
            'wrong_introduction_rate': count['wrong_introduced']/count['introduced'] if count['introduced'] else None,
            'fallback_rows': sum(reasons.values()), 'fallback_rate': sum(reasons.values())/count['rows'] if count['rows'] else None,
            'fallback_reasons': dict(reasons)}
