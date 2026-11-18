FROM python:3.12-slim

RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend backend
COPY newsent newsent
COPY frontend frontend
RUN mkdir data && chown -R user /home/user

USER user
ENV HOME=/home/user
EXPOSE 8501
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8501", "--proxy-headers", "--forwarded-allow-ips=*"]
