from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.auth import get_active_company_id
from .models import BankAccount, BankTransaction
from .serializers import BankAccountSerializer, BankReconciliationSerializer, BankTransactionSerializer


class BankAccountViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        accounts = BankAccount.nodes.filter(is_active=True, company_id=company_id)
        return Response(BankAccountSerializer(list(accounts), many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk, company_id=company_id)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(BankAccountSerializer(account).data)

    def create(self, request):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = BankAccountSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        bank_account = serializer.save()
        return Response(BankAccountSerializer(bank_account).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        company_id = get_active_company_id(request)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk, company_id=company_id)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BankAccountSerializer(account, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(BankAccountSerializer(account).data)

    def destroy(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        company_id = get_active_company_id(request)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk, company_id=company_id)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        account.is_active = False
        account.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk, company_id=company_id)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from . import services
        lines = services.get_bank_gl_lines(pk, company_id)
        return Response({'bank_account_id': pk, 'lines': lines})

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        accounts = sorted(BankAccount.nodes.filter(is_active=True, company_id=company_id), key=lambda a: a.name)
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Name', 'Bank', 'Account No.', 'Opening Balance (N)', 'Current Balance (N)']
        data = BankAccountSerializer(list(accounts), many=True).data
        rows = [
            [r['name'], r['bank_name'], r['account_number'], r['opening_balance'], r.get('current_balance')]
            for r in data
        ]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'bank_name', 'account_number', 'opening_balance', 'current_balance'], r
            )) for r in rows]}
            return pdf_response('banks/bank_account_list.html', ctx, 'bank-accounts')
        return xlsx_response(headers, rows, 'bank-accounts', 'Bank Accounts')

    @action(detail=True, methods=['get'], url_path='reconciliations')
    def reconciliations(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk, company_id=company_id)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from .models import BankReconciliation
        from .serializers import BankReconciliationSerializer
        # get all reconciliations for this bank account via Cypher
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (r:BankReconciliation {company_id: $company_id})-[:FOR_ACCOUNT]->(ba:BankAccount {bank_account_id: $id}) "
            "RETURN r.reconciliation_id ORDER BY r.created_at DESC",
            {'id': pk, 'company_id': company_id}
        )
        recons = [BankReconciliation.nodes.get_or_none(reconciliation_id=row[0]) for row in results]
        recons = [r for r in recons if r is not None]
        return Response(BankReconciliationSerializer(recons, many=True).data)


class BankReconciliationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        from neomodel import db
        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id')
        if bank_account_id:
            results, _ = db.cypher_query(
                "MATCH (r:BankReconciliation {company_id: $company_id})-[:FOR_ACCOUNT]->(ba:BankAccount {bank_account_id: $id}) "
                "RETURN r.reconciliation_id ORDER BY r.created_at DESC",
                {'id': bank_account_id, 'company_id': company_id}
            )
        else:
            results, _ = db.cypher_query(
                "MATCH (r:BankReconciliation {company_id: $company_id}) RETURN r.reconciliation_id ORDER BY r.created_at DESC",
                {'company_id': company_id}
            )
        from .models import BankReconciliation
        recons = [BankReconciliation.nodes.get_or_none(reconciliation_id=row[0]) for row in results]
        return Response(BankReconciliationSerializer(
            [r for r in recons if r], many=True
        ).data)

    def retrieve(self, request, pk=None):
        from .models import BankReconciliation
        company_id = get_active_company_id(request)
        recon = BankReconciliation.nodes.get_or_none(reconciliation_id=pk, company_id=company_id)
        if not recon:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = BankReconciliationSerializer(recon).data
        ba = recon.bank_account.single()
        if ba:
            from . import services
            data['opening_balance'] = ba.opening_balance or 0.0
            data['bank_account_name'] = ba.name
            data['lines'] = services.get_bank_gl_lines(ba.bank_account_id, company_id, recon_id=pk)
        else:
            data['opening_balance'] = 0.0
            data['bank_account_name'] = ''
            data['lines'] = []
        return Response(data)

    def create(self, request):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        company_id = get_active_company_id(request)
        bank_account_id = request.data.get('bank_account_id')
        if not bank_account_id:
            return Response({'detail': 'bank_account_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        bank_account = BankAccount.nodes.get_or_none(bank_account_id=bank_account_id, company_id=company_id)
        if not bank_account:
            return Response({'detail': 'Bank account not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BankReconciliationSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        recon = serializer.save(
            bank_account=bank_account,
            created_by=request.user.username,
        )
        return Response(BankReconciliationSerializer(recon).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='toggle-line')
    def toggle_line(self, request, pk=None):
        from .models import BankReconciliation
        company_id = get_active_company_id(request)
        recon = BankReconciliation.nodes.get_or_none(reconciliation_id=pk, company_id=company_id)
        if not recon:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if recon.status != 'DRAFT':
            return Response({'detail': 'Cannot modify a completed reconciliation.'}, status=status.HTTP_400_BAD_REQUEST)
        line_id = request.data.get('line_id')
        if not line_id:
            return Response({'detail': 'line_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        from journals.models import JournalLine
        line = JournalLine.nodes.get_or_none(line_id=line_id, company_id=company_id)
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
        company_id = get_active_company_id(request)
        recon = BankReconciliation.nodes.get_or_none(reconciliation_id=pk, company_id=company_id)
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

    def _query_transactions(self, company_id, bank_account_id=None, date_from=None, date_to=None):
        from neomodel import db
        if bank_account_id:
            results, _ = db.cypher_query(
                "MATCH (t:BankTransaction {company_id: $company_id})-[:FROM_BANK|TO_BANK]->(ba:BankAccount {bank_account_id: $id}) "
                "RETURN DISTINCT t.transaction_id, t.created_at ORDER BY t.created_at DESC",
                {'id': bank_account_id, 'company_id': company_id}
            )
            txns = [BankTransaction.nodes.get_or_none(transaction_id=row[0]) for row in results]
        else:
            txns = list(BankTransaction.nodes.filter(company_id=company_id))
            txns = sorted(txns, key=lambda t: str(t.created_at), reverse=True)
        txns = [t for t in txns if t]
        if date_from:
            txns = [t for t in txns if str(t.date) >= date_from]
        if date_to:
            txns = [t for t in txns if str(t.date) <= date_to]
        return txns

    def list(self, request):
        company_id = get_active_company_id(request)
        txns = self._query_transactions(
            company_id,
            bank_account_id=request.query_params.get('bank_account_id') or None,
            date_from=request.query_params.get('date_from') or None,
            date_to=request.query_params.get('date_to') or None,
        )
        return Response(BankTransactionSerializer(txns, many=True).data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        import csv, io
        from django.http import HttpResponse

        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id') or None
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        fmt = request.query_params.get('format', 'csv')

        txns = self._query_transactions(company_id, bank_account_id, date_from, date_to)
        data = BankTransactionSerializer(txns, many=True).data

        headers = ['Reference', 'Date', 'Bank', 'Type', 'Description', 'Amount']
        rows = [
            [r['reference'], str(r['date']), r.get('source_bank_name', ''),
             r['transaction_type'], r.get('description', ''), r['amount']]
            for r in data
        ]

        if fmt == 'xlsx':
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'Bank Transactions'
            ws.append(headers)
            for row in rows:
                ws.append(row)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            response = HttpResponse(
                buf.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = 'attachment; filename="bank-transactions.xlsx"'
            return response

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(rows)
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="bank-transactions.csv"'
        return response

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        txn = BankTransaction.nodes.get_or_none(transaction_id=pk, company_id=company_id)
        if not txn:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(BankTransactionSerializer(txn).data)

    def create(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = BankTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from . import services
        try:
            txn = services.create_bank_transaction(
                company_id=company_id,
                transaction_type=data['transaction_type'],
                txn_date=data['date'],
                description=data.get('description', ''),
                source_bank_id=data['source_bank_id'],
                destination_bank_id=data.get('destination_bank_id'),
                splits=data.get('splits', []),
                amount=data.get('transfer_amount'),
                created_by=request.user.username,
                vendor_id=data.get('vendor_id') or None,
                customer_id=data.get('customer_id') or None,
                reference=request.data.get('reference') or None,
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BankTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='import')
    def import_csv(self, request):
        import csv, io
        from datetime import datetime

        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)

        bank_account_id = request.data.get('bank_account_id', '').strip()
        default_acct_id = request.data.get('default_account_id', '').strip()
        date_format_key = request.data.get('date_format', 'dd/mm/yyyy')
        date_range_type = request.data.get('date_range_type', 'ALL')
        date_from_str   = request.data.get('date_from', '')
        date_to_str     = request.data.get('date_to', '')
        csv_file        = request.FILES.get('file')

        if not bank_account_id or not default_acct_id or not csv_file:
            return Response(
                {'detail': 'bank_account_id, default_account_id, and file are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fmt_map = {'dd/mm/yyyy': '%d/%m/%Y', 'mm/dd/yyyy': '%m/%d/%Y', 'yyyy-mm-dd': '%Y-%m-%d'}
        py_fmt = fmt_map.get(date_format_key, '%d/%m/%Y')

        date_from = date_to = None
        if date_range_type == 'DATE_RANGE':
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                date_to   = datetime.strptime(date_to_str,   '%Y-%m-%d').date()
            except ValueError:
                return Response({'detail': 'Invalid date_from/date_to.'}, status=status.HTTP_400_BAD_REQUEST)

        from . import services
        created = skipped = 0
        errors = []

        text = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader, start=2):   # row 1 is header
            date_str    = (row.get('Date') or '').strip()
            description = (row.get('Description') or '').strip()
            amount_str  = (row.get('Amount') or '').strip()

            if not date_str and not amount_str:   # trailing blank rows
                continue

            try:
                txn_date = datetime.strptime(date_str, py_fmt).date()
            except ValueError:
                errors.append(f'Row {i}: invalid date "{date_str}"')
                skipped += 1
                continue

            try:
                amount = float(amount_str.replace(',', ''))
            except ValueError:
                errors.append(f'Row {i}: invalid amount "{amount_str}"')
                skipped += 1
                continue

            if amount == 0:
                skipped += 1
                continue

            if date_from and (txn_date < date_from or txn_date > date_to):
                skipped += 1
                continue

            txn_type = 'RECEIPT' if amount > 0 else 'PAYMENT'
            try:
                services.create_bank_transaction(
                    company_id=company_id,
                    transaction_type=txn_type,
                    txn_date=txn_date,
                    description=description,
                    source_bank_id=bank_account_id,
                    destination_bank_id=None,
                    splits=[{'account_id': default_acct_id, 'amount': abs(amount), 'description': ''}],
                    amount=None,
                    created_by=request.user.username,
                )
                created += 1
            except Exception as e:
                errors.append(f'Row {i}: {e}')
                skipped += 1

        return Response({'created': created, 'skipped': skipped, 'errors': errors})
