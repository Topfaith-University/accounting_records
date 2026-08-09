from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from config.auth import get_active_company_id
from .models import Account
from .serializers import AccountSerializer
from .enums import AccountType


class AccountViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        accounts = Account.objects.filter(is_active=True, company_id=company_id)
        account_type = request.query_params.get('account_type')
        if account_type:
            accounts = accounts.filter(account_type=account_type)
        serializer = AccountSerializer(list(accounts), many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = Account.objects.filter(account_id=pk, company_id=company_id).first()
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AccountSerializer(account).data)

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = AccountSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(AccountSerializer(account).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = Account.objects.filter(account_id=pk, company_id=company_id).first()
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AccountSerializer(account, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(AccountSerializer(account).data)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = Account.objects.filter(account_id=pk, company_id=company_id).first()
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

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        accounts = Account.objects.filter(is_active=True, company_id=company_id).order_by('code')
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Code', 'Name', 'Type', 'Normal Balance', 'Balance (N)']
        from .services import compute_account_balance
        rows = [
            [a.code, a.name, a.account_type, a.normal_balance, compute_account_balance(a.account_id)]
            for a in accounts
        ]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['code', 'name', 'account_type', 'normal_balance', 'balance'], r)) for r in rows]}
            return pdf_response(request, 'accounts/account_list.html', ctx, 'accounts')
        return xlsx_response(request, headers, rows, 'accounts', 'Accounts')

    @action(detail=True, methods=['get'], url_path='balance')
    def balance(self, request, pk=None):
        company_id = get_active_company_id(request)
        account = Account.objects.filter(account_id=pk, company_id=company_id).first()
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from .services import compute_account_balance
        as_of_date = request.query_params.get('date')
        bal = compute_account_balance(pk, as_of_date)
        return Response({'account_id': pk, 'balance': bal})

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request, pk=None):
        from journals.models import JournalLine
        company_id = get_active_company_id(request)
        account = Account.objects.filter(account_id=pk, company_id=company_id).first()
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        lines = (
            JournalLine.objects
            .filter(account_id=pk, entry__company_id=company_id, entry__status='POSTED')
            .select_related('entry')
            .order_by('-entry__date')
        )
        entries = [
            {
                'entry_id': line.entry.entry_id,
                'reference': line.entry.reference,
                'date': str(line.entry.date),
                'entry_description': line.entry.description,
                'side': line.side,
                'amount': line.amount,
                'line_description': line.description,
                'entry_type': line.entry.entry_type,
            }
            for line in lines
        ]
        return Response({'account_id': pk, 'entries': entries})
