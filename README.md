# tiny_quotient_filter

A fixed-capacity quotient filter that stores hashed keys and answers membership queries with a load-factor-aware false-positive rate.

```python
from tiny_quotient_filter import QuotientFilter, FullError

qf = QuotientFilter(1024)
qf.insert(b"hello")
qf.insert(b"world")

assert b"hello" in qf
assert b"world" in qf
assert b"missing" not in qf

print(len(qf))          # 2
print(qf.load_factor)   # 0.001953125

try:
    qf.insert(b"extra")
except FullError:
    print("filter is full")
```

## Why this exists

A Bloom filter is compact but cannot delete keys and its false-positive rate is
fixed at construction. A quotient filter is also compact, supports deletion
(in principle), and its false-positive rate is directly tied to the current
load factor: as the filter fills, queries for absent keys are more likely to
return `True`. This makes it useful when you want a single structure that
adapts its error rate to how full it is, rather than committing to a fixed
rate up front.

The trade-off is that insertion can fail with `FullError` once the filter is
full. There is no automatic resizing. If you need to grow, you must create a
new filter and re-insert the keys you care about.

## Awkward edge

The filter uses a 3-bit remainder, so the false-positive probability is at
least 2^-3 = 12.5% even at low load factors. This is a deliberate simplification
to keep the implementation small; it is not suitable for applications that
require a very low false-positive rate. Also, because the remainder is derived
from a hash, two different keys can map to the same quotient and remainder,
which is indistinguishable from a true positive.

## API

- `QuotientFilter(capacity)` — create a filter with `capacity` slots. `capacity`
  must be a power of two and at least 1.
- `insert(key)` — add `key` (bytes-like). Duplicate inserts are no-ops. Raises
  `FullError` if the filter has no free slots.
- `key in qf` — membership test. Returns `True` if `key` may be present, `False`
  if it is definitely absent.
- `len(qf)` — number of keys inserted.
- `qf.capacity` — number of slots.
- `qf.load_factor` — fraction of slots occupied, between 0.0 and 1.0.
- `FullError` — exception raised when inserting into a full filter.
