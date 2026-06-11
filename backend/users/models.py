import secrets
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class InviteCode(models.Model):
    code = models.CharField(max_length=64, unique=True)
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
    def generate(cls, user, valid_days=7):
        raw = secrets.token_urlsafe(12)
        # Format as TFU-XXXX-XXXX-XXXX for readability
        code = f'TFU-{raw[:4].upper()}-{raw[4:8].upper()}-{raw[8:12].upper()}'
        return cls.objects.create(
            code=code,
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
