*** Settings ***
Library     RequestsLibrary
Library     Collections
Resource    resources/common.robot

Suite Setup       Setup API Suite
Suite Teardown    Teardown API Suite


*** Keywords ***
Setup API Suite
    Setup Temp Database
    Start API Server
    Create Session    lynx    ${BASE_URL}

Teardown API Suite
    Stop API Server
    Teardown Temp Database

# ---- BDD step keywords specific to API tests ----
a running API server
    Log    API server is running (started in Suite Setup)

the API has an instrument "${ticker}" with ${shares} shares at avg price ${price}
    ${body}=    Create Dictionary    ticker=${ticker}    shares=${shares}    avg_price=${price}
    POST On Session    lynx    /api/portfolio    json=${body}    expected_status=any

the API has an instrument "${ticker}" with ${shares} shares without avg price
    ${body}=    Create Dictionary    ticker=${ticker}    shares=${shares}
    POST On Session    lynx    /api/portfolio    json=${body}    expected_status=any

the client sends a GET request to "${path}"
    ${resp}=    GET On Session    lynx    ${path}
    Set Test Variable    ${RESPONSE}    ${resp}

the client sends a GET request to "${path}" expecting ${status}
    ${resp}=    GET On Session    lynx    ${path}    expected_status=${status}
    Set Test Variable    ${RESPONSE}    ${resp}

the client sends a POST request to "${path}" with body "${body_str}"
    ${body}=    Evaluate    ${body_str}
    ${resp}=    POST On Session    lynx    ${path}    json=${body}    expected_status=any
    Set Test Variable    ${RESPONSE}    ${resp}

the client sends a PUT request to "${path}" with body "${body_str}"
    ${body}=    Evaluate    ${body_str}
    ${resp}=    PUT On Session    lynx    ${path}    json=${body}    expected_status=any
    Set Test Variable    ${RESPONSE}    ${resp}

the client sends a DELETE request to "${path}"
    ${resp}=    DELETE On Session    lynx    ${path}    expected_status=any
    Set Test Variable    ${RESPONSE}    ${resp}

the response status should be ${status}
    Status Should Be    ${status}    ${RESPONSE}

the response body should contain key "${key}"
    Dictionary Should Contain Key    ${RESPONSE.json()}    ${key}

the response body key "${key}" should be "${value}"
    Should Be Equal As Strings    ${RESPONSE.json()}[${key}]    ${value}

the response body should be a list
    ${type}=    Evaluate    type($RESPONSE.json()).__name__
    Should Be Equal    ${type}    list


*** Test Cases ***
Health Check Returns OK
    [Documentation]    The health endpoint should return status 200 with "ok".
    Given a running API server
    When the client sends a GET request to "/api/health"
    Then the response status should be 200
    And the response body key "status" should be "ok"

Version Returns Application Info
    [Documentation]    The version endpoint should return the app name and version.
    Given a running API server
    When the client sends a GET request to "/api/version"
    Then the response status should be 200
    And the response body key "name" should be "Lynx Portfolio"

Add Instrument Via API
    [Documentation]    POSTing a new instrument with cost basis should return 201.
    Given a running API server
    When the client sends a POST request to "/api/portfolio" with body "{'ticker': 'AAPL', 'shares': 10, 'avg_price': 150}"
    Then the response status should be 201
    And the response body key "status" should be "created"

Add Instrument Without Cost Basis Via API
    [Documentation]    POSTing without avg_price should succeed (cost not tracked).
    Given a running API server
    When the client sends a POST request to "/api/portfolio" with body "{'ticker': 'TSLA', 'shares': 5}"
    Then the response status should be 201

List Portfolio Via API
    [Documentation]    GET /api/portfolio should return a JSON array.
    Given the API has an instrument "AAPL" with 10 shares at avg price 150
    When the client sends a GET request to "/api/portfolio"
    Then the response status should be 200
    And the response body should be a list

Get Single Instrument Via API
    [Documentation]    GET /api/portfolio/AAPL should return the instrument details.
    Given the API has an instrument "AAPL" with 10 shares at avg price 150
    When the client sends a GET request to "/api/portfolio/AAPL"
    Then the response status should be 200
    And the response body should contain key "ticker"

Get Nonexistent Instrument Returns 404
    [Documentation]    Requesting a ticker that does not exist should return 404.
    Given a running API server
    When the client sends a GET request to "/api/portfolio/ZZZZ" expecting 404
    Then the response status should be 404

Update Instrument Via API
    [Documentation]    PUTting updated shares should return 200.
    Given the API has an instrument "AAPL" with 10 shares at avg price 150
    When the client sends a PUT request to "/api/portfolio/AAPL" with body "{'shares': 20}"
    Then the response status should be 200
    And the response body key "status" should be "updated"

Delete Instrument Via API
    [Documentation]    DELETEing an existing instrument should return 200.
    Given the API has an instrument "AAPL" with 10 shares at avg price 150
    When the client sends a DELETE request to "/api/portfolio/AAPL"
    Then the response status should be 200
    And the response body key "status" should be "deleted"

Forex Rates Available
    [Documentation]    The forex rates endpoint should return rates with EUR base.
    Given a running API server
    When the client sends a GET request to "/api/forex/rates"
    Then the response status should be 200
    And the response body key "base_currency" should be "EUR"

Clear Cache Without Force Fails
    [Documentation]    Clearing cache without ?force=true should return 400.
    Given a running API server
    When the client sends a DELETE request to "/api/cache"
    Then the response status should be 400

Clear Cache With Force Succeeds
    [Documentation]    Clearing cache with ?force=true should return 200.
    Given a running API server
    When the client sends a DELETE request to "/api/cache?force=true"
    Then the response status should be 200
    And the response body key "status" should be "cleared"

Add Instrument With Invalid Ticker Returns 400
    [Documentation]    POSTing with special chars in ticker should return 400.
    Given a running API server
    When the client sends a POST request to "/api/portfolio" with body "{'ticker': 'A; DROP TABLE', 'shares': 10}"
    Then the response status should be 400
    And the response body should contain key "error"

Add Instrument With Negative Shares Returns 400
    [Documentation]    POSTing with negative shares should return 400.
    Given a running API server
    When the client sends a POST request to "/api/portfolio" with body "{'ticker': 'TEST', 'shares': -5}"
    Then the response status should be 400
    And the response body should contain key "error"

Add Instrument With Zero Shares Returns 400
    [Documentation]    POSTing with zero shares should return 400.
    Given a running API server
    When the client sends a POST request to "/api/portfolio" with body "{'ticker': 'TEST', 'shares': 0}"
    Then the response status should be 400

Add Instrument With Negative Price Returns 400
    [Documentation]    POSTing with negative avg_price should return 400.
    Given a running API server
    When the client sends a POST request to "/api/portfolio" with body "{'ticker': 'TEST', 'shares': 10, 'avg_price': -100}"
    Then the response status should be 400

Update With Negative Shares Returns 400
    [Documentation]    PUTting negative shares should return 400.
    Given the API has an instrument "AAPL" with 10 shares at avg price 150
    When the client sends a PUT request to "/api/portfolio/AAPL" with body "{'shares': -5}"
    Then the response status should be 400

Add Without Ticker Or ISIN Returns 400
    [Documentation]    POSTing without ticker or ISIN should return 400.
    Given a running API server
    When the client sends a POST request to "/api/portfolio" with body "{'shares': 10}"
    Then the response status should be 400
