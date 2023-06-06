#sudo docker build --tag stock:latest -f Dockerfile.stock .
sudo docker build --tag stock:latest . && sudo docker-compose up -d