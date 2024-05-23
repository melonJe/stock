from django.test import TestCase
from stock.models import Stock


class YourTestClass(TestCase):
    databases = ['stock_db']

    @classmethod
    def setUpTestData(cls):
        print("setUpTestData: Run once to set up non-modified data for all class methods.")

    def setUp(self):
        print("setUp: Run once for every test method to setup clean data.")

    def test_false_is_true(self):
        print(Stock.objects.values('symbol'))
        self.assertTrue()
