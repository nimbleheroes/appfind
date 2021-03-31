from setuptools import setup

setup(
    name='appfind',
    version='0.1',
    py_modules=['appfind'],
    install_requires=[
        'Click',
    ],
    entry_points='''
        [console_scripts]
        appfind=appfind:cli
    ''',
)
