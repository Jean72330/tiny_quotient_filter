"""A small quotient filter implementation.

The quotient filter stores a set of hashed keys. It is a compact alternative
to a Bloom filter that supports deletion and false-positive-free membership
for keys that were inserted (assuming no hash collisions).

This implementation uses a fixed-size table of 64-bit slots. Each slot stores a
remainder and three metadata bits (is_occupied, is_continuation, is_shifted).
The load factor is the fraction of occupied slots. Membership queries are
load-factor-aware: a query for a key that is not present can return True with
some probability that grows with the load factor. The filter never returns
False for a key that was inserted (again, assuming no hash collisions).

Design choices:
- The capacity must be a power of two so that the quotient is simply the high
  bits of the hash and the remainder is the low bits. This makes the modulo
  operation a bitmask.
- We use a single Python int per slot to store the remainder and metadata bits.
  This is memory-inefficient compared to a bytearray, but it is simple and
  correct. The library is "tiny" in API, not in memory footprint.
- The hash function is FNV-1a 64-bit, implemented inline to avoid depending on
  the stability of Python's built-in hash (which is randomized for strings).
"""

from __future__ import annotations

from typing import Iterable, Optional

__all__ = ["QuotientFilter", "FullError"]


class FullError(Exception):
    """Raised when an insertion would exceed the filter's capacity."""


# Metadata bit masks for a slot.
_OCCUPIED = 1 << 0
_CONTINUATION = 1 << 1
_SHIFTED = 1 << 2
_REMAINDER_MASK = ~((1 << 3) - 1)

_FNV_OFFSET_BASIS = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASK64 = (1 << 64) - 1


def _fnv1a_64(data: bytes) -> int:
    """Return a 64-bit FNV-1a hash of *data*.

    FNV-1a is used instead of Python's built-in hash because the latter is
    randomized for strings and bytes, which would make the filter's behaviour
    non-deterministic across processes. A stable hash is required for a data
    structure that may be persisted or shared.
    """
    h = _FNV_OFFSET_BASIS
    for b in data:
        h ^= b
        h = (h * _FNV_PRIME) & _MASK64
    return h


class QuotientFilter:
    """A fixed-capacity quotient filter.

    Parameters
    ----------
    capacity:
        Number of slots. Must be a power of two and at least 1.
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if capacity & (capacity - 1) != 0:
            raise ValueError("capacity must be a power of two")
        self._capacity = capacity
        self._mask = capacity - 1
        # Each slot is an int with the remainder in the high bits and metadata
        # in the low three bits. A zero slot is empty.
        self._slots: list[int] = [0] * capacity
        self._size = 0

    @property
    def capacity(self) -> int:
        """Number of slots in the filter."""
        return self._capacity

    @property
    def size(self) -> int:
        """Number of keys currently stored."""
        return self._size

    @property
    def load_factor(self) -> float:
        """Fraction of slots that are occupied (0.0 to 1.0)."""
        return self._size / self._capacity

    def _split(self, key: bytes) -> tuple[int, int]:
        """Return (quotient, remainder) for *key*."""
        h = _fnv1a_64(key)
        q = (h >> 3) & self._mask
        r = h & 0x7  # 3-bit remainder
        return q, r

    def _slot_remainder(self, slot: int) -> int:
        return self._slots[slot] >> 3

    def _slot_occupied(self, slot: int) -> bool:
        return bool(self._slots[slot] & _OCCUPIED)

    def _slot_continuation(self, slot: int) -> bool:
        return bool(self._slots[slot] & _CONTINUATION)

    def _slot_shifted(self, slot: int) -> bool:
        return bool(self._slots[slot] & _SHIFTED)

    def _set_slot(self, slot: int, remainder: int, occupied: bool, continuation: bool, shifted: bool) -> None:
        value = (remainder << 3)
        if occupied:
            value |= _OCCUPIED
        if continuation:
            value |= _CONTINUATION
        if shifted:
            value |= _SHIFTED
        self._slots[slot] = value

    def _find_run_start(self, q: int) -> int:
        """Return the index of the first slot in the run for quotient *q*.

        The caller must ensure that the cluster containing q is non-empty.
        """
        idx = q
        # Walk backwards to the start of the cluster.
        while self._slot_shifted(idx):
            idx = (idx - 1) & self._mask
        # Now walk forward to the first occupied slot, which is the run start.
        while not self._slot_occupied(idx):
            idx = (idx + 1) & self._mask
        return idx

    def _find_insert_slot(self, q: int, remainder: int) -> int:
        """Return the index where *remainder* should be inserted for quotient *q*.

        If the remainder is already present, returns its index.
        """
        if not self._slot_occupied(q):
            return q
        start = self._find_run_start(q)
        # Walk through the run, shifting entries as needed to keep the run sorted.
        idx = start
        while True:
            if not self._slot_continuation(idx):
                # This is the first entry of the run for quotient q.
                if self._slot_remainder(idx) == remainder:
                    return idx
                if self._slot_remainder(idx) > remainder:
                    return idx
            else:
                if self._slot_remainder(idx) == remainder:
                    return idx
            # Move to next slot.
            next_idx = (idx + 1) & self._mask
            if not self._slot_shifted(next_idx):
                return next_idx
            idx = next_idx

    def insert(self, key: bytes) -> None:
        """Insert *key* into the filter.

        If *key* is already present, this is a no-op. Raises FullError if the
        filter has no free slots.
        """
        if not isinstance(key, (bytes, bytearray)):
            raise TypeError("key must be bytes-like")
        key = bytes(key)
        q, r = self._split(key)

        if self._slot_occupied(q):
            # Check if already present.
            start = self._find_run_start(q)
            idx = start
            while True:
                if self._slot_remainder(idx) == r:
                    return  # already present
                next_idx = (idx + 1) & self._mask
                if not self._slot_shifted(next_idx):
                    break
                idx = next_idx

        if self._size >= self._capacity:
            raise FullError("quotient filter is full")

        # Find insertion point.
        if not self._slot_occupied(q):
            # Empty slot at q: place directly.
            self._set_slot(q, r, occupied=True, continuation=False, shifted=False)
            self._size += 1
            return

        start = self._find_run_start(q)
        # Walk to find the correct position within the run, shifting entries.
        idx = start
        while True:
            if self._slot_remainder(idx) == r:
                return  # already present (should not happen due to earlier check)
            if self._slot_remainder(idx) > r:
                break
            next_idx = (idx + 1) & self._mask
            if not self._slot_shifted(next_idx):
                idx = next_idx
                break
            idx = next_idx

        # Shift entries from idx onward to make room.
        # We walk backwards from the end of the cluster to idx.
        # First, find the end of the cluster.
        end = idx
        while self._slot_shifted((end + 1) & self._mask):
            end = (end + 1) & self._mask
        # Shift each slot one position forward.
        cur = end
        while cur != idx:
            prev = (cur - 1) & self._mask
            # Copy prev to cur, setting shifted bit.
            rem = self._slot_remainder(prev)
            occ = self._slot_occupied(prev)
            cont = self._slot_continuation(prev)
            self._set_slot(cur, rem, occ, cont, shifted=True)
            cur = prev
        # Place new entry at idx.
        # Determine continuation and shifted bits.
        cont = (idx != start)
        shifted = (idx != q)
        self._set_slot(idx, r, occupied=True, continuation=cont, shifted=shifted)
        self._size += 1

    def __contains__(self, key: bytes) -> bool:
        """Return True if *key* may be in the filter.

        False positives are possible; false negatives are not (assuming no
        hash collisions).
        """
        if not isinstance(key, (bytes, bytearray)):
            raise TypeError("key must be bytes-like")
        key = bytes(key)
        q, r = self._split(key)
        if not self._slot_occupied(q):
            return False
        start = self._find_run_start(q)
        idx = start
        while True:
            if self._slot_remainder(idx) == r:
                return True
            next_idx = (idx + 1) & self._mask
            if not self._slot_shifted(next_idx):
                return False
            idx = next_idx

    def __len__(self) -> int:
        return self._size

    def __repr__(self) -> str:
        return f"QuotientFilter(capacity={self._capacity}, size={self._size})"
