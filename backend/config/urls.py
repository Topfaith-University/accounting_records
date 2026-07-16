from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status


def _single_membership_or_none(user):
    """If the user belongs to exactly one company, return that Membership; else None."""
    memberships = list(user.memberships.select_related('company').all())
    return memberships[0] if len(memberships) == 1 else None


def _embed_company_claims(token, membership):
    if membership:
        token['company_id'] = str(membership.company_id)
        token['company_name'] = membership.company.name
        token['role'] = membership.role
    return token


class SageTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        # If the user belongs to exactly one company, embed it directly so login
        # is transparent for the common case. Users with 0 or >1 memberships get
        # a "pre-company" token; the frontend must call /api/auth/switch-company/
        # before hitting any company-scoped endpoint.
        _embed_company_claims(token, _single_membership_or_none(user))
        return token


class SageTokenObtainPairView(TokenObtainPairView):
    serializer_class = SageTokenObtainPairSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def switch_company(request):
    from users.models import Membership

    company_id = (request.data.get('company_id') or '').strip()
    if not company_id:
        return Response({'detail': 'company_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    membership = Membership.objects.select_related('company').filter(
        user=request.user, company_id=company_id,
    ).first()
    if not membership:
        return Response({'detail': 'You are not a member of that company.'}, status=status.HTTP_403_FORBIDDEN)

    token = RefreshToken.for_user(request.user)
    token['username'] = request.user.username
    _embed_company_claims(token, membership)

    return Response({'refresh': str(token), 'access': str(token.access_token)})


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """Join an existing company via a single-use invite code."""
    from django.contrib.auth.models import User
    from django.utils import timezone
    from users.models import InviteCode, Membership

    invite_code_str = (request.data.get('invite_code') or '').strip()
    code_obj = InviteCode.objects.select_related('company').filter(code=invite_code_str).first()
    if not code_obj or code_obj.status != 'active':
        return Response({'detail': 'Invalid or expired invite code.'}, status=status.HTTP_400_BAD_REQUEST)
    if not code_obj.company_id:
        return Response({'detail': 'This invite code is not linked to a company.'}, status=status.HTTP_400_BAD_REQUEST)

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
    Membership.objects.create(user=user, company=code_obj.company, role=code_obj.role)

    code_obj.used_by = user
    code_obj.used_at = timezone.now()
    code_obj.save()

    return Response({'detail': 'Account created. You can now sign in.'}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def register_company(request):
    """Create a brand-new company and its first user (who becomes that company's Admin)."""
    from django.contrib.auth.models import User
    from users.models import Company, Membership

    company_name = (request.data.get('company_name') or '').strip()
    username = (request.data.get('username') or '').strip()
    email = (request.data.get('email') or '').strip()
    password = request.data.get('password') or ''
    confirm_password = request.data.get('confirm_password') or ''

    if not company_name:
        return Response({'detail': 'Company name is required.'}, status=status.HTTP_400_BAD_REQUEST)
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
    company = Company.objects.create(name=company_name)
    Membership.objects.create(user=user, company=company, role='Admin')

    return Response({'detail': 'Company created. You can now sign in.'}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_company(request):
    """Add a Membership to the CURRENT logged-in user via an invite code — unlike
    `register`, this never creates a new User."""
    from django.utils import timezone
    from users.models import InviteCode, Membership

    invite_code_str = (request.data.get('invite_code') or '').strip()
    code_obj = InviteCode.objects.select_related('company').filter(code=invite_code_str).first()
    if not code_obj or code_obj.status != 'active':
        return Response({'detail': 'Invalid or expired invite code.'}, status=status.HTTP_400_BAD_REQUEST)
    if not code_obj.company_id:
        return Response({'detail': 'This invite code is not linked to a company.'}, status=status.HTTP_400_BAD_REQUEST)

    if Membership.objects.filter(user=request.user, company=code_obj.company).exists():
        return Response({'detail': 'You are already a member of this company.'}, status=status.HTTP_400_BAD_REQUEST)

    Membership.objects.create(user=request.user, company=code_obj.company, role=code_obj.role)

    code_obj.used_by = request.user
    code_obj.used_at = timezone.now()
    code_obj.save()

    return Response(
        {'detail': 'Joined company.', 'company_id': str(code_obj.company_id), 'company_name': code_obj.company.name},
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_company_for_current_user(request):
    """Create a brand-new company and add the CURRENT logged-in user as its Admin —
    unlike `register_company`, this never creates a new User."""
    from users.models import Company, Membership

    company_name = (request.data.get('company_name') or '').strip()
    if not company_name:
        return Response({'detail': 'Company name is required.'}, status=status.HTTP_400_BAD_REQUEST)

    company = Company.objects.create(name=company_name)
    Membership.objects.create(user=request.user, company=company, role='Admin')

    return Response(
        {'detail': 'Company created.', 'company_id': str(company.id), 'company_name': company.name},
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    memberships = list(user.memberships.select_related('company').all())
    active_company_id = request.auth.get('company_id') if request.auth else None
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'roles': list(user.groups.values_list('name', flat=True)),
        'active_company_id': active_company_id,
        'memberships': [
            {
                'company_id': str(m.company_id),
                'company_name': m.company.name,
                'role': m.role,
            }
            for m in memberships
        ],
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/token/', SageTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/auth/switch-company/', switch_company, name='switch_company'),
    path('api/auth/me/', me, name='me'),
    path('api/auth/register/', register, name='register'),
    path('api/auth/register-company/', register_company, name='register_company'),
    path('api/auth/join-company/', join_company, name='join_company'),
    path('api/auth/create-company/', create_company_for_current_user, name='create_company_for_current_user'),
    path('api/accounts/', include('accounts.urls')),
    path('api/banks/', include('banks.urls')),
    path('api/reports/', include('reports.urls')),
    path('api/journals/', include('journals.urls')),
    path('api/payables/', include('payables.urls')),
    path('api/receivables/', include('receivables.urls')),
    path('api/budget/', include('budget.urls')),
    path('api/users/', include('users.urls')),
]
