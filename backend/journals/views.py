from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.auth import get_active_company_id
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
        entries = JournalEntry.nodes.filter(company_id=company_id)
        entry_status = request.query_params.get('status')
        if entry_status:
            entries = [e for e in entries if e.status == entry_status.upper()]
        entries = sorted(entries, key=lambda e: str(e.date), reverse=True)
        return Response(JournalEntrySerializer(entries, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        entry = JournalEntry.nodes.get_or_none(entry_id=pk, company_id=company_id)
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
        entry = serializer.save(created_by=request.user.username)
        data = JournalEntrySerializer(entry).data
        data['lines'] = _serialize_lines(entry)
        return Response(data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        entry = JournalEntry.nodes.get_or_none(entry_id=pk, company_id=company_id)
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
        entry = JournalEntry.nodes.get_or_none(entry_id=pk, company_id=company_id)
        if not entry:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if entry.status != 'DRAFT':
            return Response({'detail': 'Only DRAFT entries can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        for line in entry.lines.all():
            line.delete()
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='post')
    def post_entry(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            entry = services.post_entry(pk, company_id, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(JournalEntrySerializer(entry).data)

    @action(detail=True, methods=['post'], url_path='void')
    def void_entry(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            entry = services.void_entry(pk, company_id, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(JournalEntrySerializer(entry).data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        entries = list(JournalEntry.nodes.filter(company_id=company_id))
        entries = sorted(entries, key=lambda e: str(e.date), reverse=True)
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Reference', 'Date', 'Description', 'Debit (N)', 'Credit (N)', 'Status']
        rows = [
            [e.reference, str(e.date), e.description, e.total_debit, e.total_credit, e.status]
            for e in entries
        ]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['reference', 'date', 'description', 'total_debit', 'total_credit', 'status'], r
            )) for r in rows]}
            return pdf_response(request, 'journals/entry_list.html', ctx, 'journal-entries')
        return xlsx_response(request, headers, rows, 'journal-entries', 'Journal Entries')


class FiscalYearViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        years = FiscalYear.nodes.filter(company_id=company_id)
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
        year = FiscalYear.nodes.get_or_none(year_id=pk, company_id=company_id)
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
            year = FiscalYear.nodes.get_or_none(year_id=fiscal_year_id, company_id=company_id)
            periods = list(year.periods.all()) if year else []
        else:
            periods = AccountingPeriod.nodes.filter(company_id=company_id)
        return Response(AccountingPeriodSerializer(list(periods), many=True).data)

    @action(detail=True, methods=['post'], url_path='close')
    def close_period(self, request, pk=None):
        company_id = get_active_company_id(request)
        period = AccountingPeriod.nodes.get_or_none(period_id=pk, company_id=company_id)
        if not period:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        period.status = 'CLOSED'
        period.save()
        return Response(AccountingPeriodSerializer(period).data)


def _serialize_lines(entry):
    from .serializers import JournalLineSerializer
    lines = list(entry.lines.all())
    return JournalLineSerializer(lines, many=True).data
