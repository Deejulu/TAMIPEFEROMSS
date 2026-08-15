from django.urls import path
from . import views

app_name = 'shared_tools'

urlpatterns = [
    path('weather/', views.WeatherView.as_view(), name='weather'),
    path('calculator/', views.CalculatorView.as_view(), name='calculator'),
]
