FROM python:3.10-slim
RUN apt-get update && apt-get install -y \
    libpq-dev gcc && \
    apt-get clean

WORKDIR /app

ENV TZ="Asia/Seoul"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
EXPOSE 8000

# python -u manage.py runserver 0.0.0.0:8000 --noreload
ENTRYPOINT ["python3", "-u", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
