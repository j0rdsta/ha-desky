#!/bin/bash
# Run tests for the Desky Desk integration
set -e

echo "Installing test dependencies..."
pip install -r requirements_test.txt
pip install -r <(python script/ha_test_requirements.py)

echo "Running tests with coverage..."
pytest --cov --cov-report=term-missing --cov-report=html

echo "Tests completed. Coverage report available in htmlcov/index.html"
