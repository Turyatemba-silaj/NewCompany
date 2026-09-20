import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NewCompany.settings")

from NewCompany.wsgi import application

app = application
