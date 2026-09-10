from django.conf import settings
from django.http import HttpResponsePermanentRedirect, JsonResponse
from django.core.cache import cache
import hashlib
import time

class SiteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        host = request.get_host()
        if not settings.DEBUG and host != settings.PRIMARY_DOMAIN and request.path != '/health/':
            return HttpResponsePermanentRedirect(settings.SITE_URL + request.get_full_path())
        if request.path in ('/search/', '/api/search-suggestions/'):
            identity = hashlib.sha256(request.META.get('REMOTE_ADDR', '').encode()).hexdigest()
            key = f'search:{identity}:{int(time.time()) // 60}'
            cache.add(key, 0, 65)
            try:
                count = cache.incr(key)
            except ValueError:
                count = 1
            if count > 120:
                response = JsonResponse({'error': 'Слишком много запросов. Повторите через минуту.'}, status=429)
                response['Retry-After'] = '60'
                return response
        response = self.get_response(request)
        if not request.path.startswith('/admin/'):
            response['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.path.startswith(('/users/', '/cart/', '/search/', '/api/')):
            response['X-Robots-Tag'] = 'noindex, follow'
        return response
