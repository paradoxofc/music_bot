run.server.local:
	python3 backend/manage.py runserver 0.0.0.0:8000

run.server.prod:
	PYTHONPATH=./backend gunicorn config.wsgi:application \
		--bind 0.0.0.0:8000 \
  		--workers ${GUNICORN_WORKERS} \
  		--threads ${GUNICORN_THREADS} \
  		--max-requests ${GUNICORN_MAX_REQUESTS} \
  		--max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER} \
  		--access-logfile - \
		--error-logfile - \
		--log-level info \
		--access-logformat '%(t)s "%(r)s" %(s)s %(b)s %(L)s'

run.bot:
	python3 -m telegram_bot

migrate:
	python3 backend/manage.py migrate

collectstatic:
	python3 backend/manage.py collectstatic --no-input

superuser:
	python3 backend/manage.py createsuperuser --email ""

celery:
	cd backend && celery -A config worker --loglevel=info