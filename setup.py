from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tasker-cli",
    version="0.1.0",
    author="Tasker Team",
    description="Lightweight CLI task tracker for AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "click>=8.1.0,<9.0.0",
        "rich>=13.0.0,<14.0.0",
    ],
    entry_points={
        "console_scripts": ["tasker=tasker.cli:cli"],
    },
    include_package_data=True,
)
