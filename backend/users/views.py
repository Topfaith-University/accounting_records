from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from config.auth import get_active_company_id, is_admin
from .models import InviteCode, Company, Membership, ROLE_CHOICES

VALID_ROLES = {choice[0] for choice in ROLE_CHOICES}


def _serialize_member(m):
    return {
        'membership_id': m.id,
        'user_id': m.user_id,
        'username': m.user.username,
        'email': m.user.email,
        'role': m.role,
        'created_at': m.created_at.isoformat(),
    }


def _serialize(code):
    return {
        'id': code.id,
        'code': code.code,
        'role': code.role,
        'status': code.status,
        'created_by': code.created_by.username if code.created_by else None,
        'created_at': code.created_at.isoformat(),
        'expires_at': code.expires_at.isoformat(),
        'used_by': code.used_by.username if code.used_by else None,
        'used_at': code.used_at.isoformat() if code.used_at else None,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def invite_codes(request):
    if not is_admin(request):
        return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    company_id = get_active_company_id(request)
    if not company_id:
        return Response({'detail': 'No active company. Switch to a company first.'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'GET':
        codes = InviteCode.objects.filter(company_id=company_id)
        return Response([_serialize(c) for c in codes])

    role = (request.data.get('role') or 'Staff').strip()
    if role not in VALID_ROLES:
        return Response({'detail': f'role must be one of {sorted(VALID_ROLES)}.'}, status=status.HTTP_400_BAD_REQUEST)

    company = Company.objects.get(id=company_id)
    code = InviteCode.generate(request.user, company, role=role)
    return Response(_serialize(code), status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def revoke_invite_code(request, pk):
    if not is_admin(request):
        return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    company_id = get_active_company_id(request)
    code = InviteCode.objects.filter(pk=pk, company_id=company_id).first()
    if not code:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if code.status == 'used':
        return Response({'detail': 'Cannot revoke a used code.'}, status=status.HTTP_400_BAD_REQUEST)

    code.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def members(request):
    """List every user who belongs to the active company, with their role."""
    if not is_admin(request):
        return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    company_id = get_active_company_id(request)
    if not company_id:
        return Response({'detail': 'No active company. Switch to a company first.'}, status=status.HTTP_400_BAD_REQUEST)

    memberships = Membership.objects.filter(company_id=company_id).select_related('user').order_by('user__username')
    return Response([_serialize_member(m) for m in memberships])


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_member_role(request, pk):
    """Change another member's role within the active company. Refuses to demote
    the company's only remaining Admin, so it can never be left with zero Admins."""
    if not is_admin(request):
        return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    company_id = get_active_company_id(request)
    membership = Membership.objects.filter(pk=pk, company_id=company_id).select_related('user').first()
    if not membership:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    role = (request.data.get('role') or '').strip()
    if role not in VALID_ROLES:
        return Response({'detail': f'role must be one of {sorted(VALID_ROLES)}.'}, status=status.HTTP_400_BAD_REQUEST)

    if membership.role == 'Admin' and role != 'Admin':
        other_admins = Membership.objects.filter(company_id=company_id, role='Admin').exclude(pk=membership.pk).count()
        if other_admins == 0:
            return Response(
                {'detail': 'Cannot change role: this is the only Admin in the company.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    membership.role = role
    membership.save()
    return Response(_serialize_member(membership))
