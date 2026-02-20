"""
Async utilities for running coroutines safely
"""

import asyncio
import traceback

class AsyncRunner:
    """Helper class to run async functions safely"""
    
    @staticmethod
    def run_safe(coro):
        """Run a coroutine safely, handling event loop conflicts"""
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result = new_loop.run_until_complete(coro)
                    return result
                finally:
                    new_loop.close()
                    asyncio.set_event_loop(loop)
            else:
                return loop.run_until_complete(coro)
        except Exception as e:
            print(f"AsyncRunner error: {e}")
            traceback.print_exc()
            raise