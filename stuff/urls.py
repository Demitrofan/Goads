from django.urls import path
from moto.views import search_properties_moto, details_moto
from ads.views import index
from stuff.views import search_properties_stuff, details_stuff


app_name = 'stuff'

urlpatterns = [path('search_properties_stuff/',
                    search_properties_stuff, name='search_properties_stuff'),
               path('details_stuff/<int:item_id>/',
                    details_stuff, name='details_stuff'),
               path('', index, name='index'),
               ]
