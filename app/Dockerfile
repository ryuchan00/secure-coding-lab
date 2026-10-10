FROM python:3.13-alpine
WORKDIR /app
COPY app/ /app/
COPY lessons/ /lessons/
USER 1000:1000
CMD ["python", "server.py"]
