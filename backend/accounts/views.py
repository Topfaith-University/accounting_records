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
        serializer = AccountSerializer(data=request.data, context={'request': request})
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
        from .services import compute_account_balance
        as_of_date = request.query_params.get('date')
        bal = compute_account_balance(pk, as_of_date)
        return Response({'account_id': pk, 'balance': bal})

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request, pk=None):
        account = Account.nodes.get_or_none(account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from neomodel import db
        params = {'account_id': pk}
        query = """
            MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a:Account {account_id: $account_id})
            WHERE e.status = 'POSTED'
            RETURN e.entry_id, e.reference, e.date, e.description, l.side, l.amount, l.description, e.entry_type
            ORDER BY e.date DESC
        """
        results, _ = db.cypher_query(query, params)
        entries = [
            {
                'entry_id': r[0], 'reference': r[1], 'date': str(r[2]),
                'entry_description': r[3], 'side': r[4],
                'amount': r[5], 'line_description': r[6],
                'entry_type': r[7],
            }
            for r in results
        ]
        return Response({'account_id': pk, 'entries': entries})
