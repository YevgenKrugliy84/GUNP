from django import forms

from .models import Department, Record, SupportRequest


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs.setdefault('class', css)


class RecordForm(BootstrapModelForm):
    class Meta:
        model = Record
        fields = [
            'department', 'last_name', 'first_name', 'middle_name',
            'ip_address', 'mac_address', 'service', 'office', 'work_phone', 'mobile_phone',
        ]
        labels = {
            'department': 'Підрозділ',
            'last_name': 'Прізвище',
            'first_name': "Ім'я",
            'middle_name': 'По батькові',
            'ip_address': 'IP-адреса',
            'mac_address': 'MAC-адреса',
            'service': 'Служба',
            'office': 'Кабінет',
            'work_phone': 'Робочий телефон',
            'mobile_phone': 'Мобільний телефон',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.order_by('name')


class DepartmentForm(BootstrapModelForm):
    class Meta:
        model = Department
        fields = ['name', 'ip_address']
        labels = {'name': 'Назва підрозділу', 'ip_address': 'IP-адреса'}


class SupportRequestForm(BootstrapModelForm):
    class Meta:
        model = SupportRequest
        fields = ['name', 'department', 'email', 'issue_type', 'description', 'urgency']
        labels = {
            'name': "ПІБ",
            'department': 'Підрозділ',
            'email': 'Email',
            'issue_type': 'Тип проблеми',
            'description': 'Опис',
            'urgency': 'Терміновість',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.order_by('name')
