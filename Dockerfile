# Use an official Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY src/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app
RUN chmod +x /app/main.py
RUN chmod +x /usr/local/bin/python

# Expose the application port
EXPOSE 8080

# Command to run the Quart app
CMD python /app/src/main.py