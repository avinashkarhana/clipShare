from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open('VERSION', 'r') as f:
    version = f.read()

setup(
    name='clipboardSync',
    version=version,
    description='Sync clipboard between devices',
    author='Avinash Karhana',
    author_email='avinashkarhana1@gmail.com',
    url='https://github.com/avinashkarhana/clipboardSync',
    license='LGPLv2.1',
    long_description=long_description,
    long_description_content_type='text/markdown',


    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'flask',
        'Flask-SocketIO',
        'python-socketio',
        'pyclip',
        'pyperclip',
        'pycryptodome',
        'requests',
        'pyngrok',
        'netifaces',
        'zeroconf'
    ],

    entry_points={
        'console_scripts': [
            'clipboardSync=clipboardSync.clipboardsync:main'
        ]
    },

    classifiers=[
        'Environment :: Console',
        'Environment :: Web Environment',
        'Framework :: Flask',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)',
        'Natural Language :: English',
        'Operating System :: Microsoft :: Windows :: Windows 10',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.8',
        'Topic :: Communications',
        'Topic :: Internet',
        'Topic :: Utilities'
    ],

    keywords='clipboardSync clipboard sync encrypted secure',
    python_requires='>=3.6'
)
