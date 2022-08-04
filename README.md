# conformity-migration-tool
Migrates your visiblity information in cloudconformity.com to cloudone.trendmicro.com

![GitHub release (latest by date)](https://img.shields.io/github/v/release/atiradocc/conformity-migration-tool?color=red&label=Last%20Release&logo=trend-micro&logoColor=red)
![GitHub issues](https://img.shields.io/github/issues/atiradocc/conformity-migration-tool?label=Issues)
![GitHub pull requests](https://img.shields.io/github/issues-pr/atiradocc/conformity-migration-tool?label=Pull%20Requests)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/conformity-migration-tool?logo=python&label=Python%20Version%20Support)

## **⚠ WARNING: This tool will overwrite your Cloud One Conformity**

## Requirements
1. Python versions 3.7, 3.8, or 3.9
2. Both accounts must have a valid license (Not expired)
3. API Keys for both Legacy Conformity and CloudOne Conformity
   - **Note:** Both API Keys must have admin privileges

## How to use this tool

1) Create or choose an empty folder where you would like to install and run the tool.

2) Start a shell/terminal on the folder you just created or chosen.

3) Create a python3 virtual environment
    ```
    python3 -m venv .venv
    ```

4) Activate the virtual environment
   ```
   source .venv/bin/activate
   ```

5) Install the tool
    ```
    pip install conformity-migration-tool
    ```

6) Configure the tool
    ```
    conformity-migration configure
    ```
    **Note:** Once you finish the tool configuration once, a file called **user-config.yml** with the settings you configured will be generated in the same folder, in case you need to re-run the tool.

    For Cloud One Conformity API endpoints, you can use the format: ```https://conformity.{region}.cloudone.trendmicro.com/api/```, here you can find more information about [Cloud One Regions](https://cloudone.trendmicro.com/docs/identity-and-account-management/c1-regions/).

7) If you have AWS accounts to migrate, you can either manually update your Conformity Stack's `ExternalID` parameter during migration on the next step or you can run this command `conformity-migration-aws` first before migration.

   Run this command to see all the available options:
   ```
   conformity-migration-aws update-stack --help
   ```
   Example command:
   ```
   conformity-migration-aws update-stack --access-key <aws-access-key-here> --secret-key <aws-secret-key-here>
   ```
   Using AWS_PROFILE:
   ```
   conformity-migration-aws update-stack --profile <aws-profile-here>
   ```
   
   For multiple accounts which you have cross-account role to use, you can add the option `--cross-account-role-name`.

   For multiple accounts which you don't have cross-account role to use or for a more granular control on each accounts' credentials, do the following steps:

   a. Generate a CSV file containing all your AWS accounts and default stack information from Legacy conformity:
   ```
   conformity-migration-aws generate-csv <CSV_FILE>
   ```
   b. Update the CSV file with your AWS credentials or stack information when necessary.
   
   c. Run the update-stack command with CLI option "--csv-file". You can use other options together with this option. Whatever non-empty values you put in the CSV file will override the values used in the CLI options.
   ```
   conformity-migration-aws update-stack --csv-file <CSV_FILE>
   ```


8)  Run the migration
    ```
    conformity-migration run
    ```
    If you already updated your AWS accounts' `ExternalId` beforehand as in step 8, then you can add this
    option below so it will stop prompting you to update your ExternalId manually:
    ```
    conformity-migration run --skip-aws-prompt
    ```

9)  In case you need to only migrate one or a few accounts, you can create a CSV file containing accounts that will be the only ones included in migration. In the CSV file, each row should consists of 2 fields: first is the account name and second is the environment as they appear on Conformity Dashboard. An empty file means the tool won't include any account in the migration. Here's an example:

    ```
    my-aws-account-name,production
    my-azure-subscription-name,development
    ```

    To excute the migration simply execute:

    ```
    conformity-migration run --include-accounts-file file.csv
    ```

    The same concept apply to exclude accounts from the migration:

    ```
    conformity-migration run --exclude-accounts-file file.csv
    ```

## Migration support
### Cloud Types
- [X] AWS account
  - **Note:** To grant access to CloudOne Conformity, user has to update the `ExternalId` parameter of CloudConformity stack of his/her AWS account. This can be done either manually or using the CLI `conformity-migration-aws` which is part of the conformity-migration-tool package.

- [X] Azure account
  - **Note:** User needs to specify App Registration Key so the tool can add the Active Directory to Conformity
- [ ] GCP account

### Organisation-Level Configurations
- [X] Users
  - **Note**: The tool will display other users that needs to be invited by the admin to CloudOne Conformity.
- [X] Groups
- [X] Communication channel settings
  - **Note**: The tool cannot migrate Jira, ServiceNow or ZenDesk Communication Settings, for these, it has to be migrated manually.
- [X] Profiles
- [X] Report Configs

### Group-Level Configurations
- [X] Report Configs

### Account-Level Configurations
- [X] Account tags
- [X] Conformity Bot settings
- [X] Account Rule settings
  - **Limitation:** The API only allows writing a single note to the rule so the tool won't be able to preserve the history of notes. The tool will instead combine history of notes into a single note before writing it.
- [X] Communication channel settings
  - **Note**: The tool cannot migrate Jira, ServiceNow or ZenDesk communication settings, for these, it has to be migrated manually.
- [X] Checks
  - **Limitation:** The API only allows writing a single note to the check so the tool won't be able to preserve the history of notes. In addition to that, API only allows a maximum of 200 characters of note. The tool will only get the most recent note and truncate it to 200 characters before writing it.
- [X] Report Configs

## Troubleshooting
If you encounter any errors in the execution, please [Create a New Issue](https://github.com/atiradocc/conformity-migration-tool/issues/new) describing the steps that you went through, the results expected, and the actual results that you got.

### Support logs
The tool automatically generates log files when an error is found. In the same folder that you ran the tool, you will find these files:

- ```conformity-migration-error.log``` -> Specific logs about errors encountered from the last runtime.

- ```conformity-migration.log``` -> General log information about the tool the last runtime.

**Note:** Please don't share these files publicly, they might contain sensitive information about your environment. In case you need to share for support purposes, mask sensitive information before sending it.


## Contributing

If you encounter a bug, think of a useful feature, or find something confusing
in the docs, please
[Create a New Issue](https://github.com/atiradocc/conformity-migration-tool/issues/new)!

We :heart: pull requests. If you'd like to fix a bug, contribute to a feature or
just correct a typo, please feel free to do so.

If you're thinking of adding a new feature, consider opening an issue first to
discuss it to ensure it aligns with the direction of the project (and potentially
save yourself some time!).