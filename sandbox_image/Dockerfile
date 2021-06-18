FROM python:3.8
LABEL maintainer="pySahre" 

WORKDIR /sandbox-setup
COPY . .
# Install pytorch
RUN pip3 install torch==1.9.0+cpu \
    torchvision==0.10.0+cpu \
    torchaudio==0.9.0 \
    -f https://download.pytorch.org/whl/torch_stable.html
# Install dependencies
RUN pip3 install -r requirements.txt
RUN python3 setup_matplotlib.py
# sandbox user with uid:1450
# RUN useradd sandbox -u 1450
# USER sandbox
WORKDIR /sandbox

