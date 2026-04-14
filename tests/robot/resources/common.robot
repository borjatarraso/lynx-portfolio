*** Settings ***
Library    Process
Library    OperatingSystem
Library    String


*** Variables ***
${PYTHON}          python3
${LYNX_SCRIPT}     /home/overdrive/claude/lince-investor/lynx-portfolio/lynx.py
${BASE_URL}        http://localhost:15123
${TEMP_DB}         ${EMPTY}
${LAST_RESULT}     ${EMPTY}


*** Keywords ***
# ---------------------------------------------------------------------------
# Setup / Teardown
# ---------------------------------------------------------------------------
Setup Temp Database
    ${tmp_file}=    Evaluate    __import__('tempfile').mkstemp(suffix='.db')[1]
    Set Suite Variable    ${TEMP_DB}    ${tmp_file}
    Set Environment Variable    LYNX_DB_PATH    ${TEMP_DB}

Teardown Temp Database
    Remove File    ${TEMP_DB}
    Remove Environment Variable    LYNX_DB_PATH

Start API Server
    ${process}=    Start Process    ${PYTHON}    ${LYNX_SCRIPT}    --api
    ...    --port    15123
    ...    env:LYNX_DB_PATH=${TEMP_DB}
    Set Suite Variable    ${API_PROCESS}    ${process}
    Sleep    2s    Wait for API server to initialize

Stop API Server
    Terminate Process    ${API_PROCESS}    kill=true

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
Run Lynx
    [Arguments]    @{args}
    ${result}=    Run Process    ${PYTHON}    ${LYNX_SCRIPT}    -c    @{args}
    ...    env:LYNX_DB_PATH=${TEMP_DB}
    Set Test Variable    ${LAST_RESULT}    ${result}
    RETURN    ${result}

# ---------------------------------------------------------------------------
# BDD step keywords  (Given / When / Then)
# ---------------------------------------------------------------------------
an empty portfolio
    Log    Portfolio is empty (fresh temp DB)

an instrument "${ticker}" with ${shares} shares at avg price ${price}
    Run Lynx    add    --ticker    ${ticker}    --shares    ${shares}    --avg-price    ${price}

an instrument "${ticker}" with ${shares} shares without avg price
    Run Lynx    add    --ticker    ${ticker}    --shares    ${shares}

the user runs lynx with "${args}"
    @{arg_list}=    Split String    ${args}
    Run Lynx    @{arg_list}

the user adds instrument "${ticker}" with ${shares} shares at avg price ${price}
    Run Lynx    add    --ticker    ${ticker}    --shares    ${shares}    --avg-price    ${price}

the user adds instrument "${ticker}" with ${shares} shares without avg price
    Run Lynx    add    --ticker    ${ticker}    --shares    ${shares}

the user lists the portfolio
    Run Lynx    list

the user shows instrument "${ticker}"
    Run Lynx    show    --ticker    ${ticker}

the user updates instrument "${ticker}" with shares ${shares}
    Run Lynx    update    --ticker    ${ticker}    --shares    ${shares}

the user deletes instrument "${ticker}" with force
    Run Lynx    delete    --ticker    ${ticker}    --force

the user imports from "${filepath}"
    Run Lynx    import    --file    ${filepath}

the output should contain "${text}"
    Should Contain    ${LAST_RESULT.stdout}    ${text}

the output should contain "${text}" ignoring case
    ${lower_out}=    Convert To Lower Case    ${LAST_RESULT.stdout}
    ${lower_text}=    Convert To Lower Case    ${text}
    Should Contain    ${lower_out}    ${lower_text}

the exit code should be ${code}
    Should Be Equal As Integers    ${LAST_RESULT.rc}    ${code}
