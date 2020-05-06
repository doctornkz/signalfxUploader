from setuptools import setup

setup(
    name="signalfx",
    version="0.1",

    author="Oles Pisarenko",
    author_email="doctornkz@ya.ru",
    license="MIT",
    description="Python module for Taurus to stream reports to SignalFX",
    url='https://github.com/doctornkz/signalfxUploader',
    keywords=[],

    packages=["signalfx"],
    install_requires=['bzt'],
    include_package_data=True,
)
