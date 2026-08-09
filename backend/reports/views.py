from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from config.auth import get_active_company_id
from config.export_utils import pdf_response, xlsx_response
from . import services


def _parse_date(value: str, param_name: str):
    from datetime import date
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trial_balance(request):
    company_id = get_active_company_id(request)
    if not company_id:
        return JsonResponse({'detail': 'No active company.'}, status=400)
    date_from = request.query_params.get('date_from', '')
    date_to = request.query_params.get('date_to', '')
    fmt = request.query_params.get('format', 'json')
    if not date_from or not date_to:
        return JsonResponse({'detail': 'date_from and date_to are required.'}, status=400)
    if not _parse_date(date_from, 'date_from') or not _parse_date(date_to, 'date_to'):
        return JsonResponse({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    rows = services.compute_trial_balance(company_id, date_from, date_to)
    ctx = {
        'rows': rows,
        'date_from': date_from,
        'date_to': date_to,
        'total_debits': round(sum(r['total_debits'] for r in rows), 2),
        'total_credits': round(sum(r['total_credits'] for r in rows), 2),
    }

    if fmt == 'pdf':
        pdf_rows = []
        for r in rows:
            d = max(0.0, r['total_debits'] - r['total_credits'])
            c = max(0.0, r['total_credits'] - r['total_debits'])
            pdf_rows.append({**r, 'display_debit': round(d, 2), 'display_credit': round(c, 2)})
        pdf_ctx = {
            'rows': pdf_rows,
            'date_from': date_from,
            'date_to': date_to,
            'total_debits': round(sum(r['display_debit'] for r in pdf_rows), 2),
            'total_credits': round(sum(r['display_credit'] for r in pdf_rows), 2),
        }
        return pdf_response(request, 'reports/trial_balance.html', pdf_ctx, f'trial-balance-{date_from}-{date_to}')
    if fmt == 'xlsx':
        headers = ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)']
        xlsx_rows = []
        for r in rows:
            d = max(0.0, r['total_debits'] - r['total_credits'])
            c = max(0.0, r['total_credits'] - r['total_debits'])
            xlsx_rows.append([r['code'], r['name'], r['account_type'],
                               round(d, 2) if d > 0 else None,
                               round(c, 2) if c > 0 else None])
        total_d = round(sum(max(0.0, r['total_debits'] - r['total_credits']) for r in rows), 2)
        total_c = round(sum(max(0.0, r['total_credits'] - r['total_debits']) for r in rows), 2)
        xlsx_rows.append(['', 'TOTALS', '', total_d, total_c])
        return xlsx_response(request, headers, xlsx_rows, f'trial-balance-{date_from}-{date_to}', 'Trial Balance')
    return JsonResponse(ctx)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def income_statement(request):
    company_id = get_active_company_id(request)
    if not company_id:
        return JsonResponse({'detail': 'No active company.'}, status=400)
    date_from = request.query_params.get('date_from', '')
    date_to = request.query_params.get('date_to', '')
    fmt = request.query_params.get('format', 'json')
    if not date_from or not date_to:
        return JsonResponse({'detail': 'date_from and date_to are required.'}, status=400)
    if not _parse_date(date_from, 'date_from') or not _parse_date(date_to, 'date_to'):
        return JsonResponse({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    data = services.compute_income_statement(company_id, date_from, date_to)

    if fmt == 'pdf':
        return pdf_response(request, 'reports/income_statement.html', data, f'income-statement-{date_from}-{date_to}')
    if fmt == 'xlsx':
        headers = ['Account', 'Type', 'Amount (N)']
        xlsx_rows = [['REVENUE', '', '']]
        xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in data['revenue']]
        xlsx_rows.append(['Total Revenue', '', data['total_revenue']])
        xlsx_rows.append(['COST OF SALES', '', ''])
        xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in data['cost_of_sales']]
        xlsx_rows.append(['Gross Profit', '', data['gross_profit']])
        xlsx_rows.append(['EXPENSES', '', ''])
        xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in data['expenses']]
        xlsx_rows.append(['Total Expenses', '', data['total_expenses']])
        xlsx_rows.append(['Net Surplus / (Deficit)', '', data['net_surplus']])
        return xlsx_response(request, headers, xlsx_rows, f'income-statement-{date_from}-{date_to}', 'Income Statement')
    return JsonResponse(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def balance_sheet(request):
    company_id = get_active_company_id(request)
    if not company_id:
        return JsonResponse({'detail': 'No active company.'}, status=400)
    as_of_date = request.query_params.get('as_of_date', '')
    fmt = request.query_params.get('format', 'json')
    if not as_of_date:
        return JsonResponse({'detail': 'as_of_date is required.'}, status=400)
    if not _parse_date(as_of_date, 'as_of_date'):
        return JsonResponse({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    data = services.compute_balance_sheet(company_id, as_of_date)

    if fmt == 'pdf':
        return pdf_response(request, 'reports/balance_sheet.html', data, f'balance-sheet-{as_of_date}')
    if fmt == 'xlsx':
        headers = ['Account', 'Type', 'Balance (N)']
        xlsx_rows = []
        for section_label, items, total_key in [
            ('ASSETS', data['assets'], 'total_assets'),
            ('LIABILITIES', data['liabilities'], 'total_liabilities'),
            ('EQUITY', data['equity'], 'total_equity'),
        ]:
            xlsx_rows.append([section_label, '', ''])
            xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in items]
            xlsx_rows.append([f'Total {section_label.title()}', '', data[total_key]])
        return xlsx_response(request, headers, xlsx_rows, f'balance-sheet-{as_of_date}', 'Balance Sheet')
    return JsonResponse(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def gl_detail(request):
    company_id = get_active_company_id(request)
    if not company_id:
        return JsonResponse({'detail': 'No active company.'}, status=400)
    account_id = request.query_params.get('account_id', '')
    date_from = request.query_params.get('date_from', '')
    date_to = request.query_params.get('date_to', '')
    fmt = request.query_params.get('format', 'json')
    if not account_id or not date_from or not date_to:
        return JsonResponse({'detail': 'account_id, date_from, and date_to are required.'}, status=400)
    if not _parse_date(date_from, 'date_from') or not _parse_date(date_to, 'date_to'):
        return JsonResponse({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    data = services.compute_gl_detail(company_id, account_id, date_from, date_to)
    if data is None:
        return JsonResponse({'detail': 'Account not found.'}, status=404)

    if fmt == 'pdf':
        return pdf_response(
            request, 'reports/gl_detail.html', data,
            f'gl-detail-{data["account_code"]}-{date_from}-{date_to}'
        )
    if fmt == 'xlsx':
        headers = ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)']
        xlsx_rows = [
            [line['date'], line['reference'], line['entry_description'],
             line['entry_type'] or 'MANUAL', line['side'], line['amount'], line['running_balance']]
            for line in data['lines']
        ]
        xlsx_rows.append(['', '', '', '', 'CLOSING BALANCE', '', data['closing_balance']])
        return xlsx_response(
            request, headers, xlsx_rows,
            f'gl-detail-{data["account_code"]}-{date_from}-{date_to}', f'GL {data["account_code"]}'
        )
    return JsonResponse(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    from django.db.models import Sum, F
    from journals.models import JournalEntry
    from payables.models import PurchaseInvoice
    from receivables.models import SalesInvoice

    company_id = get_active_company_id(request)
    if not company_id:
        return JsonResponse({'detail': 'No active company.'}, status=400)

    ASSET_TYPES = {'Current Assets', 'Non-Current Assets'}
    LIABILITY_TYPES = {'Current Liabilities', 'Non-Current Liabilities'}

    accounts = services._balances_by_account(company_id)
    total_assets = 0.0
    total_liabilities = 0.0
    for a in accounts:
        debits = float(a.total_debits or 0)
        credits = float(a.total_credits or 0)
        balance = (debits - credits) if a.normal_balance == 'DEBIT' else (credits - debits)
        if a.account_type in ASSET_TYPES:
            total_assets += balance
        elif a.account_type in LIABILITY_TYPES:
            total_liabilities += balance

    # AP outstanding: POSTED or PARTIAL PurchaseInvoices ('PARTIAL' isn't an
    # actual status choice — pre-existing dead condition carried over as-is).
    ap_outstanding = PurchaseInvoice.objects.filter(
        company_id=company_id, status__in=['POSTED', 'PARTIAL'],
    ).aggregate(total=Sum(F('total_amount') - F('amount_paid')))['total'] or 0.0

    # AR outstanding: POSTED or PARTIAL SalesInvoices
    ar_outstanding = SalesInvoice.objects.filter(
        company_id=company_id, status__in=['POSTED', 'PARTIAL'],
    ).aggregate(total=Sum(F('total_amount') - F('amount_received')))['total'] or 0.0

    recent_entries = [
        {
            'entry_id': e.entry_id,
            'reference': e.reference,
            'date': str(e.date),
            'description': e.description,
            'total_debit': e.total_debit or 0.0,
        }
        for e in JournalEntry.objects.filter(
            company_id=company_id, status='POSTED',
        ).order_by('-date', '-created_at')[:10]
    ]

    return JsonResponse({
        'total_assets': round(total_assets, 2),
        'total_liabilities': round(total_liabilities, 2),
        'net_equity': round(total_assets - total_liabilities, 2),
        'ap_outstanding': round(ap_outstanding, 2),
        'ar_outstanding': round(ar_outstanding, 2),
        'recent_entries': recent_entries,
    })
