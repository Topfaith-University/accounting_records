from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.auth import get_active_company_id
from .models import Budget
from .serializers import BudgetSerializer, BudgetLineSerializer
from . import services


class BudgetViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        budgets = Budget.objects.filter(company_id=company_id).order_by('-created_at')
        return Response(BudgetSerializer(budgets, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        budget = Budget.objects.filter(budget_id=pk, company_id=company_id).first()
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = BudgetSerializer(budget).data
        data['lines'] = BudgetLineSerializer(budget.lines.select_related('account').all(), many=True).data
        return Response(data)

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = BudgetSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        budget = serializer.save(created_by=request.user)
        data = BudgetSerializer(budget).data
        data['lines'] = BudgetLineSerializer(budget.lines.select_related('account').all(), many=True).data
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        budget = Budget.objects.filter(budget_id=pk, company_id=company_id).first()
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if budget.status == 'APPROVED':
            return Response({'detail': 'Cannot delete an approved budget.'}, status=status.HTTP_400_BAD_REQUEST)
        budget.delete()  # BudgetLine.budget FK is on_delete=CASCADE
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        budgets = Budget.objects.filter(company_id=company_id).order_by('-created_at')
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Name', 'Fiscal Year', 'Total Budgeted (N)', 'Status', 'Created By']
        rows = []
        for b in budgets:
            total_budgeted = sum(l.budgeted_amount for l in b.lines.all())
            rows.append([b.name, b.fiscal_year, total_budgeted, b.status, b.created_by.username if b.created_by else ''])
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'fiscal_year', 'total_budgeted', 'status', 'created_by'], r
            )) for r in rows]}
            return pdf_response(request, 'budget/budget_list.html', ctx, 'budgets')
        return xlsx_response(request, headers, rows, 'budgets', 'Budgets')

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        company_id = get_active_company_id(request)
        budget = Budget.objects.filter(budget_id=pk, company_id=company_id).first()
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            budget = services.approve_budget(budget, request.user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BudgetSerializer(budget).data)

    @action(detail=True, methods=['get'], url_path='variance')
    def variance(self, request, pk=None):
        company_id = get_active_company_id(request)
        budget = Budget.objects.filter(budget_id=pk, company_id=company_id).first()
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        lines = services.compute_variance(pk, company_id)
        return Response({
            'budget_id': pk,
            'name': budget.name,
            'fiscal_year': budget.fiscal_year,
            'lines': lines,
        })
