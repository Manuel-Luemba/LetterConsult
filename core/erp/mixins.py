from datetime import date, datetime

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy


class IsSuperuserMixin(object):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        return redirect('index')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["date_now"] = datetime.now()
        return context


class ValidatePermissionRequiredMixin(object):
    permission_required = ''
    url_redirect = None

    def get_url_redirect(self):
        if self.url_redirect is None:
            return reverse_lazy('login')
        return self.url_redirect

    def get_perms(self):
        if isinstance(self.permission_required, str):
            perms = (self.permission_required,)
        else:
            perms = self.permission_required
        return perms

    def dispatch(self, request, *args, **kwargs):
        if request.user.has_perms(self.get_perms()):
            return super().dispatch(request, *args, **kwargs)
        messages.error(request, 'Não tem permissão para aceder a este módulo.')
        return redirect(self.get_url_redirect())


# class ValidatePermissionRequiredMixin(object):
#     permission_required = ''
#     url_redirect = None
#
#     def get_perms(self):
#         perms = []
#         if isinstance(self.permission_required, str):
#             perms.append(self.permission_required)
#         else:
#             perms = list(self.permission_required)
#         return perms
#
#     def get_url_redirect(self):
#         if self.url_redirect is None:
#             return reverse_lazy('erp:dashboard')
#         return self.url_redirect
#
#     def dispatch(self, request, *args, **kwargs):
#         request = get_current_request()
#
#         if request.user.is_superuser:
#             return super().dispatch(request, *args, **kwargs)
#         if 'group' in request.session:
#             group = request.session['group']
#             perms = self.get_perms()
#             for p in perms:
#                 if not group.permissions.filter(codename=p).exists():
#                     messages.error(request, 'Não tm permissão para aceder a este módulo')
#                     return HttpResponseRedirect(self.get_url_redirect())
#             return super().dispatch(request, *args, **kwargs)
#         messages.error(request, 'Não tm permissão para aceder a este módulo')
#         return HttpResponseRedirect(self.get_url_redirect())
