from datetime import datetime

from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.auth import get_active_company_id
from config.pagination import parse_pagination_params, paginate_queryset, paginated_response
from .models import JournalEntry, FiscalYear, AccountingPeriod
from .serializers import (
    JournalEntrySerializer, FiscalYearSerializer, AccountingPeriodSerializer
)
from . import services


class JournalEntryViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        qs = JournalEntry.objects.filter(company_id=company_id)
        entry_status = request.query_params.get('status')
        if entry_status:
            qs = qs.filter(status=entry_status.upper())
        date_from = request.query_params.get('date_from')
        if date_from:
            try:
                qs = qs.filter(date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
            except ValueError:
                pass
        date_to = request.query_params.get('date_to')
        if date_to:
            try:
                qs = qs.filter(date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
            except ValueError:
                pass
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(description__icontains=search)
                | Q(lines__account__name__icontains=search)
            ).distinct()
        qs = qs.order_by('-date')
        page, page_size = parse_pagination_params(request)
        total, entries = paginate_queryset(qs, page, page_size)
        return Response(paginated_response(total, page, page_size, JournalEntrySerializer(entries, many=True).data))

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        entry = JournalEntry.objects.filter(entry_id=pk, company_id=company_id).first()
        if not entry:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = JournalEntrySerializer(entry).data
        data['lines'] = _serialize_lines(entry)
        return Response(data)

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = JournalEntrySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(created_by=request.user)
        data = JournalEntrySerializer(entry).data
        data['lines'] = _serialize_lines(entry)
        return Response(data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        entry = JournalEntry.objects.filter(entry_id=pk, company_id=company_id).first()
        if not entry:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if entry.status != 'DRAFT':
            return Response({'detail': 'Only DRAFT entries can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = JournalEntrySerializer(entry, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()
        data = JournalEntrySerializer(entry).data
        data['lines'] = _serialize_lines(entry)
        return Response(data)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        entry = JournalEntry.objects.filter(entry_id=pk, company_id=company_id).first()
        if not entry:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if entry.status != 'DRAFT':
            return Response({'detail': 'Only DRAFT entries can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        entry.delete()  # JournalLine.entry FK is on_delete=CASCADE
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='post')
    def post_entry(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            entry = services.post_entry(pk, company_id, request.user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(JournalEntrySerializer(entry).data)

    @action(detail=True, methods=['post'], url_path='void')
    def void_entry(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            entry = services.void_entry(pk, company_id, request.user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(JournalEntrySerializer(entry).data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        fmt = request.query_params.get('format', 'xlsx')
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        line_rows = services.get_export_lines(company_id, date_from, date_to)
        headers = ['Reference', 'Date', 'Account', 'Description', 'Debit (N)', 'Credit (N)', 'Status']
        rows = [
            [r['reference'], r['date'], r['account'], r['description'], r['debit'], r['credit'], r['status']]
            for r in line_rows
        ]
        if fmt == 'pdf':
            # weasyprint lays out every row in memory; a full-history line-level
            # dump (tens of thousands of rows) has been observed to OOM-kill the
            # backend. PDF is for skimming/printing — cap it and point to CSV/XLSX
            # for the complete dataset.
            PDF_ROW_LIMIT = 1000
            ctx = {
                'rows': line_rows[:PDF_ROW_LIMIT],
                'truncated': len(line_rows) > PDF_ROW_LIMIT,
                'total_count': len(line_rows),
            }
            return pdf_response(request, 'journals/entry_list.html', ctx, 'journal-entries')
        return xlsx_response(request, headers, rows, 'journal-entries', 'Journal Entries')


class FiscalYearViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        years = FiscalYear.objects.filter(company_id=company_id)
        return Response(FiscalYearSerializer(list(years), many=True).data)

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = FiscalYearSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        year = serializer.save()
        return Response(FiscalYearSerializer(year).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        year = FiscalYear.objects.filter(year_id=pk, company_id=company_id).first()
        if not year:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = FiscalYearSerializer(year).data
        data['periods'] = AccountingPeriodSerializer(list(year.periods.all()), many=True).data
        return Response(data)


class AccountingPeriodViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        fiscal_year_id = request.query_params.get('fiscal_year_id')
        if fiscal_year_id:
            year = FiscalYear.objects.filter(year_id=fiscal_year_id, company_id=company_id).first()
            periods = list(year.periods.all()) if year else []
        else:
            periods = list(AccountingPeriod.objects.filter(company_id=company_id))
        return Response(AccountingPeriodSerializer(periods, many=True).data)

    @action(detail=True, methods=['post'], url_path='close')
    def close_period(self, request, pk=None):
        company_id = get_active_company_id(request)
        period = AccountingPeriod.objects.filter(period_id=pk, company_id=company_id).first()
        if not period:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        period.status = 'CLOSED'
        period.save()
        return Response(AccountingPeriodSerializer(period).data)


def _serialize_lines(entry):
    from .serializers import JournalLineSerializer
    lines = list(entry.lines.select_related('account').all())
    return JournalLineSerializer(lines, many=True).data
