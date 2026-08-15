import requests
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import TemplateView
from django.utils import timezone


class CalculatorView(LoginRequiredMixin, TemplateView):
    """
    Simple general-purpose calculator tool.
    """
    template_name = 'shared_tools/calculator.html'


class WeatherView(LoginRequiredMixin, TemplateView):
    """
    Weather widget showing current weather for a Nigeria farm location.
    Uses Open-Meteo API (no key required).
    """
    template_name = 'shared_tools/weather.html'

    DEFAULT_LAT = 6.5244
    DEFAULT_LON = 3.3792
    DEFAULT_CITY = 'Lagos'

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        location = request.GET.get('location', '').strip()
        weather_data = self.fetch_weather(location)
        context.update(weather_data)
        return render(request, self.template_name, context)

    def fetch_weather(self, location=''):
        lat = getattr(settings, 'WEATHER_LAT', self.DEFAULT_LAT)
        lon = getattr(settings, 'WEATHER_LON', self.DEFAULT_LON)
        city = getattr(settings, 'WEATHER_CITY', self.DEFAULT_CITY)

        if location:
            coords = self.geocode_location(location)
            if coords:
                lat, lon, city = coords
            else:
                city = location.title()

        weather = {
            'city': city,
            'temperature': None,
            'humidity': None,
            'wind_speed': None,
            'weather_code': None,
            'description': 'Unavailable',
            'error': None,
            'last_updated': timezone.now(),
        }

        try:
            url = (
                'https://api.open-meteo.com/v1/forecast'
                f'?latitude={lat}&longitude={lon}'
                '&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code'
                '&timezone=Africa/Lagos'
            )
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            current = data.get('current', {})

            weather['temperature'] = current.get('temperature_2m')
            weather['humidity'] = current.get('relative_humidity_2m')
            weather['wind_speed'] = current.get('wind_speed_10m')
            weather['weather_code'] = current.get('weather_code')
            weather['description'] = self.describe_code(current.get('weather_code'))
        except Exception as exc:
            weather['error'] = str(exc)

        return weather

    @staticmethod
    def geocode_location(query):
        try:
            url = (
                'https://geocoding-api.open-meteo.com/v1/search'
                f'?name={requests.utils.quote(query)}'
                '&count=1'
                '&language=en'
                '&format=json'
            )
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            results = data.get('results') or []
            if results:
                first = results[0]
                return float(first['latitude']), float(first['longitude']), first.get('name', query)
        except Exception:
            pass
        return None

    @staticmethod
    def describe_code(code):
        if code is None:
            return 'Unavailable'
        mapping = {
            0: 'Clear sky',
            1: 'Mainly clear',
            2: 'Partly cloudy',
            3: 'Overcast',
            45: 'Foggy',
            48: 'Depositing rime fog',
            51: 'Light drizzle',
            53: 'Moderate drizzle',
            55: 'Dense drizzle',
            61: 'Slight rain',
            63: 'Moderate rain',
            65: 'Heavy rain',
            80: 'Rain showers',
            95: 'Thunderstorm',
        }
        return mapping.get(code, 'Unknown')
