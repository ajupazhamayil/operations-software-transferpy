"""transferpy."""
from setuptools import setup

setup(
    name='transferpy',
    description='Fast tool for transferring files',
    version='0.1',
    url='',
    packages=(
        'transferpy',
        'transferpy.RemoteExecution'
    ),
    install_requires=[
        'cumin',
    ],
    tests_require=[
        'flake8',
        'nose',
        'coverage',
    ],
    entry_points={
        # TODO: Expand
        'console_scripts': [
            'transferpy = transferpy.transfer:main',
        ],
    },
    test_suite='transferpy.test',
)
