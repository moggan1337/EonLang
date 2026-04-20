"""
EonLang Compiler Setup
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="eonlang",
    version="0.1.0",
    author="EonLang Team",
    author_email="info@eonlang.dev",
    description="A compiled language with LLVM backend",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/moggan1337/EonLang",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Compilers",
        "Topic :: Software Development :: Interpreters",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "eonlang=src.compiler:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
