from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status


class SageTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['groups'] = list(user.groups.values_list('name', flat=True))
        return token


class SageTokenObtainPairView(TokenObtainPairView):
    serializer_class = SageTokenObtainPairSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    from django.contrib.auth.models import User, Group
    from django.utils import timezone
    from users.models import InviteCode

    invite_code_str = (request.data.get('invite_code') or '').strip()
    code_obj = InviteCode.objects.filter(code=invite_code_str).first()
    if not code_obj or code_obj.status != 'active':
        return Response({'detail': 'Invalid or expired invite code.'}, status=status.HTTP_400_BAD_REQUEST)

    username = (request.data.get('username') or '').strip()
    email = (request.data.get('email') or '').strip()
    password = request.data.get('password') or ''
    confirm_password = request.data.get('confirm_password') or ''

    if not username:
        return Response({'detail': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not password:
        return Response({'detail': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if password != confirm_password:
        return Response({'detail': 'Passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(password) < 8:
        return Response({'detail': 'Password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username=username).exists():
        return Response({'detail': 'Username already taken.'}, status=status.HTTP_400_BAD_REQUEST)
    if email and User.objects.filter(email=email).exists():
        return Response({'detail': 'Email already registered.'}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(username=username, email=email, password=password)
    staff_group, _ = Group.objects.get_or_create(name='Staff')
    user.groups.add(staff_group)

    code_obj.used_by = user
    code_obj.used_at = timezone.now()
    code_obj.save()

    return Response({'detail': 'Account created. You can now sign in.'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'roles': list(user.groups.values_list('name', flat=True)),
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/token/', SageTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/auth/me/', me, name='me'),
    path('api/auth/register/', register, name='register'),
    path('api/accounts/', include('accounts.urls')),
    path('api/banks/', include('banks.urls')),
    path('api/reports/', include('reports.urls')),
    path('api/journals/', include('journals.urls')),
    path('api/payables/', include('payables.urls')),
    path('api/receivables/', include('receivables.urls')),
    path('api/budget/', include('budget.urls')),
    path('api/users/', include('users.urls')),
]
