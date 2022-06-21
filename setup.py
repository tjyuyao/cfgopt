from setuptools import setup

setup(name='cfgopt',
      version='0.3.0',
      description='You only configure your deep learning experiment once with cfgopt.',
      url='http://github.com/tjyuyao/cfgopt',
      author='Yuyao Huang',
      author_email='huangyuyao@outlook.com',
      license='MIT',
      packages=['cfgopt'],
      entry_points={
          'console_scripts': ['cfgoptrun=cfgopt.main:main'],
      },
      zip_safe=False)
