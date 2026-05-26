#!/bin/bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py install_labels

# Automatically create superuser if it doesn't exist
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='${DJANGO_SUPERUSER_USERNAME}').exists():
    User.objects.create_superuser(
        '${DJANGO_SUPERUSER_USERNAME}',
        '${DJANGO_SUPERUSER_EMAIL}',
        '${DJANGO_SUPERUSER_PASSWORD}'
    )
EOF

# Create Django Groups and assign superuser to Admin
python manage.py shell <<'PYEOF'
from django.contrib.auth.models import Group, User
for group_name in ['Admin', 'Manager', 'Accountant']:
    Group.objects.get_or_create(name=group_name)
admin_group = Group.objects.get(name='Admin')
for user in User.objects.filter(is_superuser=True):
    user.groups.add(admin_group)
PYEOF

exec "$@"