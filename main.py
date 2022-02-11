import os
import time
import json
from datetime import datetime, timezone
from typing import Dict, List, Set, Iterable
import yaml

from PyInquirer import prompt
from service import ConformityService
from cloud_accounts import get_cloud_account_adder
from models import Check, Group, User, CommunicationSettings, Note


def get_conf() -> dict:
    with open("config.yml", mode="r") as fh:
        return yaml.load(fh, Loader=yaml.SafeLoader)


APP_CONF = get_conf()


def get_api_conf(api_conf_file: str):
    with open(api_conf_file, mode="r") as fh:
        return yaml.load(fh, Loader=yaml.SafeLoader)


def ensure_api_conf_ready(api_conf_file: str):
    if not os.path.exists(api_conf_file):
        create_api_conf(api_conf_file)


def create_api_conf(api_conf_file: str):
    region_map = APP_CONF["REGION_API_URL"]
    region_choices = [*region_map.keys(), "Other"]
    legacy_region = ask_choices(
        msg="Legacy Conformity Region", choices=region_choices, default=1
    )
    legacy_api_url = region_map.get(legacy_region)
    if not legacy_api_url:
        legacy_api_url = ask_input(
            "Please input the Legacy Conformity API URL (e.g. https://us-west-2-api.cloudconformity.com/v1:"
        )
    legacy_api_key = ask_input("Legacy Conformity API KEY:", mask_input=True)

    c1_region = ask_choices(
        msg="CloudOne Conformity Region", choices=region_choices, default=1
    )
    c1_api_url = region_map.get(c1_region)
    if not c1_api_url:
        c1_api_url = ask_input(
            "Please input the CloudOne Conformity API URL (e.g. https://us-west-2-api.cloudconformity.com/v1:"
        )
    c1_api_key = ask_input("CloudOne Conformity API KEY:", mask_input=True)

    conf = {
        "CLOUD_ONE_CONFORMITY": {
            "API_KEY": c1_api_key,
            "API_BASE_URL": c1_api_url,
        },
        "LEGACY_CONFORMITY": {
            "API_KEY": legacy_api_key,
            "API_BASE_URL": legacy_api_url,
        },
    }
    with open(api_conf_file, mode="w") as fh:
        return yaml.dump(conf, fh)


def main():
    api_conf_file = "api_config.yml"
    ensure_api_conf_ready(api_conf_file)
    conf = get_api_conf(api_conf_file)

    legacy_svc = ConformityService(
        api_key=conf["LEGACY_CONFORMITY"]["API_KEY"],
        base_url=conf["LEGACY_CONFORMITY"]["API_BASE_URL"],
    )

    c1_svc = ConformityService(
        api_key=conf["CLOUD_ONE_CONFORMITY"]["API_KEY"],
        base_url=conf["CLOUD_ONE_CONFORMITY"]["API_BASE_URL"],
    )

    print("Retrieving Legacy Conformity Users", flush=True)
    legacy_users = legacy_svc.get_all_users()

    print("Retrieving CloudOne Conformity Users", flush=True)
    c1_users = c1_svc.get_all_users()

    invite_missing_users(legacy_users, c1_users)

    add_managed_groups(legacy_svc, c1_svc)

    create_user_defined_groups(legacy_svc, c1_svc)

    c1_org_id = c1_svc.get_organisation_id()

    print(
        "Copying communication channel settings (organisation-level)",
        end="",
        flush=True,
    )
    copy_communication_channel_settings(
        legacy_svc=legacy_svc,
        c1_svc=c1_svc,
        legacy_acct_id=None,
        c1_acct_id=None,
        legacy_users=legacy_users,
        c1_users=c1_users,
        c1_org_id=c1_org_id,
    )
    print(" - Done")

    c1_accts = c1_svc.list_accounts()
    legacy_accts = legacy_svc.list_accounts()

    for acct in legacy_accts:
        attrib = acct["attributes"]
        name = attrib["name"]
        environment = attrib["environment"]
        # tags = attrib["tags"]
        legacy_acct_id = acct["id"]

        cloud_type: str = attrib["cloud-type"]

        acct_adder = get_cloud_account_adder(
            cloud_type=cloud_type, legacy_svc=legacy_svc, c1_svc=c1_svc
        )
        if acct_adder is None:
            print(f"Does not support {cloud_type.upper()} yet! Skipping it.")

        print(f"Migrating {cloud_type.upper()} Account: {name} ({environment})")

        c1_acct_id: str = None
        exists, c1_acct_id = acct_adder.account_exists(c1_accts=c1_accts, acct=acct)
        if not exists:
            print("  --> Adding account to CloudOne Conformity")
            c1_acct_id = acct_adder.account_add(acct=acct)

        else:
            print("Account already exists in CloudOne Conformity!")
            if not (
                ask_confirmation(
                    "Continue migrating configurations (will overwrite existing ones)?"
                )
            ):
                continue

        migrate_account_configurations(
            legacy_svc=legacy_svc,
            c1_svc=c1_svc,
            legacy_acct_id=legacy_acct_id,
            c1_acct_id=c1_acct_id,
            legacy_users=legacy_users,
            c1_users=c1_users,
            c1_org_id=c1_org_id,
        )
        print()


def create_user_defined_groups(
    legacy_svc: ConformityService, c1_svc: ConformityService
):
    print("Creating groups")
    legacy_groups = legacy_svc.list_groups(
        include_group_types=[Group.GROUP_TYPE_USER_DEFINED]
    )
    c1_groups = set(
        c1_svc.list_groups(include_group_types=[Group.GROUP_TYPE_USER_DEFINED])
    )

    for group in legacy_groups:
        print(f" --> Group: {group.name}, Tags: {group.tags}", end="", flush=True)
        if group in c1_groups:
            print(" - Already exists! Skipping it.")
            continue
        c1_svc.create_group(name=group.name, tags=group.tags)
        print(" - Done")

    if not legacy_groups:
        print(" --> No group found.")


def add_managed_groups(legacy_svc: ConformityService, c1_svc: ConformityService):
    legacy_managed_groups = legacy_svc.list_groups(
        include_group_types=[Group.GROUP_TYPE_MANAGED_GROUP]
    )
    c1_managed_groups = c1_svc.list_groups(
        include_group_types=[Group.GROUP_TYPE_MANAGED_GROUP]
    )
    c1_managed_groups_set = set(c1_managed_groups)

    for mg in legacy_managed_groups:
        if mg in c1_managed_groups_set:
            # print(f"Managed Group {mg.name} ({mg.cloud_type.upper()}) already exists!")
            continue
        if mg.cloud_type == "azure":
            azure_conf = mg.cloud_data["azure"]
            directory_name = mg.name
            directory_id = azure_conf["directoryId"]
            app_client_id = azure_conf["applicationId"]
            app_client_key = prompt_azure_app_client_id(
                directory_name, directory_id, app_client_id
            )
            c1_svc.create_azure_directory(
                name=mg.name,
                directory_id=directory_id,
                app_client_id=app_client_id,
                app_client_key=app_client_key,
            )


def prompt_azure_app_client_id(directory_name, directory_id, app_client_id) -> str:
    print(
        f"""
Please enter the App registration key for the following Active Directory:
If you lost the key, you may generate a new Client Secret on your Azure App Registration.
    Active Directory Name: {directory_name}
    Active Directory Tenant ID: {directory_id}
    App registration Application ID: {app_client_id}
"""
    )
    return ask_input("App registration key:", mask_input=True)


def com_settings_legacy_to_candidate(
    legacy_com_settings: CommunicationSettings,
    legacy_user_id_email_map: Dict[str, str],
    c1_email_user_id_map: Dict[str, str],
) -> CommunicationSettings:
    legacy_conf = legacy_com_settings.configuration
    if legacy_com_settings.channel in ("email", "sms"):
        legacy_user_ids = legacy_conf["users"]
        c1_user_ids = []
        for legacy_user_id in legacy_user_ids:
            email = legacy_user_id_email_map.get(legacy_user_id)
            c1_user_id = c1_email_user_id_map.get(email)
            c1_user_ids.append(c1_user_id)
        c1_conf = {"users": c1_user_ids}
    else:
        c1_conf = legacy_conf

    return CommunicationSettings(
        channel=legacy_com_settings.channel,
        enabled=legacy_com_settings.enabled,
        filter=legacy_com_settings.filter,
        configuration=c1_conf,
    )


def copy_communication_channel_settings(
    legacy_svc: ConformityService,
    c1_svc: ConformityService,
    legacy_acct_id: str,
    c1_acct_id: str,
    legacy_users: List[User],
    c1_users: List[User],
    c1_org_id: str,
):
    legacy_user_id_email_map = {user.user_id: user.email for user in legacy_users}
    c1_email_user_id_map = {user.email: user.user_id for user in c1_users}

    legacy_com_settings = legacy_svc.get_communication_settings(acct_id=legacy_acct_id)
    candidate_com_settings: Set[CommunicationSettings] = set()
    for s in legacy_com_settings:
        legacy_conf = s.configuration
        if s.channel in ("email", "sms"):
            legacy_user_ids = legacy_conf["users"]
            c1_user_ids = []
            for legacy_user_id in legacy_user_ids:
                email = legacy_user_id_email_map.get(legacy_user_id)
                c1_user_id = c1_email_user_id_map.get(email)
                c1_user_ids.append(c1_user_id)
            c1_conf = {"users": c1_user_ids}
        else:
            c1_conf = legacy_conf

        candidate_com_settings.add(
            CommunicationSettings(
                channel=s.channel,
                enabled=s.enabled,
                filter=s.filter,
                configuration=c1_conf,
            )
        )

    c1_com_settings = set(c1_svc.get_communication_settings(acct_id=c1_acct_id))
    new_com_settings = candidate_com_settings.difference(c1_com_settings)
    if new_com_settings:
        c1_svc.create_communication_settings(
            com_settings=new_com_settings, acct_id=c1_acct_id, org_id=c1_org_id
        )


def migrate_account_configurations(
    legacy_svc: ConformityService,
    c1_svc: ConformityService,
    legacy_acct_id: str,
    c1_acct_id: str,
    legacy_users: List[User],
    c1_users: List[User],
    c1_org_id: str,
):

    legacy_acct_details = legacy_svc.get_account_details(acct_id=legacy_acct_id)
    # print(json.dumps(legacy_acct_details, indent=4))
    legacy_acct_attrib = legacy_acct_details["attributes"]

    print("  --> Updating account tags", end="", flush=True)
    c1_svc.update_account(
        acct_id=c1_acct_id,
        name=legacy_acct_attrib["name"],
        environment=legacy_acct_attrib["environment"],
        tags=legacy_acct_attrib["tags"],
    )
    print(" - Done")

    print("  --> Copying account bot settings", end="", flush=True)
    # bot_settings = legacy_svc.get_account_bot_settings(acct_id=legacy_acct_id)
    bot_settings = legacy_acct_attrib["settings"]["bot"]
    del bot_settings["lastModifiedFrom"]
    del bot_settings["lastModifiedBy"]
    resp = c1_svc.update_account_bot_settings(acct_id=c1_acct_id, settings=bot_settings)
    # print(resp)
    print(" - Done")

    print("  --> Copying account rules settings:", flush=True)
    copy_account_rules_settings(
        legacy_svc=legacy_svc,
        c1_svc=c1_svc,
        legacy_acct_id=legacy_acct_id,
        c1_acct_id=c1_acct_id,
        legacy_acct_details=legacy_acct_details,
        legacy_users=legacy_users,
    )
    # print(" - Done")

    print("  --> Copying communication channel settings", end="", flush=True)
    copy_communication_channel_settings(
        legacy_svc=legacy_svc,
        c1_svc=c1_svc,
        legacy_acct_id=legacy_acct_id,
        c1_acct_id=c1_acct_id,
        legacy_users=legacy_users,
        c1_users=c1_users,
        c1_org_id=c1_org_id,
    )
    print(" - Done")

    if has_suppressed_check(legacy_svc=legacy_svc, acct_id=legacy_acct_id):
        print("  --> Waiting for bot scan to finish ", end="", flush=True)
        wait_for_bot_scan_to_finish(c1_svc=c1_svc, acct_id=c1_acct_id)
        print(" - Done")

        print("  --> Copying suppressed checks")
        copy_suppressed_checks(
            legacy_svc=legacy_svc,
            c1_svc=c1_svc,
            legacy_acct_id=legacy_acct_id,
            c1_acct_id=c1_acct_id,
        )
    else:
        print("  --> No suppressed check found to migrate")


def copy_account_rules_settings(
    legacy_svc: ConformityService,
    c1_svc: ConformityService,
    legacy_acct_id: str,
    c1_acct_id: str,
    legacy_acct_details: dict,
    legacy_users: List[User],
):

    user_map = {user.user_id: user for user in legacy_users}
    legacy_acct_attrib = legacy_acct_details["attributes"]
    rule_ids = [r["id"] for r in legacy_acct_attrib["settings"].get("rules", [])]
    for rule_id in rule_ids:
        print(f"    --> Rule: {rule_id}", flush=True)
        rule = legacy_svc.get_account_rule_setting(
            acct_id=legacy_acct_id, rule_id=rule_id, with_notes=True
        )

        note_msg = create_new_note_from_history_of_notes(
            notes=rule.notes, user_map=user_map
        )

        c1_svc.update_account_rule_setting(
            acct_id=c1_acct_id,
            rule_id=rule_id,
            setting=rule.setting,
            note=note_msg,
        )


def truncate_txt_to_length(txt: str, length=-1, truncated_suffix="") -> str:
    if length == -1 or (0 <= len(txt) <= length):
        return txt

    return txt[: length - len(truncated_suffix)] + truncated_suffix


def get_most_recent_note_msg(notes: List[Note]) -> str:
    if not notes:
        return ""
    note = sorted(notes, key=lambda note: note.created_ts, reverse=True)[0]
    return note.note


def create_new_note_from_history_of_notes(
    notes: List[Note], user_map: Dict[str, User]
) -> str:
    note_msg = "[Copied settings via migration tool]"
    if not notes:
        return f"{note_msg} No history of notes found."

    note_frags = []
    sorted_notes = sorted(notes, key=lambda note: note.created_ts, reverse=True)
    for note in sorted_notes:
        user = user_map.get(note.created_by)
        user_name = f"{user.first_name} {user.last_name}" if user else ""
        ts = int(note.created_ts / 1000)
        dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(sep=" ")
        note_frag = f"On: {dt_str}\nBy: {user_name}\nNote: {note.note}"
        note_frags.append(note_frag)

    note_history = "\n\n".join(note_frags)

    note_msg = f"""{note_msg} History of notes:
-----------------------
{note_history}
-----------------------
"""

    return note_msg


def wait_for_bot_scan_to_finish(c1_svc: ConformityService, acct_id: str):
    while not c1_svc.is_bot_scan_done(acct_id=acct_id):
        print(".", end="", flush=True)
        time.sleep(APP_CONF["BOT_SCAN_CHECK_INTERVAL_IN_SECS"])
        continue


def has_suppressed_check(legacy_svc: ConformityService, acct_id: str) -> bool:
    checks = legacy_svc.get_suppressed_checks(acct_id=acct_id, limit=1)
    return len(list(checks)) > 0


def copy_suppressed_checks(
    legacy_svc: ConformityService,
    c1_svc: ConformityService,
    legacy_acct_id: str,
    c1_acct_id: str,
):
    legacy_checks = legacy_svc.get_suppressed_checks(acct_id=legacy_acct_id)
    for legacy_check in legacy_checks:
        print(
            f"    --> {legacy_check.rule_id}|{legacy_check.region}|{legacy_check.resource_name}|{legacy_check.resource}",
            flush=True,
        )
        filters = {
            "ruleIds": [legacy_check.rule_id],
            "regions": [legacy_check.region],
        }
        if legacy_check.resource:
            filters["resourceSearchMode"] = "text"
            filters["resource"] = legacy_check.resource
        c1_checks = list(c1_svc.get_checks(acct_id=c1_acct_id, filters=filters))
        c1_checks_map = {c: c for c in c1_checks}
        c1_check = c1_checks_map.get(legacy_check)
        if c1_check is None:
            show_instructions_for_missing_check(legacy_check)
            continue
        legacy_check_detail = legacy_svc.get_check_detail(
            check_id=legacy_check.check_id, with_notes=True
        )
        note_msg = get_most_recent_note_msg(legacy_check_detail.notes)
        if not note_msg:
            note_msg = "[Migration tool: No note found from the source Check]"
        note_msg = truncate_txt_to_length(
            txt=note_msg, length=200, truncated_suffix=".."
        )
        # print(f"Note: {note_msg}")
        c1_svc.suppress_check(
            check_id=c1_check.check_id,
            suppressed_until=legacy_check.suppressed_until,
            note=note_msg,
        )


def show_instructions_for_missing_check(check: Check):
    print(
        f"""
    Can't find the corresponding check in CloudOne. Please manually suppress the check below or try re-running this tool.
        RuleID: {check.rule_id}
        Region: {check.region}
        Resource: {check.resource}
        Message: {check.message}
"""
    )


def invite_missing_users(legacy_users: List[User], c1_users: List[User]):
    users_to_invite = set(legacy_users).difference(set(c1_users))
    invite_users(users_to_invite)


def invite_users(users_to_invite: Iterable[User]):
    if not users_to_invite:
        return

    print(
        """
Please invite the following users to your CloudOne Account.
If you are using them as recipients for your communication channel,
then it is important to add them now before we proceed with migration:
"""
    )
    for user in users_to_invite:
        print(
            f" --> {user.first_name} {user.last_name}; Email={user.email}, Role={user.role}"
        )

    ask_when_user_invite_done()


def ask_confirmation(msg: str, default=False) -> bool:
    questions = [
        {
            "type": "confirm",
            "message": msg,
            "name": "continue",
            "default": default,
        },
    ]
    answer = prompt(questions=questions)
    return answer["continue"]


def ask_choices(msg: str, choices: List[str], default=1):
    questions = [
        {
            "type": "list",
            "message": msg,
            "name": "choice",
            "choices": choices,
            "default": default,
        },
    ]
    answer = prompt(questions=questions)
    return answer["choice"]


def ask_when_user_invite_done():
    while True:
        choice = ask_choices(
            msg="Please choose 'Done' when you'are done adding the users to CloudOne.",
            choices=["Done", "Not yet"],
            default=1,
        )

        if choice == "Not yet":
            continue

        sure = ask_confirmation(f"You chose '{choice}'. Are you sure?", default=False)
        if sure:
            break


def ask_input(msg: str, mask_input=False) -> str:
    name = "input"
    questions = [
        {
            "type": "password" if mask_input else "input",
            "message": msg,
            "name": name,
            "default": "",
        },
    ]
    answer = prompt(questions=questions)
    return answer[name]


def pretty_print_com_settings(com_settings):
    for s in com_settings:
        print(s)


if __name__ == "__main__":
    import requests

    try:
        main()
    except requests.exceptions.HTTPError as err:
        resp: requests.Response = err.response
        print(resp.text)
        raise err
