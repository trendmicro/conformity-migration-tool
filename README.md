# conformity-migration-tool
Migrates your visiblity information in cloudconformity.com to cloudone.trendmicro.com

## Requirements
1. Python v3.7+
2. API Keys for both Legacy Conformity and CloudOne Conformity
3. Both API Keys must have admin privileges

## How to use this tool

1) Download this tool's folder to any folder in your local machine.

2) Go to the folder where the tool is located.
   
3) Create a python virtual environment
    ```
    python -m venv .venv
    ```
4) Install the dependencies
    ```
    pip install -r requirements.txt
    ```
 
5) Run the tool
    ```
    python main.py
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
### Account-Level Configurations
- [X] Account tags
- [X] Conformity Bot settings
- [X] Account Rule settings
  - **API Limitation:** Notes cannot be copied to rules yet.
- [X] Communication channel settings
- [ ] Profiles
- [ ] Report Configs
- [X] Checks
  - **API Limitation:** Notes cannot be ccopied to checks yet.
