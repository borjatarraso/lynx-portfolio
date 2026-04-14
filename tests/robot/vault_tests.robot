*** Settings ***
Library     Process
Library     OperatingSystem
Library     String
Resource    resources/common.robot

Test Setup       Setup Temp Database
Test Teardown    Cleanup Vault Files


*** Keywords ***
# ---------------------------------------------------------------------------
# Vault-specific BDD keywords
# ---------------------------------------------------------------------------
Cleanup Vault Files
    Remove File    ${TEMP_DB}
    Remove File    ${TEMP_DB}.enc
    Remove File    ${TEMP_DB}.salt
    Remove File    ${TEMP_DB}.bak
    Remove File    ${TEMP_DB}.enc.bak
    Remove File    ${TEMP_DB}.salt.bak
    Remove File    ${TEMP_DB}-shm
    Remove File    ${TEMP_DB}-wal
    Remove Environment Variable    LYNX_DB_PATH

the user encrypts the database with password "${pwd}"
    # Robot's Run Process stdin= expects a file path, so write password to a file
    ${stdin_file}=    Set Variable    ${TEMP_DB}_stdin.txt
    Create File    ${stdin_file}    ${pwd}\n${pwd}\n${pwd}\n
    ${result}=    Run Process    ${PYTHON}    ${LYNX_SCRIPT}    --encrypt
    ...    env:LYNX_DB_PATH=${TEMP_DB}    stdin=${stdin_file}
    Remove File    ${stdin_file}
    Set Test Variable    ${LAST_RESULT}    ${result}

the user decrypts and lists with password "${pwd}"
    ${result}=    Run Process    ${PYTHON}    ${LYNX_SCRIPT}    --decrypt    ${pwd}    -c    list
    ...    env:LYNX_DB_PATH=${TEMP_DB}
    Set Test Variable    ${LAST_RESULT}    ${result}

the user disables encryption with password "${pwd}"
    ${stdin_file}=    Set Variable    ${TEMP_DB}_stdin.txt
    Create File    ${stdin_file}    ${pwd}\n
    ${result}=    Run Process    ${PYTHON}    ${LYNX_SCRIPT}    --disable-encryption
    ...    env:LYNX_DB_PATH=${TEMP_DB}    stdin=${stdin_file}
    Remove File    ${stdin_file}
    Set Test Variable    ${LAST_RESULT}    ${result}

the user restores from backup
    Run Lynx    --restore

the encrypted vault file should exist
    File Should Exist    ${TEMP_DB}.enc

the encrypted vault salt file should exist
    File Should Exist    ${TEMP_DB}.salt

the plain database should not exist
    File Should Not Exist    ${TEMP_DB}

the plain database should exist
    File Should Exist    ${TEMP_DB}

the encrypted vault file should not exist
    File Should Not Exist    ${TEMP_DB}.enc

a backup file should exist
    ${enc_bak}=    Set Variable    ${TEMP_DB}.enc.bak
    ${plain_bak}=    Set Variable    ${TEMP_DB}.bak
    ${enc_exists}=    Run Keyword And Return Status    File Should Exist    ${enc_bak}
    ${plain_exists}=    Run Keyword And Return Status    File Should Exist    ${plain_bak}
    Should Be True    ${enc_exists} or ${plain_exists}    No backup file found


*** Test Cases ***
Encrypt An Existing Database
    [Documentation]    Encrypting a database should create .enc and .salt files
    ...                and remove the plain database.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user encrypts the database with password "test123"
    Then the output should contain "encrypted"
    And the encrypted vault file should exist
    And the encrypted vault salt file should exist
    And the plain database should not exist

Decrypt And List With Correct Password
    [Documentation]    Opening an encrypted vault with correct password should
    ...                allow listing instruments.
    Given an instrument "AAPL" with 5 shares at avg price 100
    When the user encrypts the database with password "secret"
    And the user decrypts and lists with password "secret"
    Then the output should contain "Vault unlocked"

Decrypt With Wrong Password Fails
    [Documentation]    Opening an encrypted vault with wrong password should fail.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user encrypts the database with password "correct"
    And the user decrypts and lists with password "wrong"
    Then the output should contain "Wrong password"

Disable Encryption
    [Documentation]    Disabling encryption should restore the plain database
    ...                and remove the vault files.
    Given an instrument "MSFT" with 8 shares at avg price 300
    When the user encrypts the database with password "pass"
    And the user disables encryption with password "pass"
    Then the output should contain "Encryption removed"
    And the plain database should exist
    And the encrypted vault file should not exist

Restore From Backup
    [Documentation]    The restore command should recover from the backup file.
    Given an instrument "AAPL" with 10 shares at avg price 150
    And a backup file should exist
    When the user restores from backup
    Then the output should contain "restored"

Encrypt Already Encrypted Database Fails
    [Documentation]    Encrypting an already encrypted database should fail.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user encrypts the database with password "pw1"
    And the user encrypts the database with password "pw2"
    Then the output should contain "already encrypted"

Restore Without Backup Fails
    [Documentation]    Restoring without any backup should fail.
    Given an empty portfolio
    # Remove any backup files that may exist
    Remove File    ${TEMP_DB}.bak
    Remove File    ${TEMP_DB}.enc.bak
    When the user restores from backup
    Then the output should contain "No backup found"

Disable Encryption On Plain Database Fails
    [Documentation]    Disabling encryption on a plain database should fail.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user disables encryption with password "anything"
    Then the output should contain "not encrypted"

Data Persists After Encrypt Decrypt Cycle
    [Documentation]    Adding data, encrypting, then decrypting should preserve
    ...                all instruments.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user encrypts the database with password "cycle"
    And the user decrypts and lists with password "cycle"
    Then the output should contain "Vault unlocked"
    And the output should contain "Apple" ignoring case
