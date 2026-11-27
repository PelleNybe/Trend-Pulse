"""
GitHub Issues tool module

Provides the ability to create GitHub Issues URLs and display linked error messages
Data model definition location：
- No data model
"""

from urllib.parse import quote

GITHUB_REPO = "PelleNybe/Trend-Pulse"
GITHUB_ISSUES_URL = f"https://github.com/{GITHUB_REPO}/issues/new"


def create_issue_url(title: str, body: str = "") -> str:
    """
    create GitHub Issues URL，Pre-populate title and content

    Args:
        title: Issue title
        body: Issue content（Optional）

    Returns:
        complete GitHub Issues URL
    """
    encoded_title = quote(title)
    encoded_body = quote(body) if body else ""

    if encoded_body:
        return f"{GITHUB_ISSUES_URL}?title={encoded_title}&body={encoded_body}"
    else:
        return f"{GITHUB_ISSUES_URL}?title={encoded_title}"


def error_with_issue_link(
    error_message: str,
    error_details: str = "",
    app_name: str = "Streamlit App",
    error_traceback: str = "Not provided",
) -> str:
    """
    Generate error message string with link to GitHub Issues

    Only used in general exception handling，Not used for user configuration errors

    Args:
        error_message: error message
        error_details: error details（Optional，for filling to Issue body）
        app_name: Application name，Used to identify the source of errors
        error_traceback: Error traceback（Optional）

    Returns:
        Markdown format string containing error message and link to GitHub Issues
    """
    # Use existing error_details as traceback if error_traceback is not provided
    # This maintains backward compatibility with existing calls
    if error_details and error_traceback == "Not provided":
        error_traceback = error_details
        error_details = ""

    issue_title = f"[{app_name}] {error_message[:50]}"
    issue_body = f"Issue: {error_message}\nTraceback:\n{error_traceback}"

    issue_body_parts = [issue_body]
    if error_details:
        issue_body_parts.append(f"\nDetails:\n{error_details}")
    issue_body_parts.append("\n")
    issue_body = "".join(issue_body_parts)

    issue_url = create_issue_url(issue_title, issue_body)

    error_display = f"{error_message}\n\n[📝 Submit a bug report]({issue_url})"

    if error_details:
        error_display = f"{error_message}\n\n```\n{error_details}\n```\n\n[📝 Submit a bug report]({issue_url})"

    return error_display


__all__ = [
    "create_issue_url",
    "error_with_issue_link",
    "GITHUB_REPO",
    "GITHUB_ISSUES_URL",
]
