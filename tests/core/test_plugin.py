import pytest
from src.core.plugin import Plugin

class TestPlugin:
    class MockBot:
        def __init__(self):
            self.called = False

    @pytest.fixture
    def mock_bot(self):
        return self.MockBot()

    @pytest.fixture
    def plugin(self, mock_bot):
        return Plugin(mock_bot)

    def test_plugin_init(self, plugin, mock_bot):
        assert plugin.bot == mock_bot

    @pytest.mark.asyncio
    async def test_plugin_on_load(self, plugin):
        await plugin.on_load()
        # Verify it doesn't raise any exceptions

    @pytest.mark.asyncio
    async def test_plugin_on_unload(self, plugin):
        await plugin.on_unload()
        # Verify it doesn't raise any exceptions
