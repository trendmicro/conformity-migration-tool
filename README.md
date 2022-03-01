# conformity-migration-tool
Migrates your visiblity information in cloudconformity.com to cloudone.trendmicro.com

## **⚠ WARNING: This tool will overwrite your Cloud One Conformity**

## Requirements
1. Python v3.7+
2. API Keys for both Legacy Conformity and CloudOne Conformity
   - **Note:** Both API Keys must have admin privileges

## How to use this tool

1) Create or choose an empty folder where you would like to install and run the tool.

2) Start a shell/terminal on the folder you just created or chosen.

3) Create a python3 virtual environment (minimum: python v3.7)
    ```
    python3 -m venv .venv
    ```

4) Activate the virtual environment
   ```
   source .venv/bin/activate
   ```

5) Install the tool from TestPyPI
    ```
    pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ conformity-migration-tool
    ```

6) Configure the tool
    ```
    conformity-migration configure

7) Run the migration
    ```
    conformity-migration run
    ```

## Migration support
### Cloud Types
- [X] AWS account
  - **Note:** To grant access to CloudOne Conformity, user has to manually edit the `ExternalID` parameter of CloudConformity stack of his/her AWS account.
- [X] Azure account
  - **Note:** User needs to specify App Registration Key so the tool can add the Active Directory to Conformity
- [ ] GCP account

### Organisation-Level Configurations
- [X] Users
  - **Note**: The tool will display other users that needs to be invited by the admin to CloudOne Conformity.
- [X] Groups
- [X] Communication channel settings
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
- [X] Checks
  - **Limitation:** The API only allows writing a single note to the check so the tool won't be able to preserve the history of notes. In addition to that, API only allows a maximum of 200 characters of note. The tool will only get the most recent note and truncate it to 200 characters before writing it.
- [X] Report Configs
