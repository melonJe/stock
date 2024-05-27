import logging

from django.test import TestCase

from stock.models import Stock


class YourTestClass(TestCase):
    databases = ['stock_db']

    @classmethod
    def setUpTestData(cls):
        logging.info("setUpTestData: Run once to set up non-modified data for all class methods.")

    def setUp(self):
        logging.info("setUp: Run once for every test method to setup clean data.")

    def test_false_is_true(self):
        logging.info(Stock.objects.values('symbol'))
        self.assertTrue()
