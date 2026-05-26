from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Account
from .serializers import AccountSerializer
from .enums import AccountType


class AccountViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        accounts = Account.nodes.filter(is_active=True)
        account_type = request.query_params.get('account_type')
        if account_type:
            accounts = [a for a in accounts if a.account_type == account_type]
        serializer = AccountSerializer(list(accounts), many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        account = Account.nodes.get_or_none(account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AccountSerializer(account).data)

    def create(self, request):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = AccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(AccountSerializer(account).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        account = Account.nodes.get_or_none(account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AccountSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(AccountSerializer(account).data)

    def destroy(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        account = Account.nodes.get_or_none(account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if account.is_system:
            return Response({'detail': 'System accounts cannot be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        account.is_active = False
        account.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='types')
    def types(self, request):
        return Response({'account_types': [t.value for t in AccountType]})

    @action(detail=True, methods=['get'], url_path='balance')
    def balance(self, request, pk=None):
        account = Account.nodes.get_or_none(account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'account_id': pk, 'balance': 0.0})

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request, pk=None):
        return Response({'account_id': pk, 'entries': []})
