FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py validate.py sample_data.json web_app.py ./

EXPOSE 8000

CMD ["python", "web_app.py"]
