from django.urls import path

from core.erp.views.dashboard.views import DashboardView
from core.erp.views.department.views import *
from core.erp.views.letter.views import LetterMyListView, LetterCreateView, ReferenceSearchView, \
    LetterUpdateView, LetterListView, LetterApproveView, ExportarCartaPDF, DownloadProtocolView, \
    LetterDetailView
from core.erp.views.reference.views import ReferenceListView, ReferenceCreateView, ReferenceDeleteView
from core.erp.views.type.views import *
from core.erp.views.position.views import *
from core.erp.views.absence.views import *

from django.conf.urls.static import static

app_name = 'erp'
urlpatterns = [
    # department
    path('department/list/', DepartmentListView.as_view(), name='department_list'),
    path('department/add/', DepartmentCreateView.as_view(), name='department_create'),
    path('department/update/<int:pk>/', DepartmentUpdateView.as_view(), name='department_update'),
    path('department/delete/<int:pk>/', DepartmentDeleteView.as_view(), name='department_delete'),
    path('department/form/', DepartmentFormView.as_view(), name='department_form'),

    # position
    path('position/list/', PositionListView.as_view(), name='position_list'),
    path('position/add/', PositionCreateView.as_view(), name='position_create'),
    path('position/update/<int:pk>/', PositionUpdateView.as_view(), name='position_update'),
    path('position/delete/<int:pk>/', PositionDeleteView.as_view(), name='position_delete'),

    # type
    path('type/list/', TypeListView.as_view(), name='type_list'),
    path('type/add/', TypeCreateView.as_view(), name='type_create'),
    path('type/update/<int:pk>/', TypeUpdateView.as_view(), name='type_update'),
    path('type/delete/<int:pk>/', TypeDeleteView.as_view(), name='type_delete'),

    # Absence
    path('absence/list/', AbsenceListView.as_view(), name='absence_list'),
    path('absence/my/list/', MyAbsenceListView.as_view(), name='absence_my_list'),
    path('absence/add/', AbsenceCreateView.as_view(), name='absence_create'),
    #path('Absence/add/', PedidoAusenciaView.as_view(), name='Absence_create'),
    path('absence/update/<int:pk>/', AbsenceUpdateView.as_view(), name='absence_update'),
    path('absence/delete/<int:pk>/', AbsenceDeleteView.as_view(), name='absence_delete'),
    # pending aprove
    path('absence/aprove/<int:pk>/', AproveUpdateAbsenceView.as_view(), name='absence_update_aprove'),
    path('absence/aprove/manager/<int:pk>/', AproveUpdateManagerAbsenceView.as_view(), name='absence_update_aprove_manager'),
    path('absence/aprove/', AproveCreateAbsenceView.as_view(), name='absence_create_aprove'),
    # Print Absence
#    path('absence/print/pdf/<int:pk>/', AbsenceInfoPdf.as_view(), name='absence_print_pdf'),
    path('absence/print/pdf/<int:pk>/', GeneratePdf.as_view(), name='absence_print_pdf'),
    path('absence/view/pdf/<int:pk>/', AbsenceViewPdf.as_view(), name='view_pdf'),
    # dashboard
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

    path('reference/list/', ReferenceListView.as_view(), name='reference_list'),
    path('reference/add/', ReferenceCreateView.as_view(), name='reference_create'),
    path('department/update/<int:pk>/', DepartmentUpdateView.as_view(), name='department_update'),
    path('reference/delete/<int:pk>/',ReferenceDeleteView.as_view(), name='reference_delete'),
    path('department/form/', DepartmentFormView.as_view(), name='department_form'),

    path('reference/search/', ReferenceSearchView.as_view(), name='reference_search'),
    #path('reference/check/', LetterCheckView.as_view(), name='reference_check'),
    path('letter/add/', LetterCreateView.as_view(), name='letter_create'),
    path('letter/update/<int:pk>/', LetterUpdateView.as_view(), name='letter_update'),
    path('letter/approve/<int:pk>/', LetterApproveView.as_view(), name='letter_approve'),
    path('letter/download/<int:pk>/', ExportarCartaPDF.as_view(), name='letter_download'),
    path('letter/mylist/', LetterMyListView.as_view(), name='letter_mylist'),
    path('letter/list/', LetterListView.as_view(), name='letter_list'),
    path('letter/detail/<int:pk>/', LetterDetailView.as_view(), name='letter_view'),
    path('create/', LetterCreateView.as_view(), name='create_letter'),
    path('letter/downloadprotocol/<int:pk>/', DownloadProtocolView .as_view(), name='download_protocol'),

]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)