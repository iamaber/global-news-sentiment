FROM python:3.12-slim

RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY dashboard dashboard
COPY newsent newsent
COPY .streamlit .streamlit
RUN mkdir data && chown -R user /home/user

USER user
ENV HOME=/home/user
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
