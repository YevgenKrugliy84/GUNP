import json
import logging
import os
import subprocess

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import RecordForm, SupportRequestForm
from .models import Department, DownloadLog, KnowledgeBaseArticle, Record, SupportRequest
from .services import check_departments, check_ping, generate_chatbot_response

logger = logging.getLogger(__name__)


def index(request):
    departments = list(Department.objects.order_by('name'))
    for dept in departments:
        dept.latest_request = dept.support_requests.order_by('-created_at').first()
    return render(request, 'directory/index.html', {'departments': departments})


@require_GET
def department_statuses(request):
    departments = Department.objects.exclude(ip_address__isnull=True).exclude(ip_address='')
    results = check_departments(list(departments))
    statuses = []
    for dept, result in results:
        status = 'online' if result['status'] else 'offline'
        latency = result['latency']
        color = 'green' if result['status'] else 'red'
        if result['status'] and latency and latency > 1000:
            color = 'yellow'
        dept.last_status = result['status']
        dept.last_latency = latency
        statuses.append({
            'id': dept.id,
            'name': dept.name,
            'ip_address': dept.ip_address,
            'status': status,
            'color': color,
            'latency': round(latency, 2) if latency else None,
        })
    Department.objects.bulk_update(
        [d for d, _ in results], ['last_status', 'last_latency'],
    ) if results else None
    return JsonResponse(statuses, safe=False)


@login_required
def department_detail(request, dept_id):
    department = get_object_or_404(Department, pk=dept_id)
    records = Record.objects.filter(department=department).order_by('last_name')
    return render(request, 'directory/department.html', {'department': department, 'records': records})


def add_record_public(request, dept_id):
    department = get_object_or_404(Department, pk=dept_id)
    if request.method == 'POST':
        form = RecordForm(request.POST, initial={'department': department})
        form.instance.department = department
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Запис успішно додано')
                return redirect('directory:index')
            except IntegrityError:
                messages.error(request, 'IP-адреса або MAC-адреса вже існує')
        else:
            messages.error(request, 'Перевірте правильність заповнення полів')
    else:
        form = RecordForm(initial={'department': department})
    return render(request, 'directory/public_add_record.html', {'department': department, 'dept_id': dept_id, 'form': form})


@login_required
def search(request):
    results = None
    search_term = ''
    if request.method == 'POST':
        search_term = request.POST.get('search_term', '').strip()
        if search_term:
            results = Record.objects.select_related('department').filter(
                Q(last_name__icontains=search_term)
                | Q(first_name__icontains=search_term)
                | Q(ip_address__icontains=search_term)
                | Q(mac_address__icontains=search_term)
                | Q(service__icontains=search_term)
                | Q(work_phone__icontains=search_term)
                | Q(mobile_phone__icontains=search_term)
                | Q(department__name__icontains=search_term)
            ).order_by('last_name')
        else:
            messages.warning(request, 'Будь ласка, введіть пошуковий запит')
    return render(request, 'directory/search.html', {'results': results, 'search_term': search_term})


def tech_support(request):
    departments = Department.objects.all()
    return render(request, 'directory/tech_support.html', {'departments': departments})


@require_POST
def submit_support_request(request):
    form = SupportRequestForm(request.POST)
    if form.is_valid():
        support_request = form.save()
        messages.success(request, f'Ваш запит успішно відправлено! Номер запиту: #{support_request.id}')
    else:
        messages.error(request, 'Сталася помилка при відправці запиту. Перевірте поля.')
    return redirect('directory:tech_support')


def check_support_request(request):
    request_id = None
    support_request = None
    if request.method == 'POST':
        request_id = request.POST.get('request_id', '').strip()
        if request_id.isdigit():
            support_request = SupportRequest.objects.filter(pk=int(request_id)).first()
            if not support_request:
                messages.error(request, f'Заявку з номером #{request_id} не знайдено')
        else:
            messages.error(request, 'Введіть коректний номер заявки')
    return render(request, 'directory/check_support_request.html', {
        'support_request': support_request, 'request_id': request_id,
    })


def about(request):
    return render(request, 'directory/about.html')


def network_tools(request):
    ping_result = None
    traceroute_result = None
    if request.method == 'POST':
        target = request.POST.get('target', '').strip()
        if 'ping' in request.POST and target:
            try:
                param = '-n' if os.name == 'nt' else '-c'
                result = subprocess.run(['ping', param, '4', target], capture_output=True, text=True, timeout=10)
                ping_result = result.stdout if result.returncode == 0 else result.stderr
            except subprocess.TimeoutExpired:
                ping_result = 'Ping timed out after 10 seconds'
            except Exception as e:
                ping_result = f'Error: {e}'
        elif 'traceroute' in request.POST and target:
            try:
                cmd = 'tracert' if os.name == 'nt' else 'traceroute'
                result = subprocess.run([cmd, target], capture_output=True, text=True, timeout=30)
                traceroute_result = result.stdout if result.returncode == 0 else result.stderr
            except subprocess.TimeoutExpired:
                traceroute_result = 'Traceroute timed out after 30 seconds'
            except Exception as e:
                traceroute_result = f'Error: {e}'
    return render(request, 'directory/network_tools.html', {
        'ping_result': ping_result, 'traceroute_result': traceroute_result,
    })


def ip_calculator(request):
    return render(request, 'directory/ip_calculator.html')


@require_GET
def run_speedtest(request):
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        download_speed = st.download() / 1_000_000
        upload_speed = st.upload() / 1_000_000
        return JsonResponse({
            'download': round(download_speed, 2),
            'upload': round(upload_speed, 2),
            'ping': round(st.results.ping, 2),
            'server': st.results.server['name'],
        })
    except Exception as e:
        logger.error('Speedtest failed: %s', e)
        return JsonResponse({'error': str(e)})


@require_POST
def chatbot(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        data = {}
    user_message = (data.get('message') or '').lower()
    response = generate_chatbot_response(user_message, SupportRequest)
    return JsonResponse({'response': response})


def get_my_ip(request):
    return JsonResponse({'ip': request.META.get('REMOTE_ADDR')})


def resources(request):
    articles = KnowledgeBaseArticle.objects.order_by('category', 'title')
    search_term = request.GET.get('search', '')
    if search_term:
        articles = articles.filter(Q(title__icontains=search_term) | Q(content__icontains=search_term))
    categories = list(KnowledgeBaseArticle.objects.values_list('category', flat=True).distinct())
    return render(request, 'directory/resources.html', {
        'articles': articles, 'categories': categories, 'search_term': search_term,
    })


def download_form(request):
    from django.conf import settings
    from django.http import FileResponse, Http404

    filename = 'application_form.doc'
    path = settings.MEDIA_ROOT / 'uploads' / filename
    if not path.exists():
        raise Http404
    if request.user.is_authenticated:
        DownloadLog.objects.create(user=request.user, filename=filename)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=filename)
