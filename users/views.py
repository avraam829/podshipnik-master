from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import AccountForm, CustomUserCreationForm


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(_safe_next_url(request) or 'account')
    else:
        form = CustomUserCreationForm()
    return render(request, 'users/register.html', {'form': form, 'next': _safe_next_url(request)})

class CustomLoginView(LoginView):
    template_name = 'users/login.html'


@login_required(login_url="login")
def account(request):
    if request.method == "POST":
        form = AccountForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("account")
    else:
        form = AccountForm(instance=request.user)
    orders = request.user.orders.prefetch_related("items__product")
    return render(request, "users/account.html", {"form": form, "orders": orders})

@require_POST
def custom_logout_view(request):
    logout(request)
    return redirect('/')
