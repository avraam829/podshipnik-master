from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from .forms import CustomUserCreationForm
from django.views.decorators.http import require_POST

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'users/register.html', {'form': form})

class CustomLoginView(LoginView):
    template_name = 'users/login.html'

@require_POST
def custom_logout_view(request):
    """
    Logs out the user and redirects to the homepage.
    Handles both GET and POST requests.
    """
    logout(request)
    return redirect('/')
