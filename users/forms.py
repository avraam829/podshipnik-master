from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(label="Рабочий email", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот email уже используется.")
        return email


class AccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "email", "phone", "company")
        labels = {
            "first_name": "Контактное лицо",
            "email": "Рабочий email",
            "phone": "Телефон",
            "company": "Компания",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
            "company": forms.TextInput(attrs={"autocomplete": "organization"}),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот email уже используется.")
        return email
