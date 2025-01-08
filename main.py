from fastapi import FastAPI

from scheduler import lifespan

app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    return {"Hello": "World"}
