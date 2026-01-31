from fastapi import FastAPI

from config.logging_config import setup_logging
from scheduler import lifespan

# 로깅 초기화
setup_logging(enable_file_logging=True, enable_json_logging=False)

app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    return {"Hello": "World"}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
