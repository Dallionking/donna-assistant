"""
GitHub integration tools for Donna.

Handles reading issues, PRs, and repository information.
"""

from typing import Optional, List
from datetime import datetime

from langchain_core.tools import tool
from github import Github

from donna.config import get_settings


def get_github_client() -> Optional[Github]:
    """Get GitHub client."""
    settings = get_settings()
    
    if not settings.github_token:
        return None
    
    return Github(settings.github_token)


@tool
def list_github_issues(repo_name: Optional[str] = None, state: str = "open") -> str:
    """
    List GitHub issues across repositories.
    
    Args:
        repo_name: Specific repository (owner/repo format). If None, lists from all repos.
        state: Issue state - "open", "closed", or "all"
    
    Returns list of issues with titles, labels, and assignees.
    """
    gh = get_github_client()
    
    if gh is None:
        return """⚠️ GitHub not configured.

To set up GitHub:
1. Create a Personal Access Token at github.com/settings/tokens
2. Add GITHUB_TOKEN to your .env file

This will allow me to:
- List issues across your repos
- Create issues from brain dumps
- Check PR status
"""
    
    try:
        if repo_name:
            # Single repo
            repo = gh.get_repo(repo_name)
            issues = list(repo.get_issues(state=state))[:20]
            
            if not issues:
                return f"No {state} issues in {repo_name}"
            
            lines = [f"# Issues in {repo_name}\n"]
            for issue in issues:
                labels = ", ".join([l.name for l in issue.labels]) or "No labels"
                lines.append(f"- **#{issue.number}**: {issue.title}")
                lines.append(f"  Labels: {labels}")
            
            return "\n".join(lines)
        
        else:
            # All repos the user has access to
            user = gh.get_user()
            repos = list(user.get_repos())[:10]  # Limit to 10 repos
            
            lines = ["# Open Issues Across Repositories\n"]
            
            for repo in repos:
                issues = list(repo.get_issues(state="open"))[:5]  # 5 per repo
                if issues:
                    lines.append(f"## {repo.full_name}")
                    for issue in issues:
                        lines.append(f"- **#{issue.number}**: {issue.title}")
                    lines.append("")
            
            if len(lines) == 1:
                return "No open issues found across your repositories."
            
            return "\n".join(lines)
            
    except Exception as e:
        return f"Error fetching GitHub issues: {str(e)}"


@tool
def create_github_issue(
    repo_name: str,
    title: str,
    body: str,
    labels: Optional[List[str]] = None
) -> str:
    """
    Create a new GitHub issue.
    
    Args:
        repo_name: Repository in owner/repo format
        title: Issue title
        body: Issue body/description
        labels: Optional list of label names
    
    Returns confirmation with issue URL.
    """
    gh = get_github_client()
    
    if gh is None:
        return "⚠️ GitHub not configured. Add GITHUB_TOKEN to .env"
    
    try:
        repo = gh.get_repo(repo_name)
        
        issue = repo.create_issue(
            title=title,
            body=body,
            labels=labels or []
        )
        
        return f"""✅ Issue created!

**#{issue.number}**: {issue.title}
**URL**: {issue.html_url}
"""
    except Exception as e:
        return f"Error creating issue: {str(e)}"


@tool
def list_pull_requests(repo_name: Optional[str] = None, state: str = "open") -> str:
    """
    List pull requests.
    
    Args:
        repo_name: Specific repository (owner/repo format)
        state: PR state - "open", "closed", or "all"
    
    Returns list of PRs with status.
    """
    gh = get_github_client()
    
    if gh is None:
        return "⚠️ GitHub not configured. Add GITHUB_TOKEN to .env"
    
    try:
        if not repo_name:
            return "Please specify a repository: /github prs owner/repo"
        
        repo = gh.get_repo(repo_name)
        prs = list(repo.get_pulls(state=state))[:20]
        
        if not prs:
            return f"No {state} PRs in {repo_name}"
        
        lines = [f"# Pull Requests in {repo_name}\n"]
        
        for pr in prs:
            status = "🟢" if pr.mergeable else "🔴"
            lines.append(f"- {status} **#{pr.number}**: {pr.title}")
            lines.append(f"  Branch: `{pr.head.ref}` → `{pr.base.ref}`")
            lines.append(f"  Author: {pr.user.login}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error fetching PRs: {str(e)}"


