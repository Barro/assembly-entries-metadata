from setuptools import setup, find_packages

setup(name='assembly-entries-metadata',
      version='1.0.0dev',
      description="Assembly competition entries metadata",
      author="Assembly Webcrew",
      author_email="web@assembly.org",
      url="https://archive.assembly.org/",
      license="AGPLv3",
      package_dir = {'': 'lib'},
      packages=find_packages('lib'),
      install_requires=['gdata==2.0.18'])
