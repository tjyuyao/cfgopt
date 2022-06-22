from setuptools import setup

# read the contents of README file
from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(name='cfgopt',
      version='0.4.1',
      description='You only configure your deep learning experiment once with cfgopt.',
      url='http://github.com/tjyuyao/cfgopt',
      author='Yuyao Huang',
      author_email='huangyuyao@outlook.com',
      license='MIT',
      packages=['cfgopt'],
      entry_points={
          'console_scripts': ['cfgoptrun=cfgopt.main:main'],
      },
      long_description=long_description,
      long_description_content_type='text/markdown',
      zip_safe=False)
