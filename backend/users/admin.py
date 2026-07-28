from django.contrib import admin
from .models import Company, Membership, InviteCode


admin.site.register(Company)
admin.site.register(Membership)
admin.site.register(InviteCode)
