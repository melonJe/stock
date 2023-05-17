FROM python:3.9-slim
WORKDIR /

#RUN apt-get install --yes build-base python3-dev py3-pip
RUN pip install --upgrade pip

COPY . /app
RUN pip install -r /app/requirements.txt

ENTRYPOINT ["python", "-u", "/app/main.py"]
