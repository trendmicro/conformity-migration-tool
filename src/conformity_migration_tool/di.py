import logging
import os
from typing import Any, Dict

from requests import Response, Session
from requests.adapters import BaseAdapter

from conformity_migration.conformity_api import (
    ConformityAPI,
    DefaultConformityAPI,
    WorkaroundFixConformityAPI,
)

from .utils import str2bool


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


class AppDependencies:
    def __init__(self, conf: Dict[str, Any]) -> None:
        self._conf = conf
        log_backoff = str2bool(os.getenv("LOG_BACKOFF", "False"))
        if log_backoff:
            logging.getLogger("backoff").addHandler(logging.StreamHandler())

    def _http(self) -> Session:
        sess = Session()

        url_prefix = "https://"
        adapter = sess.get_adapter(url=url_prefix)
        adapter = TimeoutHTTPAdapter(adapter, conn_timeout=5, read_timeout=60)

        sess.mount(url_prefix, adapter=adapter)
        return sess

    def legacy_conformity_api(self) -> ConformityAPI:
        api_key = self._conf["LEGACY_CONFORMITY"]["API_KEY"]
        base_url = self._conf["LEGACY_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(
            api_key=api_key, base_url=base_url, http=self._http()
        )
        return api

    def c1_conformity_api(self) -> ConformityAPI:
        api_key = self._conf["CLOUD_ONE_CONFORMITY"]["API_KEY"]
        base_url = self._conf["CLOUD_ONE_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(
            api_key=api_key, base_url=base_url, http=self._http()
        )
        return WorkaroundFixConformityAPI(api)


def dependencies(conf: Dict[str, Any]) -> AppDependencies:
    return AppDependencies(conf)
