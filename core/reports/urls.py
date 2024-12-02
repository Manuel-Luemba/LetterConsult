from django.urls import path

from core.reports.views import ReportLetterView

urlpatterns = [
    # reports
    path('letter/', ReportLetterView.as_view(), name='letter_report'),

]
