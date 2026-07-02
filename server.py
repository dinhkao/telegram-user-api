from __future__ import annotations

import asyncio

from server_app.bootstrap import main
from server_app import state as _state


def __getattr__(name):
    if name in {"_client", "_tg_gateway", "_donhang_db", "ws_clients"}:
        return getattr(_state, name)
    raise AttributeError(name)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
