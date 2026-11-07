"""Matched v2 hashing coordinates; only URI/header/body normalization differs.

Frozen privacy/numeric/tokenization rules remain unchanged. Channel assignment
uses each character n-gram's start, including boundary-spanning n-grams exactly once.
"""

import re
from functools import lru_cache

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction import FeatureHasher
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

from idps_ai.features.rich_content_v2 import rich_request_v2


@lru_cache
def hasher():
    return FeatureHasher(
        n_features=512, input_type="string", alternate_sign=False, dtype=np.float32
    )


def channel_ngrams(text):
    # Same lowercase and multi-whitespace preprocessing as HashingVectorizer(char).
    text = re.sub(r"\s\s+", " ", text.lower())
    body = text.index(" body ") + 1
    header = text.find(" header ")
    header = header + 1 if header >= 0 else body
    channels = [[], [], []]
    for n in (3, 4, 5):
        for start in range(max(0, len(text) - n + 1)):
            i = 0 if start < header else 1 if start < body else 2
            channels[i].append(text[start : start + n])
    return channels


def from_symbols(texts):
    counts = (
        hasher()
        .transform([c for text in texts for c in channel_ngrams(text)])
        .toarray()
        .reshape(len(texts), 3, 512)
    )
    shared = normalize(csr_matrix(counts.sum(axis=1)), norm="l2").toarray().astype(np.float32)
    each = normalize(csr_matrix(counts.reshape(-1, 512)), norm="l2").toarray().reshape(-1, 3, 512)
    separated = normalize(csr_matrix(each.sum(axis=1)), norm="l2").toarray().astype(np.float32)
    return shared, separated


def content(request):
    text, _ = rich_request_v2(
        request["method"], request["url"], request.get("headers"), request.get("body")
    )
    a, b = from_symbols([text])
    return a[0], b[0]


def reference(texts):
    return (
        HashingVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            n_features=512,
            alternate_sign=False,
            norm="l2",
            dtype=np.float32,
        )
        .transform(texts)
        .toarray()
    )
