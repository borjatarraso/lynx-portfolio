*** Settings ***
Library     Process
Library     OperatingSystem
Resource    resources/common.robot

Suite Setup       Setup Temp Database
Suite Teardown    Teardown Temp Database


*** Test Cases ***
Display Application Version
    [Documentation]    Verify the version flag outputs the current version string.
    Given an empty portfolio
    When the user runs lynx with "-v"
    Then the output should contain "v2.0"

Add Instrument With Cost Basis
    [Documentation]    Adding an instrument with ticker, shares, and avg price should succeed.
    Given an empty portfolio
    When the user adds instrument "AAPL" with 10 shares at avg price 150
    Then the output should contain "Added AAPL"

Add Instrument Without Cost Basis
    [Documentation]    Adding an instrument without avg price should succeed (cost not tracked).
    Given an empty portfolio
    When the user adds instrument "MSFT" with 5 shares without avg price
    Then the output should contain "Added MSFT"

List Portfolio After Adding Instrument
    [Documentation]    The list command should display previously added instruments.
    Given an instrument "GOOG" with 3 shares at avg price 100
    When the user lists the portfolio
    Then the output should contain "Alphabet" ignoring case

Show Instrument Detail
    [Documentation]    The show command should display detailed instrument information.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user shows instrument "AAPL"
    Then the output should contain "Apple" ignoring case

Update Instrument Shares
    [Documentation]    Updating shares for an existing instrument should succeed.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user updates instrument "AAPL" with shares 15
    Then the output should contain "Updated"

Delete Existing Instrument
    [Documentation]    Deleting an existing instrument with --force should succeed.
    Given an instrument "AAPL" with 10 shares at avg price 150
    When the user deletes instrument "AAPL" with force
    Then the output should contain "Deleted"

Delete Nonexistent Instrument
    [Documentation]    Attempting to delete a ticker that does not exist should report an error.
    Given an empty portfolio
    When the user deletes instrument "ZZZZ" with force
    Then the output should contain "not found"

Import Instruments From JSON File
    [Documentation]    The import command should bulk-add instruments from a JSON file.
    Given an empty portfolio
    When the user imports from "${EXECDIR}/examples/portfolio.json"
    Then the output should contain "Import complete"
