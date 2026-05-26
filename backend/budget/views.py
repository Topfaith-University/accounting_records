from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Budget
from .serializers import BudgetSerializer, BudgetLineSerializer


class BudgetViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        budgets = sorted(Budget.nodes.all(), key=lambda b: str(b.created_at), reverse=True)
        return Response(BudgetSerializer(budgets, many=True).data)

    def retrieve(self, request, pk=None):
        budget = Budget.nodes.get_or_none(budget_id=pk)
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = BudgetSerializer(budget).data
        data['lines'] = BudgetLineSerializer(list(budget.lines.all()), many=True).data
        return Response(data)

    def create(self, request):
        if not request.user.groups.filter(name__in=['Admin', 'Manager']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = BudgetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        budget = serializer.save(created_by=request.user.username)
        data = BudgetSerializer(budget).data
        data['lines'] = BudgetLineSerializer(list(budget.lines.all()), many=True).data
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        budget = Budget.nodes.get_or_none(budget_id=pk)
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if budget.status == 'APPROVED':
            return Response({'detail': 'Cannot delete an approved budget.'}, status=status.HTTP_400_BAD_REQUEST)
        for line in budget.lines.all():
            line.delete()
        budget.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        budget = Budget.nodes.get_or_none(budget_id=pk)
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if budget.status == 'APPROVED':
            return Response({'detail': 'Already approved.'}, status=status.HTTP_400_BAD_REQUEST)
        from datetime import datetime
        budget.status = 'APPROVED'
        budget.approved_by = request.user.username
        budget.approved_at = datetime.utcnow()
        budget.save()
        return Response(BudgetSerializer(budget).data)

    @action(detail=True, methods=['get'], url_path='variance')
    def variance(self, request, pk=None):
        budget = Budget.nodes.get_or_none(budget_id=pk)
        if not budget:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from neomodel import db
        results, _ = db.cypher_query("""
            MATCH (b:Budget {budget_id: $budget_id})-[:HAS_LINE]->(bl:BudgetLine)-[:FOR_ACCOUNT]->(a:Account)
            WITH a, bl.budgeted_amount AS budgeted
            OPTIONAL MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
            WHERE e.status = 'POSTED'
            RETURN a.account_id, a.code, a.name, a.account_type, a.normal_balance,
                   budgeted,
                   coalesce(sum(CASE WHEN l.side = 'DEBIT' THEN l.amount ELSE 0 END), 0) AS debits,
                   coalesce(sum(CASE WHEN l.side = 'CREDIT' THEN l.amount ELSE 0 END), 0) AS credits
            ORDER BY a.code
        """, {'budget_id': pk})
        lines = []
        for r in results:
            account_id, code, name, acc_type, normal_balance, budgeted, debits, credits = r
            if normal_balance == 'DEBIT':
                actual = round((debits or 0.0) - (credits or 0.0), 2)
            else:
                actual = round((credits or 0.0) - (debits or 0.0), 2)
            budgeted = budgeted or 0.0
            variance = round(budgeted - actual, 2)
            lines.append({
                'account_id': account_id,
                'code': code,
                'name': name,
                'account_type': acc_type,
                'budgeted': budgeted,
                'actual': actual,
                'variance': variance,
                'variance_pct': round(variance / budgeted * 100, 1) if budgeted else None,
            })
        return Response({
            'budget_id': pk,
            'name': budget.name,
            'fiscal_year': budget.fiscal_year,
            'lines': lines,
        })
