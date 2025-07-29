# Desky Desk Integration Tests

This directory contains comprehensive unit tests for the Desky Desk Home Assistant integration.

## Test Structure

- `conftest.py` - Common fixtures and mocks used across all tests
- `test_init.py` - Tests for integration setup and teardown
- `test_coordinator.py` - Tests for the data update coordinator
- `test_bluetooth.py` - Tests for Bluetooth/BLE communication
- `test_config_flow.py` - Tests for configuration flow and device discovery
- `test_cover.py` - Tests for the cover entity (desk position control)
- `test_number.py` - Tests for the number entity (height control)
- `test_button.py` - Tests for button entities (preset positions)
- `test_binary_sensor.py` - Tests for binary sensor (collision detection)

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install -r requirements_test.txt
```

### Run All Tests

```bash
# Using the test runner script
./run_tests.sh

# Or directly with pytest
pytest tests/ -v
```

### Run Specific Tests

```bash
# Run a specific test file
pytest tests/test_bluetooth.py -v

# Run a specific test function
pytest tests/test_bluetooth.py::test_connect_success -v
```

### Coverage Reports

```bash
# Generate coverage report
pytest tests/ --cov=custom_components.desky_desk --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Test Fixtures

Key fixtures provided by `conftest.py`:

- `mock_config_entry` - Mock Home Assistant config entry
- `mock_ble_device` - Mock Bluetooth device
- `mock_bleak_client` - Mock Bleak BLE client
- `mock_coordinator_data` - Mock coordinator data dict
- `init_integration` - Fully initialized integration for testing

## Writing New Tests

When adding new features, ensure you:

1. Add corresponding test cases
2. Mock all external dependencies (Bluetooth, Home Assistant APIs)
3. Test both success and failure scenarios
4. Test edge cases and error conditions
5. Maintain high test coverage (aim for >90%)

## Continuous Integration

Tests run automatically on GitHub Actions for:
- Every push to main branch
- Every pull request
- Python versions 3.11 and 3.12

## Best Practices

1. Use async test functions for async code
2. Mock at the appropriate level (prefer mocking external APIs)
3. Use fixtures to reduce code duplication
4. Test one thing per test function
5. Use descriptive test names that explain what is being tested