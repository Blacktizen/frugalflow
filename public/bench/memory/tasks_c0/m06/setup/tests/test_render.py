import unittest
from table import render

class TestRender(unittest.TestCase):
    def test_render(self):
        self.assertEqual(render.render([["a", "bb"], ["ccc", "d"]]), "| a   | bb |\n| --- | -- |\n| ccc | d  |\n")
    def test_empty(self):
        self.assertEqual(render.render([]), "")

if __name__ == "__main__":
    unittest.main()
