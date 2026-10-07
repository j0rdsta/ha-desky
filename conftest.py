"""Root pytest configuration.

`pytest_plugins` is only honoured in the rootdir conftest, so the Home Assistant
test harness is registered here rather than in `tests/conftest.py`.
"""

pytest_plugins = ["pytest_homeassistant_custom_component"]
