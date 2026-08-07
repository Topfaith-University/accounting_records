from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.auth import get_active_company_id
from config.pagination import parse_pagination_params, paginate_nodeset, paginated_response
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
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = BankAccountSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        bank_account = serializer.save()
        return Response(BankAccountSerializer(bank_account).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = BankAccount.nodes.get_or_none(bank_account_id=pk, company_id=company_id)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BankAccountSerializer(account, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(BankAccountSerializer(account).data)

    def destroy(self, request, pk=None):
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
            return pdf_response(request, 'banks/bank_account_list.html', ctx, 'bank-accounts')
        return xlsx_response(request, headers, rows, 'bank-accounts', 'Bank Accounts')

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

    def _build_transactions_qs(self, company_id, date_from=None, date_to=None):
        """No bank_account_id filter — a plain neomodel NodeSet, pageable via
        len(qs)/qs[skip:limit] without materializing the full company dataset.
        """
        from datetime import datetime
        qs = BankTransaction.nodes.filter(company_id=company_id)
        if date_from:
            try:
                qs = qs.filter(date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
            except ValueError:
                pass
        if date_to:
            try:
                qs = qs.filter(date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
            except ValueError:
                pass
        return qs.order_by('-created_at')

    def _cypher_date_conditions(self, date_from=None, date_to=None):
        """Relationship-traversal (bank_account_id) branch can't be a simple
        NodeSet filter, so it stays raw Cypher. Returns (conditions, params)
        for the optional date WHERE clauses shared by list() and export().
        """
        # DateProperty is stored as an ISO 'YYYY-MM-DD' string, not a native
        # Neo4j Date — comparing it to date($x) is a type mismatch that
        # silently matches nothing, so compare the strings directly.
        conditions = []
        params = {}
        if date_from:
            conditions.append("t.date >= $date_from")
            params['date_from'] = date_from
        if date_to:
            conditions.append("t.date <= $date_to")
            params['date_to'] = date_to
        return conditions, params

    def _paginated_bank_account_transactions(self, company_id, bank_account_id, date_from, date_to, page, page_size):
        from neomodel import db
        conditions, date_params = self._cypher_date_conditions(date_from, date_to)
        where_clause = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
        base_match = (
            "MATCH (t:BankTransaction {company_id: $company_id})-[:FROM_BANK|TO_BANK]->"
            "(ba:BankAccount {bank_account_id: $id})"
        )
        params = {'id': bank_account_id, 'company_id': company_id, **date_params}

        count_results, _ = db.cypher_query(
            f"{base_match}{where_clause} RETURN count(DISTINCT t)", params
        )
        total = int(count_results[0][0])

        skip = (page - 1) * page_size
        id_results, _ = db.cypher_query(
            f"{base_match}{where_clause} RETURN DISTINCT t.transaction_id, t.created_at "
            "ORDER BY t.created_at DESC SKIP $skip LIMIT $limit",
            {**params, 'skip': skip, 'limit': page_size},
        )
        ordered_ids = [row[0] for row in id_results]
        if not ordered_ids:
            return total, []
        # Batch-fetch the page in one query instead of one get_or_none() per row.
        nodes = list(BankTransaction.nodes.filter(transaction_id__in=ordered_ids))
        id_order = {tid: i for i, tid in enumerate(ordered_ids)}
        nodes.sort(key=lambda t: id_order[t.transaction_id])
        return total, nodes

    def _export_bank_account_transactions(self, company_id, bank_account_id, date_from, date_to):
        from neomodel import db
        conditions, date_params = self._cypher_date_conditions(date_from, date_to)
        where_clause = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
        params = {'id': bank_account_id, 'company_id': company_id, **date_params}
        results, _ = db.cypher_query(
            "MATCH (t:BankTransaction {company_id: $company_id})-[:FROM_BANK|TO_BANK]->"
            f"(ba:BankAccount {{bank_account_id: $id}}){where_clause} "
            "RETURN DISTINCT t.transaction_id, t.created_at ORDER BY t.created_at DESC",
            params,
        )
        txns = [BankTransaction.nodes.get_or_none(transaction_id=row[0]) for row in results]
        return [t for t in txns if t]

    def list(self, request):
        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id') or None
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        page, page_size = parse_pagination_params(request)

        if bank_account_id:
            total, txns = self._paginated_bank_account_transactions(
                company_id, bank_account_id, date_from, date_to, page, page_size
            )
        else:
            qs = self._build_transactions_qs(company_id, date_from, date_to)
            total, txns = paginate_nodeset(qs, page, page_size)

        return Response(paginated_response(total, page, page_size, BankTransactionSerializer(txns, many=True).data))

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        import csv, io
        from django.http import HttpResponse

        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id') or None
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        fmt = request.query_params.get('format', 'csv')

        if bank_account_id:
            txns = self._export_bank_account_transactions(company_id, bank_account_id, date_from, date_to)
        else:
            txns = list(self._build_transactions_qs(company_id, date_from, date_to))
        data = BankTransactionSerializer(txns, many=True).data

        from . import services
        account_names = services.get_account_names_for_transactions(
            [t.transaction_id for t in txns], company_id
        )

        headers = ['Reference', 'Date', 'Bank', 'Type', 'Account', 'Description', 'Amount']
        rows = [
            [r['reference'], str(r['date']), r.get('source_bank_name', ''),
             r['transaction_type'], account_names.get(r['transaction_id'], ''),
             r.get('description', ''), r['amount']]
            for r in data
        ]

        if fmt == 'xlsx':
            from config.export_utils import xlsx_response
            return xlsx_response(request, headers, rows, 'bank-transactions', 'Bank Transactions')

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
