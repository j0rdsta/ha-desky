#!/bin/bash
# Run tests for the Desky Desk integration

echo "Installing test dependencies..."
pip install -r requirements_test.txt

echo "Running tests with coverage..."
pytest tests/ -v --cov=custom_components.desky_desk --cov-report=term-missing --cov-report=html

echo "Tests completed. Coverage report available in htmlcov/index.html"