from integrations import firebase_sync as _pkg

for _name in _pkg.__all__:
    if _name != "firebase_app":
        globals()[_name] = getattr(_pkg, _name)


def __getattr__(name):
    return getattr(_pkg, name)
