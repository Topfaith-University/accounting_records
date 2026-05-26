from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import JournalEntry, FiscalYear, AccountingPeriod
from .serializers import (
    JournalEntrySerializer, FiscalYearSerializer, AccountingPeriodSerializer
)
from . import services


class JournalEntryViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        entries = JournalEntry.nodes.all()
        entry_status = request.query_params.get('status')
        if entry_status:
            entries = [e for e in entries if e.status == entry_status.upper()]
        entries = sorted(entries, key=lambda e: str(e.date), reverse=True)
        return Response(JournalEntrySerializer(entries, many=True).data)

    def retrieve(self, request, pk=None):
        entry = JournalEntry.nodes.get_or_none(entry_id=pk)
        if not entry:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = JournalEntrySerializer(entry).data
        data['lines'] = _serialize_lines(entry)
        return Response(data)

    def create(self, request):
        serializer = JournalEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(created_by=request.user.username)
        data = JournalEntrySerializer(entry).data
        data['lines'] = _serialize_lines(entry)
        return Response(data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entry = JournalEntry.nodes.get_or_none(entry_id=pk)
        if not entry:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if entry.status != 'DRAFT':
            return Response({'detail': 'Only DRAFT entries can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        if entry.created_by != request.user.username and not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        for field in ['reference', 'date', 'description', 'entry_type']:
            if field in request.data:
                setattr(entry, field, request.data[field])
        entry.save()
        return Response(JournalEntrySerializer(entry).data)

    def destroy(self, request, pk=None):
        entry = JournalEntry.nodes.get_or_none(entry_id=pk)
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
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            entry = services.post_entry(pk, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(JournalEntrySerializer(entry).data)

    @action(detail=True, methods=['post'], url_path='void')
    def void_entry(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            entry = services.void_entry(pk, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(JournalEntrySerializer(entry).data)


class FiscalYearViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        years = FiscalYear.nodes.all()
        return Response(FiscalYearSerializer(list(years), many=True).data)

    def create(self, request):
        if not request.user.groups.filter(name__in=['Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = FiscalYearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year = serializer.save()
        return Response(FiscalYearSerializer(year).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        year = FiscalYear.nodes.get_or_none(year_id=pk)
        if not year:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = FiscalYearSerializer(year).data
        data['periods'] = AccountingPeriodSerializer(list(year.periods.all()), many=True).data
        return Response(data)


class AccountingPeriodViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        fiscal_year_id = request.query_params.get('fiscal_year_id')
        if fiscal_year_id:
            year = FiscalYear.nodes.get_or_none(year_id=fiscal_year_id)
            periods = list(year.periods.all()) if year else []
        else:
            periods = AccountingPeriod.nodes.all()
        return Response(AccountingPeriodSerializer(list(periods), many=True).data)

    @action(detail=True, methods=['post'], url_path='close')
    def close_period(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        period = AccountingPeriod.nodes.get_or_none(period_id=pk)
        if not period:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        period.status = 'CLOSED'
        period.save()
        return Response(AccountingPeriodSerializer(period).data)


def _serialize_lines(entry):
    from .serializers import JournalLineSerializer
    lines = list(entry.lines.all())
    return JournalLineSerializer(lines, many=True).data
