import os
from setuptools import setup, find_packages
import fixture_magic
BASE_DIR = os.path.abspath(os.path.split(__file__)[0])
os.chdir(BASE_DIR)
setup(
        name='django-fixture-magic',
        version=fixture_magic.__version__,
        description='A few extra management tools to handle fixtures.',
        long_description=open(os.path.join(BASE_DIR, 'README.rst')).read(),
        author='Dave Dash',
        author_email='dd+pypi@davedash.com',
        url='http://github.com/davedash/django-fixture-magic',
        license='BSD',
        packages=find_packages(),
        include_package_data=True,
        classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: Web Environment',
            'Framework :: Django',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: BSD License',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Topic :: Software Development :: Libraries :: Python Modules',
        ],
    )

