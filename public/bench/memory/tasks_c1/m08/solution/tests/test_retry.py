import unittest
from backoff import retry

class TestRetry(unittest.TestCase):
    def test_retry(self):
        self.assertTrue(retry.should_retry(0, 3, ValueError("x"), {ValueError}))
    def test_exhausted(self):
        self.assertFalse(retry.should_retry(3, 3, ValueError("x"), {ValueError}))
    def test_type_filter(self):
        self.assertFalse(retry.should_retry(0, 3, ValueError("x"), {TypeError}))
        self.assertFalse(retry.should_retry(0, 3, TypeError("x"), {ValueError}))

if __name__ == "__main__":
    unittest.main()
