from setuptools import setup, find_packages

setup(
    name="superhelperhxpro",
    version="1.0.4",
    author="Suresh-pyhobbyist",
    description="An intelligent command-line assistant to organize and manage files effortlessly.",
    long_description=open("docs/readme.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/Suresh-pyhobbyist/superhelperhxpro",
    packages=find_packages(where="src"),
    package_dir={"": "src"},  # Explicitly define package location
    install_requires=[],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "superhxpro=superhelperhxpro.main:main"  # Adjust to match your `main.py` structure
        ]
    }
)
