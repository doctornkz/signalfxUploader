FROM python

# Installing latest SignalFX and Taurus as dependency
RUN pip install --upgrade pip \
    && pip install --upgrade setuptools \
    && git clone https://github.com/doctornkz/signalfxUploader.git \
    && cd signalfxUploader \
    && pip install .
