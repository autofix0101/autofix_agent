"""
Delivery module — ships validated patches back to GitHub as pull requests.
"""
from .pull_request import PullRequestError, create_pull_request_for_job

__all__ = [
    "PullRequestError",
    "create_pull_request_for_job",
]
