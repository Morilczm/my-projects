import re
import unicodedata


ENGLISH_STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "on", "for", "with", "by", "from",
    "and", "or", "is", "are", "was", "were", "be", "been", "being",
    "can", "could", "should", "would", "will", "may", "might",
    "this", "that", "these", "those", "it", "its", "as", "at", "into",
}


TERM_ALIASES = {
    "fourier transform": ["傅里叶变换", "fourier transformation"],
    "time domain signal": ["时域信号", "time-domain signal"],
    "frequency domain representation": ["频域表示", "频率分量", "frequency-domain representation"],
    "frequency domain signal": ["频域信号", "frequency-domain signal"],
    "convolution": ["卷积"],
    "angular frequency": ["角频率"],
    "wavelength": ["波长"],
    "hash table": ["哈希表", "散列表"],
    "hash function": ["哈希函数"],
    "collision resolution": ["冲突解决", "哈希冲突处理"],
    "binary search tree": ["二叉搜索树"],
    "stack": ["栈"],
    "keys": ["关键字", "键"],
    "buckets": ["桶", "存储位置"],
}


REVERSE_ALIASES = {}
for canonical, aliases in TERM_ALIASES.items():
    REVERSE_ALIASES[canonical] = canonical
    for alias in aliases:
        REVERSE_ALIASES[alias.lower()] = canonical


def normalize_term(text):
    value = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    value = value.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"[_/]+", " ", value)
    value = re.sub(r"\s*-\s*", " ", value)
    value = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokenize_for_retrieval(text):
    normalized = normalize_term(text)
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", normalized)
    expanded = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 2:
            expanded.extend(token[i:i + 2] for i in range(len(token) - 1))
    return expanded


def remove_stopwords(tokens):
    return [
        token for token in tokens
        if token and token not in ENGLISH_STOPWORDS and len(token) > 1
    ]


def core_tokens(text):
    return remove_stopwords(tokenize_for_retrieval(text))


def alias_terms_for_query(query):
    normalized = normalize_term(query)
    aliases = set()
    canonical = REVERSE_ALIASES.get(normalized)
    if canonical:
        aliases.add(canonical)
        aliases.update(TERM_ALIASES.get(canonical, []))
    for canonical_term, alias_values in TERM_ALIASES.items():
        canonical_norm = normalize_term(canonical_term)
        if canonical_norm and canonical_norm in normalized:
            aliases.add(canonical_term)
            aliases.update(alias_values)
        for alias in alias_values:
            alias_norm = normalize_term(alias)
            if alias_norm and alias_norm in normalized:
                aliases.add(canonical_term)
                aliases.update(alias_values)
    return sorted(aliases)


def expanded_core_tokens(text):
    tokens = set(core_tokens(text))
    for alias in alias_terms_for_query(text):
        tokens.update(core_tokens(alias))
    return sorted(tokens)
