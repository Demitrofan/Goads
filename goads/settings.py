from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

STATIC_DIR = os.path.join(BASE_DIR, 'static')
settings_dir = os.path.dirname(__file__)

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]


DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

# На сервере за nginx с HTTPS (в .env SITE_HTTPS=True)
if os.environ.get("SITE_HTTPS") == "True":
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = ["https://" + h for h in ALLOWED_HOSTS if h != "*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'ads',
    'moto',
    'stuff',


]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Сайт только для своих: в .env SITE_LOGIN_REQUIRED=True (по умолчанию включено)
if os.environ.get("SITE_LOGIN_REQUIRED", "True") == "True":
    MIDDLEWARE.append('django.contrib.auth.middleware.LoginRequiredMiddleware')

ROOT_URLCONF = 'goads.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'ads.currency.context',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            # Добавлено
        },
    },
]


WSGI_APPLICATION = 'goads.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_rielt.db',
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru-RU'

TIME_ZONE = 'Asia/Kolkata'  # время Гоа

USE_I18N = True

USE_TZ = True

STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

STATIC_ROOT = os.environ.get("STATIC_ROOT", '/usr/share/nginx/html/static/')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Фото объявлений (сервис services/ads/service.py)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# OpenRouter: модель для разбора объявлений
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek/deepseek-v4-flash")

# Вход для своих
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'login'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 180   # полгода не спрашивать пароль
