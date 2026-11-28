from django.urls import path
from . import views
app_name='banking'
urlpatterns=[path('',views.index,name='index'),
path('account/',views.account,name='account'),
path('upload/',views.upload,name='upload'),
path('<int:pk>/',views.detail,name='detail'),
path('<int:pk>/action/',views.action,name='action')]
