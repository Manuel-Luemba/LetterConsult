from django.db.models import Count, Avg, F
from django.db.models.functions import TruncDate
from core.requisition.models import RequisitionAuditLog, PurchaseRequest
from core.timesheet.models import TimesheetStatusChange, Timesheet
from datetime import datetime, timedelta

class StatsService:
    @staticmethod
    def get_dashboard_stats(start_date=None, end_date=None):
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).date()
        if not end_date:
            end_date = datetime.now().date()

        # 1. Atividade Diária (Volume de ações por dia)
        req_activity = RequisitionAuditLog.objects.filter(
            created_at__date__range=[start_date, end_date]
        ).annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).order_by('date')

        ts_activity = TimesheetStatusChange.objects.filter(
            created_at__date__range=[start_date, end_date]
        ).annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).order_by('date')

        # 2. Top Utilizadores (Quem mais trabalha no sistema)
        top_users = RequisitionAuditLog.objects.filter(
            created_at__date__range=[start_date, end_date]
        ).values('performed_by__username').annotate(total=Count('id')).order_by('-total')[:5]

        # 3. Eficiência (Tempo Médio de Aprovação em dias)
        # Comparamos a criação da requisição com o log de aprovação
        avg_approval = RequisitionAuditLog.objects.filter(
            action_type='approved',
            created_at__date__range=[start_date, end_date]
        ).aggregate(
            avg_days=Avg(F('created_at') - F('purchase_request__created_at'))
        )

        return {
            "activity_chart": {
                "requisitions": list(req_activity),
                "timesheets": list(ts_activity)
            },
            "top_users": list(top_users),
            "efficiency": {
                "avg_approval_days": round(avg_approval['avg_days'].days, 1) if avg_approval['avg_days'] else 0
            }
        }
