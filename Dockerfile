FROM python:3.9-slim
WORKDIR /

#RUN apt-get install --yes build-base python3-dev py3-pip
RUN pip install --upgrade pip
ENV TZ="Asia/Seoul"
EXPOSE 8000

COPY . /app
RUN pip install -r /app/requirements.txt
RUN python manage.py migrate

ENTRYPOINT ["python", "-u", "manage.py", "runserver"]