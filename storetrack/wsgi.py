"""
WSGI config for storetrack project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
from pathlib import Path
from django.core.wsgi import get_wsgi_application

# 1. Dynamically locate your project's root folder
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. Try to load python-dotenv (Install this via pip)
try:
    from dotenv import load_dotenv
    # Look specifically for your production configuration file on the server
    prod_env = BASE_DIR / '.env.prod'
    if prod_env.exists():
        load_dotenv(prod_env)
    else:
        # Fallback to standard .env for local debugging if run via a WSGI server
        load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'storetrack.settings')

application = get_wsgi_application()

