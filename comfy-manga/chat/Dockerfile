FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core openssh-client && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart websocket-client pillow
RUN useradd -u 1000 -m manga   # ssh (manga-gpu helper) needs a passwd entry for the app uid
WORKDIR /app
COPY . /app
EXPOSE 8189
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8189"]
