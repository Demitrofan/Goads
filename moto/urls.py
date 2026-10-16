from django.urls import path
from moto.views import search_properties_moto, details_moto
from ads.views import index


app_name = 'moto'

urlpatterns = [path('search_properties_moto/',
                    search_properties_moto, name='search_properties_moto'),
               path('details_moto/<int:item_id>/',
                    details_moto, name='details_moto'),
               path('', index, name='index'),
               ]
