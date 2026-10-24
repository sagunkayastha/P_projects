FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart websocket-client
WORKDIR /app
COPY . /app
EXPOSE 8189
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8189"]
