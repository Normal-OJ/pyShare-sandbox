FROM python:3.8
LABEL maintainer="pySahre" 

WORKDIR /sandbox-setup
COPY . .
RUN pip3 install -r requirements.txt
RUN python3 setup_matplotlib.py
# sandbox user with uid:1450
# RUN useradd sandbox -u 1450
# USER sandbox
WORKDIR /sandbox
