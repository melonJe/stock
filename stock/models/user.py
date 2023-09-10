from django.db import models


class User(models.Model):
    class Meta:
        db_table = 'user'
        app_label = 'users_db'

    objects = models.Manager()

    email = models.CharField(primary_key=True)
    pass_hash = models.BinaryField()
    pass_salt = models.BinaryField()
