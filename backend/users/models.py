import secrets
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


ROLE_CHOICES = [
    ('Admin', 'Admin'),
    ('Manager', 'Manager'),
    ('Accountant', 'Accountant'),
    ('Staff', 'Staff'),
]


class Membership(models.Model):
    ROLE_CHOICES = ROLE_CHOICES

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Staff')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'company')]

    def __str__(self):
        return f'{self.user.username} @ {self.company.name} ({self.role})'


class InviteCode(models.Model):
    code = models.CharField(max_length=64, unique=True)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='invite_codes',
        null=True,
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Staff')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_invites',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='used_invite',
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def generate(cls, user, company, role='Staff', valid_days=7):
        raw = secrets.token_urlsafe(12)
        # Format as TFU-XXXX-XXXX-XXXX for readability
        code = f'TFU-{raw[:4].upper()}-{raw[4:8].upper()}-{raw[8:12].upper()}'
        return cls.objects.create(
            code=code,
            company=company,
            role=role,
            created_by=user,
            expires_at=timezone.now() + timedelta(days=valid_days),
        )

    @property
    def status(self):
        if self.used_by_id:
            return 'used'
        if timezone.now() >= self.expires_at:
            return 'expired'
        return 'active'
