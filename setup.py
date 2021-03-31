from setuptools import setup

setup(
    name='appfind',
    version='0.1',
    description='A universal app finder and wrapper',
    author='Anthony Kramer',
    author_email='anthony.kramer@gmail.com',
    py_modules=['appfind', 'click_default_group'],
    install_requires=[
        'click',
        'tabulate',
    ],
    entry_points='''
        [console_scripts]
        appfind=appfind:cli
    ''',
)
