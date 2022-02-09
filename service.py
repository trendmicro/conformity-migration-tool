from urllib.parse import quote
from typing import List, Iterable, Optional, Dict, Any
import json

import requests
from models import User, Group, CommunicationSettings, Check


class ConformityService:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.strip().rstrip("/")
        self._headers = {
            "Authorization": f"ApiKey {self._api_key}",
            "Content-Type": "application/vnd.api+json",
        }
        self._organisation_external_id: str = None

    # def _raise_for_status(self, resp):
    #     try:
    #         resp.raise_for_status()
    #     except BaseException as e:
    #         print()
    #         print(resp.text)
    #         print()
    #         raise e

    def _get_request(self, url, params=None):
        resp = requests.get(url=url, headers=self._headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post_request(self, url, data):
        return self._exec_request("POST", url, data)

    def _patch_request(self, url, data):
        return self._exec_request("PATCH", url, data)

    def _exec_request(self, method, url, data):
        json_data = json.dumps(data, indent=4)
        resp = requests.request(
            method=method,
            url=url,
            data=json_data,
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    def list_accounts(self):
        res = self._get_request(f"{self._base_url}/accounts")
        return res["data"]

    def get_organisation_external_id(self) -> str:
        if not self._organisation_external_id:
            res = self._get_request(f"{self._base_url}/organisation/external-id")
            self._organisation_external_id = res["data"]["id"]
        return self._organisation_external_id

    def get_account_access_configuration(self, acct_id) -> dict:
        res = self._get_request(f"{self._base_url}/accounts/{acct_id}/access")
        return res["attributes"]["configuration"]

    def add_aws_account(
        self,
        name: str,
        environment: str,
        role_arn: str,
        external_id: str,
        subscription_type="advanced",
    ) -> dict:

        res = self._post_request(
            url=f"{self._base_url}/accounts",
            data={
                "data": {
                    "attributes": {
                        "name": name,
                        "environment": environment,
                        "access": {
                            "keys": {"roleArn": role_arn, "externalId": external_id}
                        },
                        "subscriptionType": subscription_type,
                    },
                }
            },
        )

        return res["data"]

    def add_azure_subscription(
        self,
        name: str,
        environment: str,
        subscription_id: str,
        active_directory_id: str,
    ) -> dict:

        res = self._post_request(
            url=f"{self._base_url}/accounts/azure",
            data={
                "data": {
                    "attributes": {
                        "name": name,
                        "environment": environment,
                        "access": {
                            "subscriptionId": subscription_id,
                            "activeDirectoryId": active_directory_id,
                        },
                    },
                }
            },
        )

        return res["data"]

    def update_account(
        self, acct_id: str, name: str, environment: str, tags: List[str]
    ):
        res = self._patch_request(
            url=f"{self._base_url}/accounts/{acct_id}",
            data={
                "data": {
                    "attributes": {
                        "name": name,
                        "environment": environment,
                        "tags": tags,
                    },
                },
            },
        )
        return res

    def get_account_bot_settings(self, acct_id: str) -> dict:
        res = self._get_request(f"{self._base_url}/accounts/{acct_id}/settings/bot")
        return res["data"]["attributes"]["settings"]["bot"]

    def update_account_bot_settings(self, acct_id: str, settings: dict):
        res = self._patch_request(
            url=f"{self._base_url}/accounts/{acct_id}/settings/bot",
            data={
                "data": {"attributes": {"settings": {"bot": settings}}},
            },
        )
        return res

    def get_account_details(self, acct_id: str) -> dict:
        res = self._get_request(f"{self._base_url}/accounts/{acct_id}")
        return res["data"]

    def get_account_rules_settings(self, acct_id: str) -> list:
        try:
            res = self._get_request(
                f"{self._base_url}/accounts/{acct_id}/settings/rules"
            )
            return res["data"]["attributes"]["settings"]["rules"]
        except requests.exceptions.HTTPError as err:
            resp: requests.Response = err.response
            if resp.status_code == 404:
                return []
            raise err

    def update_account_rule_settings(
        self, acct_id: str, settings: dict, note: str = "Copied from API"
    ):
        res = self._patch_request(
            url=f"{self._base_url}/accounts/{acct_id}/settings/rules",
            data={
                "data": {"attributes": {"note": note, "ruleSettings": settings}},
            },
        )
        return res

    def get_group_details(self, group_id: str) -> dict:
        res = self._get_request(f"{self._base_url}/groups/{group_id}")
        return res["data"][0]

    def list_groups(self, include_group_types: List[str] = None) -> List[Group]:
        res = self._get_request(f"{self._base_url}/groups")
        if include_group_types is None:
            include_group_types = []
        groups = []
        for g in res["data"]:
            gattrib = g["attributes"]
            group_type = gattrib.get("group-type", Group.GROUP_TYPE_USER_DEFINED)
            if include_group_types and group_type not in include_group_types:
                continue
            group = Group(
                name=gattrib["name"],
                tags=gattrib.get("tags"),
                group_type=group_type,
                cloud_type=gattrib.get("cloud-type"),
                cloud_data=gattrib.get("cloud-data"),
            )
            groups.append(group)
        return groups

    def create_group(self, name, tags=List[str]):
        res = self._post_request(
            url=f"{self._base_url}/groups",
            data={"data": {"attributes": {"name": name, "tags": tags}}},
        )
        return res["data"]

    def get_organisation_id(self) -> str:
        res = self._get_request(f"{self._base_url}/users")
        return res["data"][0]["relationships"]["organisation"]["data"]["id"]

    def list_all_users(self) -> List[dict]:
        res = self._get_request(f"{self._base_url}/users")
        return res["data"]

    def get_all_users(self) -> List[User]:
        res = self._get_request(f"{self._base_url}/users")
        users = []
        for u in res["data"]:
            user_attrib = u["attributes"]
            email: str = user_attrib.get("email")
            if not email:  # skip users who does not have email, e.g. Api key user
                continue
            users.append(
                User(
                    user_id=u["id"],
                    email=email,
                    first_name=user_attrib["first-name"],
                    last_name=user_attrib["last-name"],
                    role=user_attrib["role"],
                )
            )
        return users

    def get_user_details(self, user_id: str) -> dict:
        res = self._get_request(f"{self._base_url}/users/{user_id}")
        return res["data"]

    def invite_user(self, user: dict) -> List[dict]:
        attrib = user["attributes"]
        first_name = attrib["first-name"]
        last_name = attrib["last-name"]
        email = attrib["email"]
        role = attrib["role"]

        data = {
            "data": {
                "attributes": {
                    "firstName": first_name,
                    "lastName": last_name,
                    "email": email,
                    "role": role,
                }
            }
        }
        if role == "USER":
            data["data"]["attributes"]["accessList"] = user["relationships"][
                "accountAccessList"
            ]

        res = self._post_request(
            url=f"{self._base_url}/users",
            data=data,
        )
        return res["data"]

    def get_communication_settings(self, acct_id: str) -> List[CommunicationSettings]:
        if acct_id:
            params = {"accountId": acct_id}
        else:
            params = {"includeParents": True}
        res = self._get_request(
            f"{self._base_url}/settings/communication", params=params
        )
        # return res["data"]
        settings: List[CommunicationSettings] = []
        for s in res["data"]:
            attrib = s["attributes"]
            settings.append(
                CommunicationSettings(
                    channel=attrib["channel"],
                    enabled=attrib["enabled"],
                    filter=attrib.get("filter"),
                    configuration=attrib.get("configuration"),
                )
            )
        return settings

    def create_communication_settings(
        self, com_settings: List[CommunicationSettings], acct_id: str, org_id: str
    ):
        # for cs in com_settings:
        #     print(cs)
        settings = []
        for cs in com_settings:
            if not cs.configuration:
                continue
            s: dict = {
                "type": "settings",
                "attributes": {
                    "type": "communication",
                    "enabled": cs.enabled,
                    "channel": cs.channel,
                    "filter": cs.filter,
                    "configuration": cs.configuration,
                },
                "relationships": {
                    "account": {
                        "data": None,
                    },
                    "organisation": {
                        "data": {
                            "type": "organisations",
                            "id": org_id,
                        }
                    },
                },
            }
            if acct_id:
                s["relationships"]["account"]["data"] = {
                    "type": "accounts",
                    "id": acct_id,
                }

            settings.append(s)

        res = self._post_request(
            url=f"{self._base_url}/settings/communication", data={"data": settings}
        )
        return res

    def create_azure_directory(
        self, name: str, directory_id: str, app_client_id: str, app_client_key: str
    ):
        res = self._post_request(
            url=f"{self._base_url}/azure/active-directories",
            data={
                "data": {
                    "attributes": {
                        "name": name,
                        "directoryId": directory_id,
                        "applicationId": app_client_id,
                        "applicationKey": app_client_key,
                    }
                }
            },
        )
        return res["data"]

    def get_checks(
        self, acct_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> Iterable[Check]:

        params = {
            "accountIds": acct_id,
            "page[size]": 100,
        }
        if filters:
            for filter_name, filter_val in filters.items():
                params[f"filter[{filter_name}]"] = filter_val

        total_items = 0
        page_num = 0
        while True:
            params["page[number]"] = page_num
            res = self._get_request(
                f"{self._base_url}/checks",
                params=params,
            )
            data = res["data"]
            for c in data:
                attrib: dict = c["attributes"]
                region = attrib["region"]
                resource_name = attrib.get("resourceName", "")
                resource = attrib.get("resource", "")
                yield Check(
                    check_id=c["id"],
                    rule_id=c["relationships"]["rule"]["data"]["id"],
                    region=region,
                    resource_name=resource_name,
                    resource=resource,
                    message=attrib["message"],
                    suppressed=attrib.get("suppressed"),
                    suppressed_until=attrib.get("suppressed-until"),
                )
            total_items += len(data)
            meta = res["meta"]
            # print(meta)
            # print(f"total_items: {total_items}")
            if total_items >= meta["total"]:
                break
            page_num += 1

    def get_suppressed_checks(self, acct_id: str) -> Iterable[Check]:
        return self.get_checks(
            acct_id=acct_id, filters={"suppressed": True, "suppressedFilterMode": "v2"}
        )

    def suppress_check(
        self, check_id: str, suppressed_until: Optional[int], note="Copied from API"
    ):
        res = self._patch_request(
            url=f"{self._base_url}/checks/{quote(check_id, safe='')}",
            data={
                "data": {
                    "type": "checks",
                    "attributes": {
                        "suppressed": True,
                        "suppressed-until": suppressed_until,
                    },
                },
                "meta": {
                    "note": note,
                },
            },
        )
        return res["data"]

    def is_bot_scan_done(self, acct_id: str) -> bool:
        res = self._get_request(f"{self._base_url}/accounts/{acct_id}")
        attrib = res["data"]["attributes"]
        bot_status = attrib.get("bot-status")
        return bot_status is None
