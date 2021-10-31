FROM python:3.7-slim

WORKDIR /app

# install dependencies
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

CMD gunicorn -c gunicorn.conf.py app:app
