import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Set

import yaml
from PyInquirer import prompt

from conformity_migration.cloud_accounts import get_cloud_account_adder
from conformity_migration.conformity_api import ConformityAPI, ConformityException
from conformity_migration.models import (
    Account,
    AccountDetails,
    Check,
    CommunicationSettings,
    Group,
    Note,
    ReportConfig,
    User,
)

from .di import dependencies

script_dir = os.path.abspath(os.path.dirname(__file__))


def get_conf() -> Any:
    with open(os.path.join(script_dir, "config.yml"), mode="r") as fh:
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


def cloud_type_accts_map(accts: List[Account]) -> Dict[str, List[Account]]:
    accts_map: Dict[str, List[Account]] = dict()

    for acct in accts:
        cloud_type_accts = accts_map.setdefault(acct.cloud_type, [])
        cloud_type_accts.append(acct)

    return accts_map


def run_migration():
    api_conf_file = "api_config.yml"
    ensure_api_conf_ready(api_conf_file)
    conf = get_api_conf(api_conf_file)

    deps = dependencies(conf)

    legacy_api = deps.legacy_conformity_api()

    c1_api = deps.c1_conformity_api()

    update_organisation_profile(legacy_api, c1_api)

    add_managed_groups(legacy_api, c1_api)

    c1_accts = c1_api.list_accounts()
    legacy_accts = legacy_api.list_accounts()

    legacy_cloud_type_accts_map = cloud_type_accts_map(legacy_accts)
    c1_cloud_type_accts_map = cloud_type_accts_map(c1_accts)

    cloud_accts_to_migrate: Dict[str, Dict[str, str]] = dict()

    for cloud_type, legacy_accts in legacy_cloud_type_accts_map.items():
        acct_adder = get_cloud_account_adder(
            cloud_type=cloud_type, legacy_api=legacy_api, c1_api=c1_api
        )
        if acct_adder is None:
            print(f"Does not support {cloud_type.upper()} yet! Skipping it.")
            continue

        print(f"Adding {cloud_type.upper()} accounts to CloudOne Conformity:")
        c1_cloud_type_accounts = c1_cloud_type_accts_map.get(cloud_type, [])

        accts_to_migrate: Dict[str, str] = dict()
        cloud_accts_to_migrate[cloud_type] = accts_to_migrate
        for acct in legacy_accts:
            c1_acct_id: str
            exists, c1_acct_id = acct_adder.account_exists(
                c1_accts=c1_cloud_type_accounts, acct=acct
            )
            env_suffix = f" ({acct.environment})" if acct.environment else ""
            if exists:
                print(
                    f"Account {acct.name}{env_suffix} already exists in CloudOne Conformity!"
                )
                if not (
                    ask_confirmation(
                        "Do you want to migrate configurations for this account (will overwrite existing ones)?",
                        ask_if_sure=True,
                    )
                ):
                    continue
            else:
                print(f" --> Account: {acct.name}{env_suffix}")
                c1_acct_id = acct_adder.account_add(acct=acct)

            accts_to_migrate[acct.account_id] = c1_acct_id

    print("Retrieving Legacy Conformity Users", flush=True)
    legacy_users = legacy_api.get_all_users()

    print("Retrieving CloudOne Conformity Users", flush=True)
    c1_users = c1_api.get_all_users()

    invite_missing_users(legacy_users, c1_users)

    create_user_defined_groups(legacy_api, c1_api)

    copy_custom_profiles(legacy_api, c1_api)

    copy_organisation_report_configs(legacy_api, c1_api)

    migrate_all_groups_configs(legacy_api, c1_api)

    c1_org_id = c1_api.get_organisation_id()

    print("Copying communication channel settings (organisation-level)", flush=True)
    copy_communication_channel_settings(
        legacy_api=legacy_api,
        c1_api=c1_api,
        legacy_acct_id="",
        c1_acct_id="",
        legacy_users=legacy_users,
        c1_users=c1_users,
        c1_org_id=c1_org_id,
    )

    for _, acct_id_map in cloud_accts_to_migrate.items():
        for legacy_acct_id, c1_acct_id in acct_id_map.items():
            migrate_account_configurations(
                legacy_api=legacy_api,
                c1_api=c1_api,
                legacy_acct_id=legacy_acct_id,
                c1_acct_id=c1_acct_id,
                legacy_users=legacy_users,
                c1_users=c1_users,
                c1_org_id=c1_org_id,
            )
            print()


def migrate_all_groups_configs(legacy_api: ConformityAPI, c1_api: ConformityAPI):
    c1_group_id_map: Dict[Group, str] = {g: g.group_id for g in c1_api.list_groups()}

    for legacy_group in legacy_api.list_groups():
        print(
            f"Migrating group configurations for Group={legacy_group.name}, Tags={legacy_group.tags}",
            flush=True,
        )
        legacy_group_id = legacy_group.group_id
        c1_group_id = c1_group_id_map.get(legacy_group)
        if not c1_group_id:
            print(
                f"Can't find corresponding CloudOne group for: Group={legacy_group.name}, Tags={legacy_group.tags}. Cannot migrate it's configurations."
            )
            continue

        copy_group_report_configs(
            legacy_api=legacy_api,
            c1_api=c1_api,
            legacy_group_id=legacy_group_id,
            c1_group_id=c1_group_id,
        )


def update_organisation_profile(legacy_api: ConformityAPI, c1_api: ConformityAPI):
    print("Copying Organisation Profile", flush=True)
    legacy_org_profile = legacy_api.get_organisation_profile(include_rule_settings=True)
    c1_org_profile = c1_api.get_organisation_profile(include_rule_settings=True)

    if c1_org_profile.included_rules:
        overwrite = ask_confirmation(
            "CloudOne Organisation Profile has configured rules in it. Do you want to overwrite it?",
            ask_if_sure=True,
        )
        if not overwrite:
            return

    c1_api.update_organisation_profile(profile=legacy_org_profile)


def copy_custom_profiles(legacy_api: ConformityAPI, c1_api: ConformityAPI):
    print("Copying Custom Profiles", flush=True)
    legacy_profiles = legacy_api.get_custom_profiles()
    c1_profiles = c1_api.get_custom_profiles()

    legacy_profiles_set = set(legacy_profiles)
    c1_profiles_to_replace = [p for p in c1_profiles if p in legacy_profiles_set]
    if c1_profiles_to_replace:
        print("Found following custom profiles that will be replaced during migration:")
        for c1_profile in c1_profiles_to_replace:
            print(f"  - Profile: {c1_profile.name}")
        cont = ask_confirmation("Continue migrating custom profiles?", ask_if_sure=True)
        if not cont:
            return

    for profile in c1_profiles_to_replace:
        # print(f" --> Deleting CloudOne profile: {profile.name}")
        c1_api.delete_profile(profile_id=profile.profile_id)

    for profile in legacy_profiles:
        print(f"  --> Profile: {profile.name}", flush=True)
        profile_with_rules = legacy_api.get_profile(
            profile_id=profile.profile_id, include_rule_settings=True
        )
        c1_api.create_new_profile(profile=profile_with_rules)


def check_existing_c1_report_configs(
    c1_api: ConformityAPI,
    legacy_report_configs: List[ReportConfig],
    c1_report_configs: List[ReportConfig],
    rconf_type: str,
) -> bool:
    rconf_type = rconf_type.capitalize()

    legacy_rconf_set = set(legacy_report_configs)
    c1_rconf_to_replace = [r for r in c1_report_configs if r in legacy_rconf_set]
    if c1_rconf_to_replace:
        print(
            f"Found following {rconf_type} Report Configs that will be replaced during migration:"
        )
        for c1_rconf in c1_rconf_to_replace:
            print(f"  - Report Config: {c1_rconf.title}")
        cont = ask_confirmation(
            f"Continue migrating {rconf_type} Report Configs?", ask_if_sure=True
        )
        if not cont:
            return False

    for rconf in c1_rconf_to_replace:
        # print(f" --> Deleting CloudOne {rconf_type} Report Config: {rconf.title}")
        c1_api.delete_report_config(report_conf_id=rconf.report_config_id)

    return True


def copy_account_report_configs(
    legacy_api: ConformityAPI,
    c1_api: ConformityAPI,
    legacy_acct_id: str,
    c1_acct_id: str,
):
    rconf_type = "Account"
    print(f"  --> Copying {rconf_type} Report Configs", flush=True)
    legacy_report_configs = legacy_api.list_account_report_configs(
        acct_id=legacy_acct_id
    )
    c1_report_configs = c1_api.list_account_report_configs(acct_id=c1_acct_id)

    cont_migration = check_existing_c1_report_configs(
        c1_api=c1_api,
        legacy_report_configs=legacy_report_configs,
        c1_report_configs=c1_report_configs,
        rconf_type=rconf_type,
    )
    if not cont_migration:
        return

    for report_config in legacy_report_configs:
        print(f"    --> Report Config: {report_config.title}")
        c1_api.create_account_report_config(
            report_conf=report_config.configuration, acct_id=c1_acct_id
        )


def copy_group_report_configs(
    legacy_api: ConformityAPI,
    c1_api: ConformityAPI,
    legacy_group_id: str,
    c1_group_id: str,
):
    rconf_type = "Group"
    print(f" --> Copying {rconf_type} Report Configs", flush=True)
    legacy_report_configs = legacy_api.list_group_report_configs(
        group_id=legacy_group_id
    )
    c1_report_configs = c1_api.list_group_report_configs(group_id=c1_group_id)

    cont_migration = check_existing_c1_report_configs(
        c1_api=c1_api,
        legacy_report_configs=legacy_report_configs,
        c1_report_configs=c1_report_configs,
        rconf_type=rconf_type,
    )
    if not cont_migration:
        return

    for report_config in legacy_report_configs:
        print(f"    --> Report Config: {report_config.title}")
        c1_api.create_group_report_config(
            report_conf=report_config.configuration, group_id=c1_group_id
        )


def copy_organisation_report_configs(
    legacy_api: ConformityAPI,
    c1_api: ConformityAPI,
):
    rconf_type = "Organisation"
    print(f"Copying {rconf_type} Report Configs", flush=True)
    legacy_report_configs = legacy_api.list_organisation_report_configs()
    c1_report_configs = c1_api.list_organisation_report_configs()

    cont_migration = check_existing_c1_report_configs(
        c1_api=c1_api,
        legacy_report_configs=legacy_report_configs,
        c1_report_configs=c1_report_configs,
        rconf_type=rconf_type,
    )
    if not cont_migration:
        return

    for report_config in legacy_report_configs:
        print(f"  --> Report Config: {report_config.title}")
        c1_api.create_organisation_report_config(
            report_conf=report_config.configuration
        )


def create_user_defined_groups(legacy_api: ConformityAPI, c1_api: ConformityAPI):
    print("Creating groups")
    legacy_groups = legacy_api.list_groups(
        include_group_types=[Group.GROUP_TYPE_USER_DEFINED]
    )
    c1_groups = set(
        c1_api.list_groups(include_group_types=[Group.GROUP_TYPE_USER_DEFINED])
    )

    for group in legacy_groups:
        print(f" --> Group: {group.name}, Tags: {group.tags}", end="", flush=True)
        if group in c1_groups:
            print(" - Already exists! Skipping it.")
            continue
        c1_api.create_group(name=group.name, tags=group.tags)
        print(" - Done")

    if not legacy_groups:
        print(" --> No group found.")


def add_managed_groups(legacy_api: ConformityAPI, c1_api: ConformityAPI):
    legacy_managed_groups = legacy_api.list_groups(
        include_group_types=[Group.GROUP_TYPE_MANAGED_GROUP]
    )
    c1_managed_groups = c1_api.list_groups(
        include_group_types=[Group.GROUP_TYPE_MANAGED_GROUP]
    )
    c1_managed_groups_set = set(c1_managed_groups)

    for mg in legacy_managed_groups:
        if mg in c1_managed_groups_set:
            # print(f"Managed Group {mg.name} ({mg.cloud_type.upper()}) already exists!")
            continue
        if mg.cloud_type == "azure":
            azure_conf = mg.cloud_data["azure"]  # type: ignore
            directory_name = mg.name
            directory_id = azure_conf["directoryId"]
            app_client_id = azure_conf["applicationId"]
            app_client_key = prompt_azure_app_client_id(
                directory_name, directory_id, app_client_id
            )
            c1_api.create_azure_directory(
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


def _convert_com_settings_conf_from_legacy_to_c1(
    legacy_conf: Dict[str, Any],
    legacy_user_id_email_map: Dict[str, str],
    c1_email_user_id_map: Dict[str, str],
) -> Dict[str, Any]:
    legacy_user_ids = legacy_conf["users"]
    c1_user_ids = []
    for legacy_user_id in legacy_user_ids:
        email = legacy_user_id_email_map.get(legacy_user_id)
        if email is None:
            print(
                f"Cannot find email of Legacy Conformity user with an ID of: {legacy_user_id}. Excluding user from notification."
            )
            continue

        c1_user_id = c1_email_user_id_map.get(email)
        if c1_user_id is None:
            print(
                f"Cannot find corresponding user in CloudOne Conformity: {email}. Excluding user from notification."
            )
            continue

        c1_user_ids.append(c1_user_id)

    c1_conf = {"users": c1_user_ids}

    return c1_conf


def copy_communication_channel_settings(
    legacy_api: ConformityAPI,
    c1_api: ConformityAPI,
    legacy_acct_id: str,
    c1_acct_id: str,
    legacy_users: List[User],
    c1_users: List[User],
    c1_org_id: str,
):
    legacy_user_id_email_map = {user.user_id: user.email for user in legacy_users}
    c1_email_user_id_map = {user.email: user.user_id for user in c1_users}

    legacy_com_settings = legacy_api.get_communication_settings(acct_id=legacy_acct_id)
    candidate_com_settings: Set[CommunicationSettings] = set()
    for s in legacy_com_settings:
        legacy_conf = s.configuration
        if s.channel in ("email", "sms"):
            c1_conf = _convert_com_settings_conf_from_legacy_to_c1(
                legacy_conf, legacy_user_id_email_map, c1_email_user_id_map
            )
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

    c1_com_settings = set(c1_api.get_communication_settings(acct_id=c1_acct_id))
    new_com_settings = candidate_com_settings.difference(c1_com_settings)
    if new_com_settings:
        c1_api.create_communication_settings(
            com_settings=new_com_settings, acct_id=c1_acct_id, org_id=c1_org_id
        )


def migrate_account_configurations(
    legacy_api: ConformityAPI,
    c1_api: ConformityAPI,
    legacy_acct_id: str,
    c1_acct_id: str,
    legacy_users: List[User],
    c1_users: List[User],
    c1_org_id: str,
):

    legacy_acct_details = legacy_api.get_account_details(acct_id=legacy_acct_id)
    name = legacy_acct_details.name
    environment = legacy_acct_details.environment
    cloud_type = legacy_acct_details.cloud_type
    print(
        f"Migrating account configurations for: {name} ({environment}) [{cloud_type.upper()}]:"
    )

    print("  --> Updating account tags", flush=True)
    c1_api.update_account(
        acct_id=c1_acct_id,
        name=name,
        environment=environment,
        tags=legacy_acct_details.tags,
    )

    print("  --> Copying account bot settings", flush=True)
    # bot_settings = legacy_api.get_account_bot_settings(acct_id=legacy_acct_id)
    bot_settings = legacy_acct_details.bot_settings
    del bot_settings["lastModifiedFrom"]
    del bot_settings["lastModifiedBy"]
    c1_api.update_account_bot_settings(acct_id=c1_acct_id, settings=bot_settings)

    print("  --> Copying account rules settings:", flush=True)
    copy_account_rules_settings(
        legacy_api=legacy_api,
        c1_api=c1_api,
        legacy_acct_id=legacy_acct_id,
        c1_acct_id=c1_acct_id,
        legacy_acct_details=legacy_acct_details,
        legacy_users=legacy_users,
    )

    print("  --> Copying communication channel settings", flush=True)
    copy_communication_channel_settings(
        legacy_api=legacy_api,
        c1_api=c1_api,
        legacy_acct_id=legacy_acct_id,
        c1_acct_id=c1_acct_id,
        legacy_users=legacy_users,
        c1_users=c1_users,
        c1_org_id=c1_org_id,
    )

    copy_account_report_configs(
        legacy_api=legacy_api,
        c1_api=c1_api,
        legacy_acct_id=legacy_acct_id,
        c1_acct_id=c1_acct_id,
    )

    if has_suppressed_check(legacy_api=legacy_api, acct_id=legacy_acct_id):
        print("  --> Waiting for bot scan to finish ", end="", flush=True)
        wait_for_bot_scan_to_finish(c1_api=c1_api, acct_id=c1_acct_id)
        print(" - Done")

        print("  --> Copying suppressed checks")
        copy_suppressed_checks(
            legacy_api=legacy_api,
            c1_api=c1_api,
            legacy_acct_id=legacy_acct_id,
            c1_acct_id=c1_acct_id,
        )
    else:
        print("  --> No suppressed check found to migrate")


def copy_account_rules_settings(
    legacy_api: ConformityAPI,
    c1_api: ConformityAPI,
    legacy_acct_id: str,
    c1_acct_id: str,
    legacy_acct_details: AccountDetails,
    legacy_users: List[User],
):

    user_map = {user.user_id: user for user in legacy_users}
    for rule in legacy_acct_details.rules:
        rule_id = rule.rule_id
        print(
            f"    --> Rule: {rule_id} ({'enabled' if rule.enabled else 'disabled'})",
            flush=True,
        )
        rule_with_notes = legacy_api.get_account_rule_setting(
            acct_id=legacy_acct_id, rule_id=rule_id, with_notes=True
        )

        note_msg = create_new_note_from_history_of_notes(
            notes=rule_with_notes.notes, user_map=user_map
        )

        c1_api.update_account_rule_setting(
            acct_id=c1_acct_id,
            rule_id=rule_id,
            setting=rule_with_notes.setting,
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


def wait_for_bot_scan_to_finish(c1_api: ConformityAPI, acct_id: str):
    while not c1_api.is_bot_scan_done(acct_id=acct_id):
        print(".", end="", flush=True)
        time.sleep(APP_CONF["BOT_SCAN_CHECK_INTERVAL_IN_SECS"])
        continue


def has_suppressed_check(legacy_api: ConformityAPI, acct_id: str) -> bool:
    checks = legacy_api.get_suppressed_checks(acct_id=acct_id, limit=1)
    return len(list(checks)) > 0


def copy_suppressed_checks(
    legacy_api: ConformityAPI,
    c1_api: ConformityAPI,
    legacy_acct_id: str,
    c1_acct_id: str,
):
    legacy_checks = legacy_api.get_suppressed_checks(acct_id=legacy_acct_id)
    for legacy_check in legacy_checks:
        print(
            f"    --> {legacy_check.rule_id}|{legacy_check.region}|{legacy_check.resource_name}|{legacy_check.resource}",
            flush=True,
        )
        filters: Dict[str, Any] = {
            "ruleIds": [legacy_check.rule_id],
            "regions": [legacy_check.region],
        }
        if legacy_check.resource:
            filters["resourceSearchMode"] = "text"
            filters["resource"] = legacy_check.resource
        c1_checks = list(c1_api.get_checks(acct_id=c1_acct_id, filters=filters))
        c1_checks_map = {c: c for c in c1_checks}
        c1_check = c1_checks_map.get(legacy_check)
        if c1_check is None:
            show_instructions_for_missing_check(legacy_check)
            continue
        legacy_check_detail = legacy_api.get_check_detail(
            check_id=legacy_check.check_id, with_notes=True
        )
        note_msg = get_most_recent_note_msg(legacy_check_detail.notes)
        if not note_msg:
            note_msg = "[Migration tool: No note found from the source Check]"
        note_msg = truncate_txt_to_length(
            txt=note_msg, length=200, truncated_suffix=".."
        )
        # print(f"Note: {note_msg}")
        c1_api.suppress_check(
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


def ask_confirmation(msg: str, default=False, ask_if_sure=False) -> bool:
    questions = [
        {
            "type": "confirm",
            "message": msg,
            "name": "continue",
            "default": default,
        },
    ]
    while True:
        answer = prompt(questions=questions)
        cont = answer["continue"]
        if not ask_if_sure or not cont:
            return cont

        sure = ask_confirmation(
            f"You chose {'Yes' if cont else 'No'}. Are you sure?", default=False
        )
        if sure:
            return cont


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


def ask_when_user_invite_done() -> None:
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


def main():
    try:
        run_migration()
    except ConformityException as e:
        print(e)
        print(e.details)
        # raise e


if __name__ == "__main__":
    main()
