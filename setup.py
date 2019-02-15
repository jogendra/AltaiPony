import setuptools

with open("README.rst", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="altaipony",
    version="0.0.1",
    author="Ekaterina Ilin",
    author_email="eilin@aip.de",
    description="A flare finding and analysis package for K2",
    long_description=long_description,
    long_description_content_type="text/restructuredtext",
    url="https://github.com/jogendra/AltaiPony",
    packages=setuptools.find_packages(),
    install_requires = ['lightkurve>=1.0b21','numpy>=1.15.1', 'pandas>=0.23.4',
                        'progressbar2'],
    dependency_links=['https://github.com/OxES/k2sc.git'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
)
