from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import BankAccount, BankTransaction
from .serializers import BankAccountSerializer, BankReconciliationSerializer, BankTransactionSerializer


class BankAccountViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        accounts = BankAccount.nodes.filter(is_active=True)
        return Response(BankAccountSerializer(list(accounts), many=True).data)

    def retrieve(self, request, pk=None):
        account = BankAccount.nodes.get_or_none(bank_account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(BankAccountSerializer(account).data)

    def create(self, request):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = BankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bank_account = serializer.save()
        return Response(BankAccountSerializer(bank_account).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BankAccountSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(BankAccountSerializer(account).data)

    def destroy(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        account.is_active = False
        account.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request, pk=None):
        account = BankAccount.nodes.get_or_none(bank_account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from . import services
        lines = services.get_bank_gl_lines(pk)
        return Response({'bank_account_id': pk, 'lines': lines})

    @action(detail=True, methods=['get'], url_path='reconciliations')
    def reconciliations(self, request, pk=None):
        account = BankAccount.nodes.get_or_none(bank_account_id=pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from .models import BankReconciliation
        from .serializers import BankReconciliationSerializer
        # get all reconciliations for this bank account via Cypher
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (r:BankReconciliation)-[:FOR_ACCOUNT]->(ba:BankAccount {bank_account_id: $id}) "
            "RETURN r.reconciliation_id ORDER BY r.created_at DESC",
            {'id': pk}
        )
        recons = [BankReconciliation.nodes.get_or_none(reconciliation_id=row[0]) for row in results]
        recons = [r for r in recons if r is not None]
        return Response(BankReconciliationSerializer(recons, many=True).data)


class BankReconciliationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        from neomodel import db
        bank_account_id = request.query_params.get('bank_account_id')
        if bank_account_id:
            results, _ = db.cypher_query(
                "MATCH (r:BankReconciliation)-[:FOR_ACCOUNT]->(ba:BankAccount {bank_account_id: $id}) "
                "RETURN r.reconciliation_id ORDER BY r.created_at DESC",
                {'id': bank_account_id}
            )
        else:
            results, _ = db.cypher_query(
                "MATCH (r:BankReconciliation) RETURN r.reconciliation_id ORDER BY r.created_at DESC"
            )
        from .models import BankReconciliation
        recons = [BankReconciliation.nodes.get_or_none(reconciliation_id=row[0]) for row in results]
        return Response(BankReconciliationSerializer(
            [r for r in recons if r], many=True
        ).data)

    def retrieve(self, request, pk=None):
        from .models import BankReconciliation
        recon = BankReconciliation.nodes.get_or_none(reconciliation_id=pk)
        if not recon:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = BankReconciliationSerializer(recon).data
        ba = recon.bank_account.single()
        if ba:
            from . import services
            data['opening_balance'] = ba.opening_balance or 0.0
            data['bank_account_name'] = ba.name
            data['lines'] = services.get_bank_gl_lines(ba.bank_account_id, recon_id=pk)
        else:
            data['opening_balance'] = 0.0
            data['bank_account_name'] = ''
            data['lines'] = []
        return Response(data)

    def create(self, request):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        bank_account_id = request.data.get('bank_account_id')
        if not bank_account_id:
            return Response({'detail': 'bank_account_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        bank_account = BankAccount.nodes.get_or_none(bank_account_id=bank_account_id)
        if not bank_account:
            return Response({'detail': 'Bank account not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BankReconciliationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recon = serializer.save(
            bank_account=bank_account,
            created_by=request.user.username,
        )
        return Response(BankReconciliationSerializer(recon).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='toggle-line')
    def toggle_line(self, request, pk=None):
        from .models import BankReconciliation
        recon = BankReconciliation.nodes.get_or_none(reconciliation_id=pk)
        if not recon:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if recon.status != 'DRAFT':
            return Response({'detail': 'Cannot modify a completed reconciliation.'}, status=status.HTTP_400_BAD_REQUEST)
        line_id = request.data.get('line_id')
        if not line_id:
            return Response({'detail': 'line_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        from journals.models import JournalLine
        line = JournalLine.nodes.get_or_none(line_id=line_id)
        if not line:
            return Response({'detail': 'Journal line not found.'}, status=status.HTTP_404_NOT_FOUND)
        if recon.reconciled_lines.is_connected(line):
            recon.reconciled_lines.disconnect(line)
            reconciled = False
        else:
            recon.reconciled_lines.connect(line)
            reconciled = True
        return Response({'line_id': line_id, 'is_reconciled': reconciled})

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        from .models import BankReconciliation
        recon = BankReconciliation.nodes.get_or_none(reconciliation_id=pk)
        if not recon:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if recon.status != 'DRAFT':
            return Response({'detail': 'Already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        ba = recon.bank_account.single()
        opening = ba.opening_balance if ba else 0.0
        lines = list(recon.reconciled_lines.all())
        book_balance = opening
        for line in lines:
            if line.side == 'DEBIT':
                book_balance += line.amount
            else:
                book_balance -= line.amount
        if abs(round(book_balance, 2) - round(recon.statement_balance, 2)) > 0.01:
            diff = round(recon.statement_balance - book_balance, 2)
            return Response(
                {'detail': f'Unreconciled difference of ₦{diff:,.2f}. Tick all matching items first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        from datetime import datetime
        recon.status = 'COMPLETED'
        recon.completed_at = datetime.utcnow()
        recon.save()
        return Response(BankReconciliationSerializer(recon).data)


class BankTransactionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        bank_account_id = request.query_params.get('bank_account_id')
        if bank_account_id:
            from neomodel import db
            results, _ = db.cypher_query(
                "MATCH (t:BankTransaction)-[:FROM_BANK]->(ba:BankAccount {bank_account_id: $id}) "
                "RETURN t.transaction_id ORDER BY t.created_at DESC",
                {'id': bank_account_id}
            )
            txns = [BankTransaction.nodes.get_or_none(transaction_id=row[0]) for row in results]
        else:
            txns = list(BankTransaction.nodes.all())
            txns = sorted(txns, key=lambda t: str(t.created_at), reverse=True)
        return Response(BankTransactionSerializer([t for t in txns if t], many=True).data)

    def retrieve(self, request, pk=None):
        txn = BankTransaction.nodes.get_or_none(transaction_id=pk)
        if not txn:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(BankTransactionSerializer(txn).data)

    def create(self, request):
        serializer = BankTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from . import services
        try:
            txn = services.create_bank_transaction(
                transaction_type=data['transaction_type'],
                txn_date=data['date'],
                description=data.get('description', ''),
                source_bank_id=data['source_bank_id'],
                destination_bank_id=data.get('destination_bank_id'),
                splits=data.get('splits', []),
                amount=data.get('transfer_amount'),
                created_by=request.user.username,
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BankTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)
