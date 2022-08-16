from setuptools import setup
from os import path
base_dir = path.abspath(path.dirname(__file__))
setup(
  name='snapsave',
  packages=['snapsave'],
  include_package_data=True,
  version='0.1.6',
  license='MIT',
  description='Snapsave Downloader',
  author='Krypton Byte',
  author_email='galaxyvplus6434@gmail.com',
  url='https://github.com/krypton-byte/snapsave',
  keywords=[
    'facebook',
    'fbdown',
    'snapsave',
    'downloader'
  ],
  install_requires=[
          'httpx'
      ],
  classifiers=[
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3.9',
  ],
)