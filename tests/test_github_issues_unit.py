import pytest
import re
from urllib.parse import unquote
from utils.github_issues import create_issue_url, error_with_issue_link, GITHUB_ISSUES_URL

def test_create_issue_url_title_only():
    title = "Test Issue"
    expected = f"{GITHUB_ISSUES_URL}?title=Test%20Issue"
    assert create_issue_url(title) == expected

def test_create_issue_url_with_body():
    title = "Test Issue"
    body = "Test Body"
    expected = f"{GITHUB_ISSUES_URL}?title=Test%20Issue&body=Test%20Body"
    assert create_issue_url(title, body) == expected

def test_create_issue_url_special_characters():
    title = "Bug: [App] Critical Error!"
    body = "Steps to reproduce:\n1. Open app\n2. Click button"
    url = create_issue_url(title, body)
    assert "title=Bug%3A%20%5BApp%5D%20Critical%20Error%21" in url
    assert "body=Steps%20to%20reproduce%3A%0A1.%20Open%20app%0A2.%20Click%20button" in url

def test_error_with_issue_link_basic():
    error_message = "Something went wrong"
    result = error_with_issue_link(error_message)
    assert error_message in result
    assert "[📝 Submit a bug report]" in result

    match = re.search(r"\[📝 Submit a bug report\]\((.*?)\)", result)
    assert match is not None
    url = match.group(1)
    decoded_url = unquote(url)
    assert "Traceback:\nNot provided" in decoded_url

def test_error_with_issue_link_with_legacy_details():
    # Test backward compatibility where details was used for traceback
    error_message = "Something went wrong"
    legacy_traceback = "Traceback contents"
    result = error_with_issue_link(error_message, legacy_traceback)

    match = re.search(r"\[📝 Submit a bug report\]\((.*?)\)", result)
    assert match is not None
    url = match.group(1)
    decoded_url = unquote(url)
    assert f"Traceback:\n{legacy_traceback}" in decoded_url

def test_error_with_issue_link_with_details_and_traceback():
    error_message = "Something went wrong"
    error_details = "Specific details here"
    error_traceback = "Traceback here"
    result = error_with_issue_link(error_message, error_details, error_traceback=error_traceback)
    assert error_message in result
    assert error_details in result
    assert "```" in result
    assert "[📝 Submit a bug report]" in result

    match = re.search(r"\[📝 Submit a bug report\]\((.*?)\)", result)
    assert match is not None
    url = match.group(1)
    decoded_url = unquote(url)
    assert f"Traceback:\n{error_traceback}" in decoded_url
    assert f"Details:\n{error_details}" in decoded_url

def test_error_with_issue_link_custom_traceback():
    error_message = "Something went wrong"
    custom_traceback = "Traceback (most recent call last):\n  File \"app.py\", line 10, in <module>\n    1/0\nZeroDivisionError: division by zero"
    result = error_with_issue_link(error_message, error_traceback=custom_traceback)

    match = re.search(r"\[📝 Submit a bug report\]\((.*?)\)", result)
    assert match is not None
    url = match.group(1)
    decoded_url = unquote(url)
    assert custom_traceback in decoded_url
