from django.contrib import admin
from django.urls import path, include
from ads.views import index  # ads,
from ads.seo import robots_txt, sitemap_xml, verification_file
from django.conf import settings
import os

from django.urls import re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', index, name='index'),
    path('robots.txt', robots_txt),
    path('sitemap.xml', sitemap_xml),
    re_path(r'^(?P<name>(yandex_|google)\w+\.html)$', verification_file),
    # не 'ads/': блокировщики рекламы (Adblock) режут адреса с /ads/
    path('rent/', include('ads.urls')),
    path('moto/', (include('moto.urls')), name='moto'),
    path('stuff/', (include('stuff.urls')), name='stuff'),

]

# Фото отдаёт сам Django: при отладке или на временном показе (SERVE_MEDIA=True в .env).
# На постоянном сервере их будет отдавать nginx.
if settings.DEBUG or os.environ.get("SERVE_MEDIA") == "True":
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
