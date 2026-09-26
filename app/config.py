from __future__ import annotations

import os


APP_NAME = "همراه مالی"
APP_VERSION = "0.7.0"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "testserver"}
MAX_PAGE_SIZE = int(os.getenv("FINANCIAL_ASSISTANT_MAX_PAGE_SIZE", "100"))
