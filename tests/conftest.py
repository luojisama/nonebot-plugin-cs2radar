import atexit
import os
import tempfile

import nonebot

_test_dir = tempfile.TemporaryDirectory()
_original_cwd = os.getcwd()
os.chdir(_test_dir.name)
atexit.register(os.chdir, _original_cwd)
atexit.register(_test_dir.cleanup)

nonebot.init(
    driver="~none",
    localstore_use_cwd=True,
    superusers={"10000"},
    personification_api_key="must-not-be-reused",
)
nonebot.load_plugin("nonebot_plugin_cs2radar")
