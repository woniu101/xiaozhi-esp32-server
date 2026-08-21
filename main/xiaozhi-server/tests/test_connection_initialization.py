import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

# Importing the production connection module normally validates the live
# manager-api configuration. Unit tests isolate the connection lifecycle and
# must not contact that external service during module import.
from config import settings
from core.utils.cache.manager import CacheType, cache_manager

settings.config_file_valid = True
cache_manager.set(
    CacheType.CONFIG,
    "main_config",
    {
        "log": {
            "log_level": "ERROR",
            "log_dir": "/tmp",
            "log_file": "xiaozhi-connection-tests.log",
        }
    },
)

import core.connection as connection_module
from core.connection import ConnectionHandler


class _Logger:
    def bind(self, **_kwargs):
        return self

    def error(self, *_args, **_kwargs):
        return None


class ConnectionInitializationTest(unittest.TestCase):
    def test_route_waits_until_full_runtime_is_ready(self):
        async def scenario():
            conn = object.__new__(ConnectionHandler)
            conn.initialization_completed_event = asyncio.Event()
            conn.bind_completed_event = asyncio.Event()
            conn.bind_completed_event.set()
            conn.need_bind = False

            handle_text = AsyncMock()
            with patch.object(connection_module, "handleTextMessage", handle_text):
                route_task = asyncio.create_task(conn._route_message('{"type":"listen"}'))
                await asyncio.sleep(0)

                self.assertFalse(route_task.done())
                handle_text.assert_not_awaited()

                conn.initialization_completed_event.set()
                await route_task

            handle_text.assert_awaited_once_with(conn, '{"type":"listen"}')

        asyncio.run(scenario())

    def test_hello_is_available_for_capability_negotiation_during_initialization(self):
        async def scenario():
            conn = object.__new__(ConnectionHandler)
            conn.initialization_completed_event = asyncio.Event()
            conn.bind_completed_event = asyncio.Event()
            conn.bind_completed_event.set()
            conn.need_bind = False

            handle_text = AsyncMock()
            hello = '{"type":"hello","features":{"mcp":true}}'
            with patch.object(connection_module, "handleTextMessage", handle_text):
                await asyncio.wait_for(conn._route_message(hello), timeout=0.1)

            handle_text.assert_awaited_once_with(conn, hello)
            self.assertFalse(conn.initialization_completed_event.is_set())

        asyncio.run(scenario())

    def test_background_ready_event_is_set_after_companion_and_prompt_setup(self):
        async def scenario():
            conn = object.__new__(ConnectionHandler)
            conn.loop = asyncio.get_running_loop()
            conn.executor = ThreadPoolExecutor(max_workers=1)
            conn.initialization_completed_event = asyncio.Event()
            conn.logger = _Logger()
            calls = []

            async def initialize_private_config():
                calls.append("config")

            async def initialize_companion():
                calls.append("companion")

            def initialize_components():
                self.assertFalse(conn.initialization_completed_event.is_set())
                calls.append("components")

            conn._initialize_private_config_async = initialize_private_config
            conn._initialize_companion = initialize_companion
            conn._initialize_components = initialize_components

            try:
                await conn._background_initialize()
            finally:
                conn.executor.shutdown(wait=True)

            self.assertEqual(["config", "companion", "components"], calls)
            self.assertTrue(conn.initialization_completed_event.is_set())

        asyncio.run(scenario())

    def test_background_failure_releases_waiting_messages(self):
        async def scenario():
            conn = object.__new__(ConnectionHandler)
            conn.loop = asyncio.get_running_loop()
            conn.executor = ThreadPoolExecutor(max_workers=1)
            conn.initialization_completed_event = asyncio.Event()
            conn.logger = _Logger()

            async def initialize_private_config():
                raise RuntimeError("config unavailable")

            conn._initialize_private_config_async = initialize_private_config

            try:
                await conn._background_initialize()
            finally:
                conn.executor.shutdown(wait=True)

            self.assertTrue(conn.initialization_completed_event.is_set())

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
