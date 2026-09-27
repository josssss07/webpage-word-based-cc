
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Dict, List, Tuple


# ---- Control URL numbers (reserved) ----------------------------------------
START = 0
WAIT = 1
END = 2

CONTROL = {START: "START", WAIT: "WAIT", END: "END"}


# ---- Page parsing ----------------------------------------------------------
class _PageParser(HTMLParser):
    """Pull URLs (href/src) and visible words out of an HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: List[str] = []
        self._text_chunks: List[str] = []
        self._skip = False  # inside <script>/<style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.urls.append(value.strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text_chunks.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._text_chunks)


_WORD_RE = re.compile(r"[A-Za-z]+")


def parse_page(html: str) -> Tuple[List[str], List[str]]:
    """Return (sorted unique URLs, sorted unique lowercase words)."""
    p = _PageParser()
    p.feed(html)

    urls = sorted(set(p.urls))
    words = sorted({w.lower() for w in _WORD_RE.findall(p.text)})
    return urls, words


# ---- The covert channel ----------------------------------------------------
class CovertChannel:
    """
    Build the URL + word dictionaries from a page and encode / decode messages.

    Exactly the same object is used by the sender and the receiver -- because
    they share the same page, they independently build identical dictionaries.
    """

    def __init__(self, html: str):
        self.urls, self.words = parse_page(html)
        self.n = len(self.urls)
        if self.n < 4:
            raise ValueError(
                "Page needs at least 4 unique URLs (3 control + >=1 word URL); "
                f"found only {self.n}."
            )
        self.base = self.n - 3  # number of non-control URLs (3 .. n-1)

        # URL number <-> URL string
        self.url_by_num: Dict[int, str] = dict(enumerate(self.urls))
        self.num_by_url: Dict[str, int] = {u: i for i, u in enumerate(self.urls)}

        # Word -> encoding tokens (list of URL numbers)
        self.word_to_tokens: Dict[str, List[int]] = {}
        # Reverse maps for decoding
        self._single: Dict[int, str] = {}          # url_num -> word
        self._multi: Dict[Tuple[int, int], str] = {}  # (shift, wordurl) -> word

        self.max_words = self.base + self.base * self.base
        self._build_word_dictionary()

    # -- dictionary construction --
    def _build_word_dictionary(self) -> None:
        for i, word in enumerate(self.words):
            if i >= self.max_words:
                break  # beyond channel capacity for this page
            if i < self.base:
                url = i + 3
                self.word_to_tokens[word] = [url]
                self._single[url] = word
            else:
                j = i - self.base
                shift = 3 + j // self.base
                wordurl = 3 + j % self.base
                self.word_to_tokens[word] = [shift, WAIT, wordurl]
                self._multi[(shift, wordurl)] = word

    # -- convenience --
    def sendable_vocabulary(self) -> List[str]:
        return list(self.word_to_tokens.keys())

    def num_to_url(self, num: int) -> str:
        return self.url_by_num[num]

    # -- ENCODE --
    def encode(self, message: str):
        """
        Turn a plaintext message into the covert URL-request sequence.

        Returns a dict with:
          sequence  : list[int]  -- the full URL-number sequence (START..END)
          urls      : list[str]  -- the same sequence as URL paths to request
          breakdown : list[dict] -- per-word explanation (tokens + urls)
          missing   : list[str]  -- message words NOT in the page vocabulary
        """
        tokens = [t.lower() for t in _WORD_RE.findall(message)]

        sequence: List[int] = [START]
        breakdown = []
        missing: List[str] = []

        for word in tokens:
            enc = self.word_to_tokens.get(word)
            if enc is None:
                missing.append(word)
                breakdown.append({"word": word, "sendable": False,
                                  "tokens": [], "urls": []})
                continue
            sequence.extend(enc)
            breakdown.append({
                "word": word,
                "sendable": True,
                "tokens": enc,
                "kind": "single" if len(enc) == 1 else "multi",
                "urls": [self.url_by_num[t] for t in enc],
            })
        sequence.append(END)

        return {
            "sequence": sequence,
            "urls": [self.url_by_num[t] for t in sequence],
            "breakdown": breakdown,
            "missing": missing,
        }

    # -- DECODE --
    def decode(self, sequence: List[int]) -> str:
        """
        Turn a covert URL-number sequence back into plaintext.

        The receiver walks the sequence between START and END. For each
        content URL it peeks at the next number: a WAIT (1) means the current
        URL was a *shift* and this is a multiple-URL word; otherwise it is a
        single-URL word.
        """
        # Isolate the payload between the first START and the next END.
        try:
            start = sequence.index(START)
        except ValueError:
            start = -1
        payload = sequence[start + 1:]
        if END in payload:
            payload = payload[:payload.index(END)]

        words: List[str] = []
        i = 0
        while i < len(payload):
            cur = payload[i]
            is_multi = (i + 1 < len(payload)) and (payload[i + 1] == WAIT)
            if is_multi:
                shift = cur
                wordurl = payload[i + 2] if i + 2 < len(payload) else None
                word = self._multi.get((shift, wordurl), "<?>")
                words.append(word)
                i += 3
            else:
                words.append(self._single.get(cur, "<?>"))
                i += 1
        return " ".join(words)

    # -- decode straight from requested URL paths (receiver side) --
    def decode_from_urls(self, url_paths: List[str]) -> str:
        """
        Given the raw list of requested URL PATHS captured in a server log,
        map them back to URL numbers, keep only the covert segment
        (START..END) and decode it. Unknown paths (noise) are dropped.
        """
        nums: List[int] = []
        capturing = False
        for path in url_paths:
            num = self.num_by_url.get(path)
            if num is None:
                continue  # request for something not in the dictionary = noise
            if num == START:
                capturing = True
                nums = [START]
                continue
            if not capturing:
                continue
            nums.append(num)
            if num == END:
                break
        return self.decode(nums)


# ---- Tiny self-test when run directly --------------------------------------
if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "sample_site", "index.html")) as fh:
        cc = CovertChannel(fh.read())

    print(f"URLs (n)          : {cc.n}")
    print(f"Word URLs (n-3)   : {cc.base}")
    print(f"Max vocabulary    : {cc.max_words}")
    print(f"Sendable words    : {len(cc.word_to_tokens)}")

    secret = "meet at the library at noon"
    enc = cc.encode(secret)
    print(f"\nSecret            : {secret!r}")
    print(f"Missing words     : {enc['missing']}")
    print(f"URL-number seq    : {enc['sequence']}")
    back = cc.decode(enc["sequence"])
    print(f"Decoded           : {back!r}")
    assert back == " ".join(t for t in re.findall(r"[A-Za-z]+", secret.lower())
                            if t in cc.word_to_tokens)
    print("\nself-test OK")
