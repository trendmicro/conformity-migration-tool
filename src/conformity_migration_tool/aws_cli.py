import csv
import json
import multiprocessing as mp
import time
from dataclasses import dataclass
from typing import Iterable, Tuple

import boto3
import click
from mypy_boto3_cloudformation import CloudFormationClient
from mypy_boto3_cloudformation.type_defs import (
    DescribeStacksOutputTypeDef,
    ParameterTypeDef,
    UpdateStackOutputTypeDef,
)

from .cli import include_exclude_accts, read_accts_file
from .di import c1_conformity_api, legacy_conformity_api


@dataclass
class LegacyConformityAWSAccountInfo:
    account_name: str
    aws_account_number: str
    old_external_id: str


def get_legacy_conformity_aws_accounts_info(
    include_accounts_file: str, exclude_accounts_file: str
) -> Iterable[LegacyConformityAWSAccountInfo]:

    include_accounts = (
        read_accts_file(accounts_file=include_accounts_file)
        if include_accounts_file
        else None
    )
    exclude_accounts = (
        read_accts_file(accounts_file=exclude_accounts_file)
        if exclude_accounts_file
        else None
    )

    legacy_api = legacy_conformity_api()
    old_external_id = legacy_api.get_organisation_external_id()
    accts = [acct for acct in legacy_api.list_accounts() if acct.cloud_type == "aws"]
    accts = include_exclude_accts(
        legacy_accts=accts,
        include_accts=include_accounts,
        exclude_accts=exclude_accounts,
    )
    for acct in accts:
        aws_acct_id = acct.attributes.get("awsaccount-id")
        if not aws_acct_id:
            print(f"Skipping account {acct.name}. It doesn't have awsaccount-id")
            continue
        yield LegacyConformityAWSAccountInfo(
            account_name=acct.name,
            aws_account_number=aws_acct_id,
            old_external_id=old_external_id,
        )


@click.group()
@click.pass_context
def cli(ctx):
    ctx.ensure_object(dict)
    # ctx.obj["region"] = region
    # ctx.obj["profile"] = profile


@cli.command(
    "generate-csv",
    help="Creates a csv file containing AWS accounts to be used for 'update-stack --csv-file' command option.",
)
@click.argument("csv-file")
@click.option(
    "--include-accounts-file",
    required=False,
    type=str,
    help="CSV file containing accounts that will be the only ones included. Each row should consists of 2 fields: first is the account name and second is the environment as they appear on Conformity Dashboard. An empty file means the tool won't include any account.",
)
@click.option(
    "--exclude-accounts-file",
    required=False,
    type=str,
    help="CSV file containing accounts that will be excluded. Each row should consists of 2 fields: first is the account name and second is the environment as they appear on Conformity Dashboard.",
)
def generate_csv(csv_file: str, include_accounts_file: str, exclude_accounts_file: str):
    print(f"Generating CSV: {csv_file}")
    with open(csv_file, newline="", mode="w") as fh:
        csvw = csv.DictWriter(
            fh,
            fieldnames=[
                "Account Name",
                "AWS Account Number",
                "Old ExternalID",
                "Conformity Stack Name",
                "Conformity Stack Region",
                "AWS_PROFILE",
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
                "Cross-Account Role Name",
            ],
            dialect="excel",
        )
        csvw.writeheader()

        accts = get_legacy_conformity_aws_accounts_info(
            include_accounts_file=include_accounts_file,
            exclude_accounts_file=exclude_accounts_file,
        )
        for acct in accts:
            csvw.writerow(
                {
                    "Account Name": acct.account_name,
                    "AWS Account Number": acct.aws_account_number,
                    "Old ExternalID": acct.old_external_id,
                    "Conformity Stack Name": "CloudConformity",
                    "Conformity Stack Region": "us-east-1",
                    "AWS_PROFILE": "",
                    "AWS_ACCESS_KEY_ID": "",
                    "AWS_SECRET_ACCESS_KEY": "",
                    "AWS_SESSION_TOKEN": "",
                    "Cross-Account Role Name": "",
                }
            )
    print("Done!")
    print(
        """
    You may now open and edit the csv especially the credentials column(s).
    You can either edit AWS_PROFILE or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN
    If you specify both, then it will ignore AWS_PROFILE.
    AWS_SESSION_TOKEN is optional - you will need this when the credentials are temporary ones.

    The values in the columns 'Conformity Stack Name' and 'Conformity Stack Region' are the default ones.
    You may edit them as necessary.
"""
    )


@cli.command("update-stack", help="Updates ExternalID of Cloud Conformity Stack")
@click.option(
    "--stack-name",
    default="CloudConformity",
    show_default=True,
    required=False,
    help="Name of the Cloud Conformity Stack",
)
@click.option(
    "--external-id",
    type=str,
    required=False,
    help="New value for the Stack paramater ExternalID. If not specified, it will use the ExternalId from Cloud One Conformity.",
)
@click.option(
    "--csv-file",
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True
    ),
    required=False,
    help="An optional CSV file containing AWS accounts' credentials and stack information. Non-empty field values in the CSV file will override whatever values entered in the CLI options.",
)
@click.option(
    "--region",
    type=str,
    envvar="AWS_DEFAULT_REGION",
    show_envvar=True,
    required=False,
    show_default=True,
    default="us-east-1",
    help="Region where Cloud Conformity Stack is deployed",
)
@click.option(
    "--profile",
    type=str,
    envvar="AWS_PROFILE",
    show_envvar=True,
    required=False,
    default=None,
    help="AWS credentials/config profile to use",
)
@click.option(
    "--access-key",
    type=str,
    envvar="AWS_ACCESS_KEY_ID",
    show_envvar=True,
    required=False,
    default=None,
    help="AWS Access Key",
)
@click.option(
    "--secret-key",
    type=str,
    envvar="AWS_SECRET_ACCESS_KEY",
    show_envvar=True,
    required=False,
    default=None,
    help="AWS Secret Key",
)
@click.option(
    "--session-token",
    type=str,
    envvar="AWS_SESSION_TOKEN",
    show_envvar=True,
    required=False,
    default=None,
    help="AWS Session Token",
)
@click.option(
    "--cross-account-role-name",
    type=str,
    required=False,
    default=None,
    help="Cross-Account Role name (e.g. OrganizationAccountAccessRole). The role should at least have the permissions necessary to update the Conformity stack.",
)
@click.option(
    "--include-accounts-file",
    required=False,
    type=str,
    help="CSV file containing accounts that will be the only ones included. Each row should consists of 2 fields: first is the account name and second is the environment as they appear on Conformity Dashboard. An empty file means the tool won't include any account.",
)
@click.option(
    "--exclude-accounts-file",
    required=False,
    type=str,
    help="CSV file containing accounts that will be excluded. Each row should consists of 2 fields: first is the account name and second is the environment as they appear on Conformity Dashboard.",
)
@click.pass_context
def update_stack(
    ctx,
    stack_name: str,
    external_id: str,
    csv_file: str,
    region: str,
    profile: str,
    access_key: str,
    secret_key: str,
    session_token: str,
    cross_account_role_name: str,
    include_accounts_file: str,
    exclude_accounts_file: str,
):
    # region = ctx.obj["region"]
    # profile = ctx.obj["profile"]
    if not external_id:
        print("Retrieving ExternalId from Cloud One Conformity")
        external_id = c1_conformity_api().get_organisation_external_id()
        print(f"ExternalId: {external_id}")

    accts: Iterable[AccountStackInfo]
    if csv_file:
        accts = read_csv_file(csv_file=csv_file)
        accts = _fill_acct_with_defaults(
            accts=accts,
            default_stack_name=stack_name,
            default_profile=profile,
            default_region=region,
            default_access_key=access_key,
            default_secret_key=secret_key,
            default_session_token=session_token,
            default_cross_account_role_name=cross_account_role_name,
        )
    else:
        accts = (
            AccountStackInfo(
                account_name=acct.account_name,
                aws_account_number=acct.aws_account_number,
                old_external_id=acct.old_external_id,
                stack_name=stack_name,
                stack_region=region,
                aws_profile=profile,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                aws_session_token=session_token,
                cross_account_role_name=cross_account_role_name,
            )
            for acct in get_legacy_conformity_aws_accounts_info(
                include_accounts_file=include_accounts_file,
                exclude_accounts_file=exclude_accounts_file,
            )
        )

    accts = list(accts)
    proc_count = min(len(accts), 10)
    with mp.Pool(processes=proc_count) as pool:
        params = _update_stack_params(accts=accts, external_id=external_id)
        pool.map(_update_stack_worker, params)


@dataclass
class AccountStackInfo:
    account_name: str
    aws_account_number: str
    old_external_id: str
    stack_name: str
    stack_region: str
    aws_profile: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_session_token: str
    cross_account_role_name: str


def _update_stack_params(
    accts: Iterable[AccountStackInfo],
    external_id: str,
) -> Iterable[Tuple[AccountStackInfo, str]]:
    for acct in accts:
        yield (acct, external_id)


def _update_stack_worker(params: Tuple[AccountStackInfo, str]):
    # print(f"[Process: {os.getpid()}] Params: {params}")
    acct, external_id = params
    try:
        _update_stack(acct=acct, external_id=external_id)
    except Exception as e:
        print(f"Failed to update stack for {acct.account_name}. Error: {e}")


def _fill_acct_with_defaults(
    accts: Iterable[AccountStackInfo],
    default_stack_name: str,
    default_profile: str,
    default_region: str,
    default_access_key: str,
    default_secret_key: str,
    default_session_token: str,
    default_cross_account_role_name: str,
) -> Iterable[AccountStackInfo]:
    for acct in accts:
        stack_name = acct.stack_name if acct.stack_name else default_stack_name
        stack_region = acct.stack_region if acct.stack_region else default_region
        aws_profile = acct.aws_profile if acct.aws_profile else default_profile
        access_key = (
            acct.aws_access_key_id if acct.aws_access_key_id else default_access_key
        )
        secret_key = (
            acct.aws_secret_access_key
            if acct.aws_secret_access_key
            else default_secret_key
        )
        session_token = (
            acct.aws_session_token if acct.aws_session_token else default_session_token
        )
        cross_account_role_name = (
            acct.cross_account_role_name
            if acct.cross_account_role_name
            else default_cross_account_role_name
        )
        yield AccountStackInfo(
            account_name=acct.account_name,
            aws_account_number=acct.aws_account_number,
            old_external_id=acct.old_external_id,
            stack_name=stack_name,
            stack_region=stack_region,
            aws_profile=aws_profile,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            cross_account_role_name=cross_account_role_name,
        )


def read_csv_file(csv_file: str) -> Iterable[AccountStackInfo]:
    with open(csv_file, newline="", mode="r") as fh:
        csvr = csv.DictReader(fh, dialect="excel")
        for rec in csvr:
            acct = AccountStackInfo(
                account_name=rec["Account Name"],
                aws_account_number=rec["AWS Account Number"].strip(),
                old_external_id=rec["Old ExternalID"].strip(),
                stack_name=rec["Conformity Stack Name"].strip(),
                stack_region=rec["Conformity Stack Region"].strip(),
                aws_profile=rec["AWS_PROFILE"].strip(),
                aws_access_key_id=rec["AWS_ACCESS_KEY_ID"].strip(),
                aws_secret_access_key=rec["AWS_SECRET_ACCESS_KEY"].strip(),
                aws_session_token=rec["AWS_SESSION_TOKEN"].strip(),
                cross_account_role_name=rec.get("Cross-Account Role Name", "").strip(),
            )
            yield acct


def _get_sess_acct_number(sess: boto3.Session) -> str:
    sts = sess.client("sts")
    return sts.get_caller_identity()["Account"]


def _get_cross_acct_sess(sess: boto3.Session, aws_acct_num: str, role_name: str):
    sess_acct_num = _get_sess_acct_number(sess)
    if sess_acct_num == aws_acct_num:
        return sess

    sts = sess.client("sts")
    resp = sts.assume_role(
        RoleArn=f"arn:aws:iam::{aws_acct_num}:role/{role_name}",
        RoleSessionName=f"cross_acct_sess_{sess_acct_num}",
        DurationSeconds=3600,
    )

    creds = resp["Credentials"]

    return boto3.Session(
        region_name=sess.region_name,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def _update_stack(acct: AccountStackInfo, external_id: str):

    if acct.aws_access_key_id and acct.aws_secret_access_key:
        session_token = acct.aws_session_token if acct.aws_session_token else None
        sess = boto3.Session(
            region_name=acct.stack_region,
            aws_access_key_id=acct.aws_access_key_id,
            aws_secret_access_key=acct.aws_secret_access_key,
            aws_session_token=session_token,
        )
    else:
        sess = boto3.Session(
            profile_name=acct.aws_profile, region_name=acct.stack_region
        )

    if acct.cross_account_role_name:
        sess = _get_cross_acct_sess(
            sess=sess,
            aws_acct_num=acct.aws_account_number,
            role_name=acct.cross_account_role_name,
        )

    sess_acct_num = _get_sess_acct_number(sess)
    if sess_acct_num != acct.aws_account_number:
        print(
            f"AWS credentials not for this account AWS={acct.aws_account_number} ({acct.account_name})"
        )
        return

    cfn = sess.client("cloudformation", region_name=acct.stack_region)
    old_external_id = get_stack_external_id(cfn=cfn, stack_name=acct.stack_name)

    acct_info = (
        f" [AWS={acct.aws_account_number} ({acct.account_name})]"
        if acct.aws_account_number
        else ""
    )

    if external_id == old_external_id:
        print(
            f"[Update stack skipped]{acct_info} [{old_external_id} --> {external_id}]",
            flush=True,
        )
        return

    print(
        f"[Update stack started]{acct_info} [{old_external_id} --> {external_id}]",
        flush=True,
    )

    params = [
        ParameterTypeDef(
            ParameterKey="AccountId",
            UsePreviousValue=True,
        ),
        ParameterTypeDef(
            ParameterKey="ExternalId",
            ParameterValue=external_id,
        ),
    ]
    res: UpdateStackOutputTypeDef = cfn.update_stack(
        StackName=acct.stack_name,
        UsePreviousTemplate=True,
        Parameters=params,
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )
    stack_id = res["StackId"]

    (is_successful, reason) = wait_for_update_stack(
        cfn=cfn, stack_id=stack_id, check_interval_in_secs=5
    )
    if is_successful:
        print(
            f"[Update stack success]{acct_info} [{old_external_id} --> {external_id}]"
        )
    else:
        print(
            f"[Update stack failed! Reason={reason}]{acct_info} [{old_external_id} --> {external_id}]"
        )


def get_stack_external_id(cfn: CloudFormationClient, stack_name: str) -> str:
    res: DescribeStacksOutputTypeDef = cfn.describe_stacks(StackName=stack_name)
    stack = res["Stacks"][0]
    params = stack["Parameters"]
    for param in params:
        if param["ParameterKey"] == "ExternalId":
            return param["ParameterValue"]
    return ""


def wait_for_update_stack(
    cfn: CloudFormationClient, stack_id: str, check_interval_in_secs=5
) -> Tuple[bool, str]:
    is_success = False
    reason = ""
    while True:
        res: DescribeStacksOutputTypeDef = cfn.describe_stacks(StackName=stack_id)
        stack = res["Stacks"][0]
        status = stack["StackStatus"]
        if status == "UPDATE_IN_PROGRESS":
            time.sleep(check_interval_in_secs)
            continue
        reason = stack.get("StackStatusReason", "")
        reason = f"({status}) {reason}"
        if status in {"UPDATE_COMPLETE", "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS"}:
            is_success = True
            break
        else:
            pretty_print(res)
            is_success = False
            break
    return is_success, reason


def pretty_print(obj):
    print(json.dumps(obj, indent=4, default=str))


if __name__ == "__main__":
    cli()
