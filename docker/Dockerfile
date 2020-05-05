FROM ubuntu:18.04

ARG JMETER_VER=5.2.1

# Installing dependencies and phantom
RUN apt-get update \
    && apt-get install -y software-properties-common wget openjdk-8-jdk ant \
    python-pip build-essential python-dev libffi-dev git gfortran libssl-dev \
    && add-apt-repository ppa:yandex-load/main \
    && apt-get update \
    && apt-get install -y phantom phantom-ssl

# Installing Jmeter
RUN wget https://downloads.apache.org//jmeter/binaries/apache-jmeter-$JMETER_VER.tgz -q \
    && gunzip -c apache-jmeter-$JMETER_VER.tgz | tar xvf - \
    && mv apache-jmeter-$JMETER_VER jmeter \
    && rm -r apache-jmeter-$JMETER_VER.tgz

# Installing latest Yandex Tank
RUN pip install --upgrade pip \
    && pip install --upgrade setuptools \
    && git clone https://github.com/doctornkz/yandex-tank.git \
    && cd yandex-tank \
    && python setup.py build \
    && python setup.py install \
    && yandex-tank --version
 
