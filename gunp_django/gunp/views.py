from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse


def healthz(request):
    """Liveness/readiness check: confirms the process is up and the DB is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except OperationalError:
        return JsonResponse({'status': 'error', 'database': 'unreachable'}, status=503)
    return JsonResponse({'status': 'ok'})
