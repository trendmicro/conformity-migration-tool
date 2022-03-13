import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from requests import Response, Session
from requests.adapters import BaseAdapter, HTTPAdapter
from urllib3 import Retry

from conformity_migration.conformity_api import (
    CloudOneConformityAPI,
    DefaultConformityAPI,
    LegacyConformityAPI,
    WorkaroundFixConformityAPI,
)

from .utils import str2bool

log_backoff = str2bool(os.getenv("LOG_BACKOFF", "False"))
if log_backoff:
    logging.getLogger("backoff").addHandler(logging.StreamHandler())


script_dirpath = Path(__file__).parent
script_name = Path(sys.argv[0]).name

USER_CONF_FILENAME = "user_config.yml"
APP_CONF_FILENAME = "config.yml"


def _load_yaml_config(yaml_path: Path):
    with open(yaml_path, mode="r") as fh:
        return yaml.load(fh, Loader=yaml.SafeLoader)


def app_config_path() -> Path:
    return script_dirpath.joinpath(APP_CONF_FILENAME)


@lru_cache(maxsize=1)
def app_config() -> Dict[str, Any]:
    return _load_yaml_config(app_config_path())


def ask_user_to_run_configure():
    print(
        f"Please configure migration tool by running this command: {script_name} configure"
    )
    sys.exit(1)


def user_config_path() -> Path:
    return Path(USER_CONF_FILENAME)


@lru_cache(maxsize=1)
def user_config() -> Dict[str, Any]:
    path = user_config_path()
    if not path.exists():
        ask_user_to_run_configure()
    return _load_yaml_config(path)


class TimeoutHTTPAdapter(BaseAdapter):
    def __init__(self, adapter: BaseAdapter, conn_timeout: float, read_timeout: float):
        self._adapter = adapter
        self._conn_timeout = conn_timeout
        self._read_timeout = read_timeout

    def send(self, *args, **kwargs) -> Response:
        timeout = (self._conn_timeout, self._read_timeout)
        kwargs["timeout"] = timeout
        return self._adapter.send(*args, **kwargs)

    def close(self) -> None:
        return self._adapter.close()


def _http() -> Session:
    sess = Session()

    app_conf = app_config()

    adapter = HTTPAdapter(
        max_retries=Retry(
            total=None,
            connect=0,
            read=0,
            redirect=0,
            other=0,
            backoff_factor=app_conf["API_RETRY_BACKOFF_FACTOR"],
            status=app_conf["API_RETRY_COUNT"],  # max retries for any status_forcelist
            status_forcelist=app_conf["API_RETRY_HTTP_STATUSES"],
            allowed_methods=False,  # false means retry on all Methods
            respect_retry_after_header=True,
        )
    )

    adapter = TimeoutHTTPAdapter(
        adapter,
        conn_timeout=app_conf["API_CONNECTION_TIMEOUT"],
        read_timeout=app_conf["API_READ_TIMEOUT"],
    )

    sess.mount("https://", adapter=adapter)
    return sess


def legacy_conformity_api() -> LegacyConformityAPI:
    user_conf = user_config()
    api_key = user_conf["LEGACY_CONFORMITY"]["API_KEY"]
    base_url = user_conf["LEGACY_CONFORMITY"]["API_BASE_URL"]

    api = DefaultConformityAPI(api_key=api_key, base_url=base_url, http=_http())
    api = LegacyConformityAPI(api)
    return api


def c1_conformity_api() -> CloudOneConformityAPI:
    user_conf = user_config()
    api_key = user_conf["CLOUD_ONE_CONFORMITY"]["API_KEY"]
    base_url = user_conf["CLOUD_ONE_CONFORMITY"]["API_BASE_URL"]

    api = DefaultConformityAPI(api_key=api_key, base_url=base_url, http=_http())
    api = WorkaroundFixConformityAPI(api)
    api = CloudOneConformityAPI(api)
    return api
