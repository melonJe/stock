FROM python:3.10-slim
WORKDIR /app

ENV TZ="Asia/Seoul"

RUN apt-get update && apt-get install -y libpq-dev gcc && apt-get clean

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
EXPOSE 8000

ENTRYPOINT ["uvicorn", "main:app", "--reload"]
