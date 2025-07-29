"""Simple test to verify async testing setup."""
import pytest


@pytest.mark.asyncio
async def test_simple_async():
    """Test simple async function."""
    assert True


def test_simple_sync():
    """Test simple sync function."""
    assert True