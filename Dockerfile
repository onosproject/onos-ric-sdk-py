FROM python:3.8-slim

WORKDIR /usr/local

COPY . ./onos-ric-sdk-py
RUN pip install --upgrade pip ./onos-ric-sdk-py --no-cache-dir

ENTRYPOINT [ "python" ]

# docker build --tag onos-ric-sdk-py:latest -f Dockerfile .
