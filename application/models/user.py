from django.db import models

class user(models.Model):
    email = models.CharField

    def __str__(self):
        return self.email


class stock(models.Model):
    symbol = models.CharField
    name = models.CharField
    unit = models.CharField

    def __str__(self):
        return self.name

