import logging
import os
from typing import Any, Dict

from requests import Session

from conformity_migration.conformity_api import (
    ConformityAPI,
    DefaultConformityAPI,
    WorkaroundFixConformityAPI,
)

from .utils import str2bool


class AppDependencies:
    def __init__(self, conf: Dict[str, Any]) -> None:
        self._conf = conf
        log_backoff = str2bool(os.getenv("LOG_BACKOFF", "False"))
        if log_backoff:
            logging.getLogger("backoff").addHandler(logging.StreamHandler())

    def legacy_conformity_api(self) -> ConformityAPI:
        api_key = self._conf["LEGACY_CONFORMITY"]["API_KEY"]
        base_url = self._conf["LEGACY_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(api_key=api_key, base_url=base_url, http=Session())
        return api

    def c1_conformity_api(self) -> ConformityAPI:
        api_key = self._conf["CLOUD_ONE_CONFORMITY"]["API_KEY"]
        base_url = self._conf["CLOUD_ONE_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(api_key=api_key, base_url=base_url, http=Session())
        return WorkaroundFixConformityAPI(api)


def dependencies(conf: Dict[str, Any]) -> AppDependencies:
    return AppDependencies(conf)
