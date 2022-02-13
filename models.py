import json
from typing import List, Optional, Union
from deepdiff import DeepDiff, DeepHash


class User:
    def __init__(
        self, user_id: str, email: str, first_name: str, last_name: str, role: str
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.role = role

    def __hash__(self) -> int:
        return hash(self.email)

    def __eq__(self, __o: object) -> bool:
        if self.__class__ != __o.__class__:
            return False
        other: User = __o

        return self.email == other.email


class Group:

    GROUP_TYPE_MANAGED_GROUP = "MANAGED_GROUP"
    GROUP_TYPE_USER_DEFINED = ""

    def __init__(
        self,
        name: str,
        tags: List[str] = None,
        group_type: str = None,
        cloud_type: str = None,
        cloud_data: dict = None,
    ) -> None:
        self.name = name
        self.tags = [] if tags is None else tags
        self._tags = tuple() if tags is None else tuple(tags)
        self.group_type = group_type
        self.cloud_type = cloud_type
        self.cloud_data = cloud_data

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, __o: object) -> bool:
        if self.__class__ != __o.__class__:
            return False
        other: Group = __o

        return self.name == other.name and self._tags == other._tags

    def __str__(self) -> str:
        fields = vars(self)
        del fields["_tags"]
        return json.dumps(fields, indent=4)


class CommunicationSettings:
    def __init__(
        self,
        channel: str,
        enabled: bool,
        filter: dict,
        configuration: dict,
    ) -> None:
        self.channel = channel
        self.enabled = enabled
        self.filter = filter
        self.configuration = configuration
        self._obj = {
            "channel": channel,
            "filter": filter,
            "configuration": configuration,
        }

    def __hash__(self) -> int:
        dh = DeepHash(self._obj)[self._obj]
        return hash(dh)

    def __eq__(self, __o: object) -> bool:
        diff = DeepDiff(self._obj, __o._obj, ignore_order=True)
        return len(diff) == 0

    def __str__(self) -> str:
        fields = vars(self)
        del fields["_obj"]
        return json.dumps(fields, indent=4)


class Note:
    def __init__(self, note: str, created_by: str, created_ts: int) -> None:
        self.note = note
        self.created_by = created_by
        self.created_ts = created_ts

    def __str__(self) -> str:
        return json.dumps(vars(self), indent=4)


class Check:
    def __init__(
        self,
        check_id: str,
        rule_id: str,
        region: str,
        resource_name: str,
        resource: str,
        message: str,
        suppressed: Optional[bool],
        suppressed_until: Optional[int],
        notes: List[Note] = None,
    ) -> None:
        self.check_id = check_id
        self.rule_id = rule_id
        self.region = region
        self.resource_name = resource_name
        self.resource = resource
        self.message = message
        self.suppressed = suppressed
        self.suppressed_until = suppressed_until
        self.notes = notes if notes is not None else []

    def __hash__(self) -> int:
        return hash(f"{self.rule_id}|{self.resource_name}|{self.resource}")

    def __eq__(self, __o: object) -> bool:
        if self.__class__ != __o.__class__:
            return False
        other: Check = __o

        return (
            self.rule_id == other.rule_id
            and self.region == other.region
            and self.resource_name == other.resource_name
            and self.resource == other.resource
        )

    def __str__(self) -> str:
        return json.dumps(vars(self), indent=4)


class Rule:
    def __init__(self, setting: dict, notes: List[Note] = None) -> None:
        self.setting = setting
        self.notes = notes if notes is not None else []
        self.rule_id = setting["id"]
        self.enabled = setting["enabled"]
        self.configured = setting.get("configured", False)

    def __hash__(self) -> int:
        return hash(self.rule_id)

    def __eq__(self, __o: object) -> bool:
        if self.__class__ != __o.__class__:
            return False
        other: Rule = __o
        return self.rule_id == other.rule_id


class Profile:
    def __init__(self, settings: dict) -> None:
        self.settings = settings
        # data = settings["data"]
        # attrib = data["attributes"]
        # self.profile_id = data.get("id", "")
        # self.name = attrib["name"]
        # self.description = attrib.get("description", "")

    @property
    def profile_id(self) -> str:
        return self.settings["data"].get("id", "")

    @profile_id.setter
    def profile_id(self, profile_id: str) -> None:
        self.settings["data"]["id"] = profile_id

    @property
    def name(self) -> str:
        return self.settings["data"]["attributes"]["name"]

    @name.setter
    def name(self, name: str) -> None:
        self.settings["data"]["attributes"]["name"] = name

    @property
    def description(self) -> str:
        return self.settings["data"]["attributes"].get("description", "")

    @description.setter
    def description(self, description: str) -> None:
        self.settings["data"]["attributes"]["description"] = description

    @property
    def included_rules(self) -> Union[List[dict], None]:
        return self.settings.get("included")

    def delete_profile_id(self) -> None:
        if "id" in self.settings["data"]:
            del self.settings["data"]["id"]

    def delete_meta(self) -> None:
        if "meta" in self.settings:
            del self.settings["meta"]

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, __o: object) -> bool:
        if self.__class__ != __o.__class__:
            return False
        other: Profile = __o
        return self.name == other.name
