from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('directory:index')
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Реєстрація успішна! Ласкаво просимо.')
            return redirect('directory:index')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})
