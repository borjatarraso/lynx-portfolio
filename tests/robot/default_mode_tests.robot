*** Settings ***
Library     Process
Library     OperatingSystem
Library     String
Resource    resources/common.robot

Test Setup       Setup Temp Database
Test Teardown    Teardown Temp Database


*** Test Cases ***
Default Mode Is Production With LYNX_DB_PATH
    [Documentation]    When LYNX_DB_PATH is set, the program uses production
    ...                mode by default and subcommands work via -c.
    Given an empty portfolio
    When the user adds instrument "AAPL" with 10 shares at avg price 150
    Then the output should contain "Added AAPL"
    When the user lists the portfolio
    Then the output should contain "Apple" ignoring case

Devel Mode Creates Temporary Database
    [Documentation]    Running with --devel should use a temp DB; data is not
    ...                persisted to the configured path.
    # Must remove LYNX_DB_PATH from environment to test real --devel behavior
    Remove Environment Variable    LYNX_DB_PATH
    ${result}=    Run Process    ${PYTHON}    ${LYNX_SCRIPT}
    ...    --devel    -c    list
    # Restore LYNX_DB_PATH for subsequent tests
    Set Environment Variable    LYNX_DB_PATH    ${TEMP_DB}
    Should Contain    ${result.stdout}    DEVEL MODE

Console Mode Required For Subcommands
    [Documentation]    Subcommands like list/add/show only work in console mode.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user lists the portfolio
    Then the output should contain "Apple" ignoring case

Version Flag Works Without Mode
    [Documentation]    The -v flag should print version regardless of mode.
    When the user runs lynx with "-v"
    Then the output should contain "v2.0"

Encrypt Works Without Explicit Production Flag
    [Documentation]    Vault operations should work without --production when
    ...                LYNX_DB_PATH is set (not in devel mode).
    Given an instrument "AAPL" with 10 shares at avg price 150
    ${stdin_file}=    Set Variable    ${TEMP_DB}_stdin.txt
    Create File    ${stdin_file}    test123\ntest123\ntest123\n
    ${result}=    Run Process    ${PYTHON}    ${LYNX_SCRIPT}    --encrypt
    ...    env:LYNX_DB_PATH=${TEMP_DB}    stdin=${stdin_file}
    Remove File    ${stdin_file}
    Should Contain    ${result.stdout}    encrypted

Encrypt Fails In Devel Mode
    [Documentation]    Vault operations should fail when --devel is specified
    ...                and no LYNX_DB_PATH env override is set.
    ${stdin_file}=    Set Variable    ${TEMP_DB}_stdin.txt
    Create File    ${stdin_file}    test123\ntest123\ntest123\n
    # Must remove LYNX_DB_PATH from environment to test real --devel behavior
    Remove Environment Variable    LYNX_DB_PATH
    ${result}=    Run Process    ${PYTHON}    ${LYNX_SCRIPT}    --devel    --encrypt
    ...    stdin=${stdin_file}
    Remove File    ${stdin_file}
    # Restore LYNX_DB_PATH for subsequent tests
    Set Environment Variable    LYNX_DB_PATH    ${TEMP_DB}
    Should Contain    ${result.stdout}    cannot be used with --devel
