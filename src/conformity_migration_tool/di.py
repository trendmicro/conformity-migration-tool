import logging
import os
from typing import Any, Dict

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

        adapter = HTTPAdapter(
            max_retries=Retry(
                total=None,
                connect=0,
                read=0,
                redirect=0,
                other=0,
                backoff_factor=5,
                status=3,  # number of retries for failed statuses that matches any of status_forcelist
                status_forcelist=[429, 500, 501, 502, 503, 504],
                allowed_methods=False,  # false means retry on all Methods
                respect_retry_after_header=True,
            )
        )
        adapter = TimeoutHTTPAdapter(adapter, conn_timeout=5, read_timeout=60)

        sess.mount("https://", adapter=adapter)
        return sess

    def legacy_conformity_api(self) -> LegacyConformityAPI:
        api_key = self._conf["LEGACY_CONFORMITY"]["API_KEY"]
        base_url = self._conf["LEGACY_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(
            api_key=api_key, base_url=base_url, http=self._http()
        )
        api = LegacyConformityAPI(api)
        return api

    def c1_conformity_api(self) -> CloudOneConformityAPI:
        api_key = self._conf["CLOUD_ONE_CONFORMITY"]["API_KEY"]
        base_url = self._conf["CLOUD_ONE_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(
            api_key=api_key, base_url=base_url, http=self._http()
        )
        api = WorkaroundFixConformityAPI(api)
        api = CloudOneConformityAPI(api)
        return api


def dependencies(conf: Dict[str, Any]) -> AppDependencies:
    return AppDependencies(conf)
