import os
from typing import Any, Dict

import requests

from conformity_migration.conformity_api import (  # WorkaroundFixConformityAPI,
    ConformityAPI,
    DefaultConformityAPI,
)


class SessionDecorator(requests.Session):
    def __init__(self, sess: requests.Session) -> None:
        self._sess = sess

    def __getattr__(self, name):
        return getattr(self._sess, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_sess":
            return super().__setattr__(name, value)
        return setattr(self._sess, name, value)


class CustomContentTypeSession(SessionDecorator):
    def __init__(self, sess: requests.Session, content_type: str) -> None:
        super().__init__(sess)
        self._content_type = content_type

    def request(self, *args, **kwargs) -> requests.Response:
        headers = kwargs.setdefault("headers", dict())
        headers["Content-Type"] = self._content_type
        return super().request(*args, **kwargs)


class AppDependencies:
    def __init__(self, conf: Dict[str, Any]) -> None:
        self._conf = conf

    def custom_content_type_http(self) -> requests.Session:
        sess = requests.Session()
        http_content_type = os.getenv("C1_HTTP_CONTENT_TYPE")
        if http_content_type:
            sess = CustomContentTypeSession(sess=sess, content_type=http_content_type)
        return sess

    def legacy_conformity_api(self) -> ConformityAPI:
        api_key = self._conf["LEGACY_CONFORMITY"]["API_KEY"]
        base_url = self._conf["LEGACY_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(
            api_key=api_key, base_url=base_url, http=requests.Session()
        )
        return api

    def c1_conformity_api(self) -> ConformityAPI:
        api_key = self._conf["CLOUD_ONE_CONFORMITY"]["API_KEY"]
        base_url = self._conf["CLOUD_ONE_CONFORMITY"]["API_BASE_URL"]

        api = DefaultConformityAPI(
            api_key=api_key, base_url=base_url, http=self.custom_content_type_http()
        )
        return api
        # return WorkaroundFixConformityAPI(api)


def dependencies(conf: Dict[str, Any]) -> AppDependencies:
    return AppDependencies(conf)
