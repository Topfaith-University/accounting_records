from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import InviteCode


def _is_admin(user):
    return user.is_staff or user.groups.filter(name__in=['Admin', 'Manager']).exists()


def _serialize(code):
    return {
        'id': code.id,
        'code': code.code,
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
    if not _is_admin(request.user):
        return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        codes = InviteCode.objects.all()
        return Response([_serialize(c) for c in codes])

    code = InviteCode.generate(request.user)
    return Response(_serialize(code), status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def revoke_invite_code(request, pk):
    if not _is_admin(request.user):
        return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    code = InviteCode.objects.filter(pk=pk).first()
    if not code:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if code.status == 'used':
        return Response({'detail': 'Cannot revoke a used code.'}, status=status.HTTP_400_BAD_REQUEST)

    code.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
