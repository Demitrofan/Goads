from django.urls import path

from ads.views import details, index, search_properties

app_name = 'ads'

urlpatterns = [
    path('search_properties/', search_properties, name='search_properties'),
    path('details/<int:item_id>/', details, name='details'),
    path('', index, name='index'),
]
