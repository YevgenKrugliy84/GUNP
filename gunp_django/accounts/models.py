from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    department = models.CharField(max_length=100, blank=True)

    @property
    def is_admin(self):
        return self.is_staff
