from abc import ABCMeta, abstractmethod
from typing import List, Union, Tuple
from PyInquirer import prompt
from models import Account
from service import ConformityService


class CloudAccountAdder(metaclass=ABCMeta):
    @abstractmethod
    def account_exists(
        self, c1_accts: List[Account], acct: Account
    ) -> Tuple[bool, str]:
        pass

    @abstractmethod
    def account_add(self, acct: Account) -> str:
        pass


class AWSCloudAccountAdder(CloudAccountAdder):
    def __init__(
        self, legacy_svc: ConformityService, c1_svc: ConformityService
    ) -> None:
        self.legacy_svc = legacy_svc
        self.c1_svc = c1_svc

    def _account_uniq_attrib(self, acct: Account) -> str:
        return acct.attributes["awsaccount-id"]

    def account_exists(
        self, c1_accts: List[Account], acct: Account
    ) -> Tuple[bool, str]:
        for c1_acct in c1_accts:
            if c1_acct.cloud_type != "aws":
                continue
            if self._account_uniq_attrib(acct) == self._account_uniq_attrib(c1_acct):
                return True, c1_acct.account_id
        return False, ""

    def account_add(self, acct: Account) -> str:
        name = acct.name
        environment = acct.environment
        legacy_acct_id = acct.account_id

        c1_external_id = self.c1_svc.get_organisation_external_id()

        aws_acct_num = acct.attributes["awsaccount-id"]

        access_conf = self.legacy_svc.get_account_access_configuration(
            acct_id=legacy_acct_id
        )
        role_arn = access_conf["roleArn"]
        old_external_id = access_conf["externalId"]

        self.show_update_stack_external_id_instructions(
            aws_acct_num=aws_acct_num,
            old_external_id=old_external_id,
            new_external_id=c1_external_id,
        )
        prompt_continue()

        res = self.c1_svc.add_aws_account(
            name=name,
            environment=environment,
            role_arn=role_arn,
            external_id=c1_external_id,
        )

        return res["id"]

    @staticmethod
    def show_update_stack_external_id_instructions(
        aws_acct_num, old_external_id, new_external_id
    ):
        print(
            f"""
Please do the following steps to grant CloudOne Conformity access to your AWS account:
    1. Sign in to AWS console for AWS Account {aws_acct_num}
    2. Go to CloudFormation and find stack name CloudConformity
    3. Click Update button to edit stack.
    4. Under Prepare Template, choose: Use current template, and click Next
    5. Under Parameters, change value of ExternalID to the new one below:
        Old Value: {old_external_id}
        New Value: {new_external_id}
"""
        )


class AzureCloudAccountAdder(CloudAccountAdder):
    def __init__(
        self, legacy_svc: ConformityService, c1_svc: ConformityService
    ) -> None:
        self.legacy_svc = legacy_svc
        self.c1_svc = c1_svc

    def _account_uniq_attrib(self, acct: Account) -> str:
        return acct.attributes["cloud-data"]["azure"]["subscriptionId"]

    def account_exists(
        self, c1_accts: List[Account], acct: Account
    ) -> Tuple[bool, str]:
        for c1_acct in c1_accts:
            if c1_acct.cloud_type != "azure":
                continue
            if self._account_uniq_attrib(acct) == self._account_uniq_attrib(c1_acct):
                return True, c1_acct.account_id
        return False, ""

    def account_add(self, acct: Account) -> str:
        name = acct.name
        environment = acct.environment

        azure_sub_id = acct.attributes["cloud-data"]["azure"]["subscriptionId"]
        group_id = acct.managed_group_id

        res = self.legacy_svc.get_group_details(group_id=group_id)
        gattrib = res["attributes"]
        azure_data = gattrib["cloud-data"]["azure"]
        active_directory_id = azure_data["directoryId"]

        res = self.c1_svc.add_azure_subscription(
            name=name,
            environment=environment,
            subscription_id=azure_sub_id,
            active_directory_id=active_directory_id,
        )
        # print(res)
        return res["id"]


def prompt_continue():
    questions = [
        {
            "type": "confirm",
            "message": "Do you want to continue?",
            "name": "continue",
            "default": False,
        },
    ]
    while (prompt(questions=questions))["continue"] is False:
        pass


def get_cloud_account_adder(
    cloud_type: str, legacy_svc: ConformityService, c1_svc: ConformityService
) -> Union[CloudAccountAdder, None]:
    if cloud_type == "aws":
        return AWSCloudAccountAdder(legacy_svc, c1_svc)
    if cloud_type == "azure":
        return AzureCloudAccountAdder(legacy_svc, c1_svc)
    return None
