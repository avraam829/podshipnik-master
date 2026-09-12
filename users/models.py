from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    phone = models.CharField("Телефон", max_length=32, blank=True, default="")
    company = models.CharField("Компания", max_length=255, blank=True, default="")
