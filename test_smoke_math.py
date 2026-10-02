import unittest
from smoke_math import add, subtract

class SmokeMathTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_subtract_positive_numbers(self):
        self.assertEqual(subtract(7, 2), 5)

    def test_subtract_from_negative_number(self):
        self.assertEqual(subtract(-1, 4), -5)

if __name__ == "__main__":
    unittest.main()
