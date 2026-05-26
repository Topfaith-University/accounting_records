import io
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from . import services


def _pdf_response(template_name, context, filename):
    from weasyprint import HTML
    html = render_to_string(template_name, context)
    pdf = HTML(string=html).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def _xlsx_response(wb, filename):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trial_balance(request):
    date_from = request.query_params.get('date_from', '')
    date_to = request.query_params.get('date_to', '')
    fmt = request.query_params.get('format', 'json')
    if not date_from or not date_to:
        return JsonResponse({'detail': 'date_from and date_to are required.'}, status=400)

    rows = services.compute_trial_balance(date_from, date_to)
    ctx = {
        'rows': rows,
        'date_from': date_from,
        'date_to': date_to,
        'total_debits': round(sum(r['total_debits'] for r in rows), 2),
        'total_credits': round(sum(r['total_credits'] for r in rows), 2),
    }

    if fmt == 'pdf':
        return _pdf_response('reports/trial_balance.html', ctx, f'trial-balance-{date_from}-{date_to}.pdf')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = 'Trial Balance'
        ws.append(['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)', 'Balance (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for r in rows:
            ws.append([r['code'], r['name'], r['account_type'],
                       r['total_debits'], r['total_credits'], r['balance']])
        ws.append(['', 'TOTALS', '', ctx['total_debits'], ctx['total_credits'], ''])
        return _xlsx_response(wb, f'trial-balance-{date_from}-{date_to}.xlsx')
    return JsonResponse(ctx)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def income_statement(request):
    date_from = request.query_params.get('date_from', '')
    date_to = request.query_params.get('date_to', '')
    fmt = request.query_params.get('format', 'json')
    if not date_from or not date_to:
        return JsonResponse({'detail': 'date_from and date_to are required.'}, status=400)

    data = services.compute_income_statement(date_from, date_to)

    if fmt == 'pdf':
        return _pdf_response('reports/income_statement.html', data, f'income-statement-{date_from}-{date_to}.pdf')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = 'Income Statement'
        ws.append(['Account', 'Type', 'Amount (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.append(['REVENUE', '', ''])
        for r in data['revenue']:
            ws.append([r['name'], r['account_type'], r['balance']])
        ws.append(['Total Revenue', '', data['total_revenue']])
        ws.append(['COST OF SALES', '', ''])
        for r in data['cost_of_sales']:
            ws.append([r['name'], r['account_type'], r['balance']])
        ws.append(['Gross Profit', '', data['gross_profit']])
        ws.append(['EXPENSES', '', ''])
        for r in data['expenses']:
            ws.append([r['name'], r['account_type'], r['balance']])
        ws.append(['Total Expenses', '', data['total_expenses']])
        ws.append(['Net Surplus / (Deficit)', '', data['net_surplus']])
        return _xlsx_response(wb, f'income-statement-{date_from}-{date_to}.xlsx')
    return JsonResponse(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def balance_sheet(request):
    as_of_date = request.query_params.get('as_of_date', '')
    fmt = request.query_params.get('format', 'json')
    if not as_of_date:
        return JsonResponse({'detail': 'as_of_date is required.'}, status=400)

    data = services.compute_balance_sheet(as_of_date)

    if fmt == 'pdf':
        return _pdf_response('reports/balance_sheet.html', data, f'balance-sheet-{as_of_date}.pdf')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = 'Balance Sheet'
        ws.append(['Account', 'Type', 'Balance (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for section_label, items, total_key in [
            ('ASSETS', data['assets'], 'total_assets'),
            ('LIABILITIES', data['liabilities'], 'total_liabilities'),
            ('EQUITY', data['equity'], 'total_equity'),
        ]:
            ws.append([section_label, '', ''])
            for r in items:
                ws.append([r['name'], r['account_type'], r['balance']])
            ws.append([f'Total {section_label.title()}', '', data[total_key]])
        return _xlsx_response(wb, f'balance-sheet-{as_of_date}.xlsx')
    return JsonResponse(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def gl_detail(request):
    account_id = request.query_params.get('account_id', '')
    date_from = request.query_params.get('date_from', '')
    date_to = request.query_params.get('date_to', '')
    fmt = request.query_params.get('format', 'json')
    if not account_id or not date_from or not date_to:
        return JsonResponse({'detail': 'account_id, date_from, and date_to are required.'}, status=400)

    data = services.compute_gl_detail(account_id, date_from, date_to)
    if data is None:
        return JsonResponse({'detail': 'Account not found.'}, status=404)

    if fmt == 'pdf':
        return _pdf_response(
            'reports/gl_detail.html', data,
            f'gl-detail-{data["account_code"]}-{date_from}-{date_to}.pdf'
        )
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = f'GL {data["account_code"]}'
        ws.append(['Date', 'Reference', 'Description', 'Side', 'Amount (N)', 'Running Balance (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for line in data['lines']:
            ws.append([line['date'], line['reference'], line['entry_description'],
                       line['side'], line['amount'], line['running_balance']])
        ws.append(['', '', '', 'CLOSING BALANCE', '', data['closing_balance']])
        return _xlsx_response(wb, f'gl-detail-{data["account_code"]}-{date_from}-{date_to}.xlsx')
    return JsonResponse(data)
