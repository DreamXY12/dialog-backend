# 
FROM python:3.11

# 
WORKDIR /project/dialog-backend

# 
COPY ./requirements.txt /project/requirements.txt

# 
RUN pip install --no-cache-dir --upgrade -r /project/requirements.txt

# 
COPY . /project/dialog-backend

EXPOSE 80

CMD ["uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
