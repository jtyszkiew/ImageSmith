import pytest
import asyncio
import sys

# This is needed for Windows testing
if sys.platform == 'win32':
    @pytest.fixture
    def event_loop():
        loop = asyncio.ProactorEventLoop()
        yield loop
        loop.close()
else:
    @pytest.fixture
    def event_loop():
        """Create an instance of the default event loop for each test case."""
        policy = asyncio.get_event_loop_policy()
        loop = policy.new_event_loop()
        yield loop
        loop.close()

@pytest.fixture(autouse=True)
def setup_test_event_loop(event_loop):
    """Fixture to automatically set up the event loop for all async tests."""
    asyncio.set_event_loop(event_loop)
    return event_loop
