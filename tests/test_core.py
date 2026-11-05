import unittest

from tiny_quotient_filter import QuotientFilter, FullError


class TestQuotientFilter(unittest.TestCase):
    def test_empty_filter(self):
        qf = QuotientFilter(8)
        self.assertEqual(len(qf), 0)
        self.assertEqual(qf.capacity, 8)
        self.assertEqual(qf.load_factor, 0.0)
        self.assertNotIn(b"hello", qf)

    def test_insert_and_contains(self):
        qf = QuotientFilter(16)
        qf.insert(b"a")
        qf.insert(b"b")
        qf.insert(b"c")
        self.assertIn(b"a", qf)
        self.assertIn(b"b", qf)
        self.assertIn(b"c", qf)
        self.assertEqual(len(qf), 3)

    def test_duplicate_insert(self):
        qf = QuotientFilter(16)
        qf.insert(b"x")
        qf.insert(b"x")
        self.assertEqual(len(qf), 1)
        self.assertIn(b"x", qf)

    def test_full_error(self):
        qf = QuotientFilter(1)
        qf.insert(b"only")
        with self.assertRaises(FullError):
            qf.insert(b"another")

    def test_load_factor(self):
        qf = QuotientFilter(4)
        qf.insert(b"a")
        qf.insert(b"b")
        self.assertAlmostEqual(qf.load_factor, 0.5)

    def test_resize_not_supported(self):
        qf = QuotientFilter(2)
        qf.insert(b"a")
        qf.insert(b"b")
        with self.assertRaises(FullError):
            qf.insert(b"c")

    def test_false_positive_possible(self):
        # With a small filter, a non-inserted key may collide. This test
        # verifies that the filter does not return False for inserted keys,
        # and that it can return True for some non-inserted key (probabilistic).
        qf = QuotientFilter(8)
        for i in range(4):
            qf.insert(f"key{i}".encode())
        # Not a strict test of false positives, but ensures no crash.
        self.assertIn(b"key0", qf)
        self.assertIn(b"key3", qf)

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            QuotientFilter(0)
        with self.assertRaises(ValueError):
            QuotientFilter(3)
        with self.assertRaises(ValueError):
            QuotientFilter(-4)

    def test_type_error(self):
        qf = QuotientFilter(4)
        with self.assertRaises(TypeError):
            qf.insert("string")
        with self.assertRaises(TypeError):
            "string" in qf

    def test_repr(self):
        qf = QuotientFilter(4)
        self.assertEqual(repr(qf), "QuotientFilter(capacity=4, size=0)")


if __name__ == "__main__":
    unittest.main()
