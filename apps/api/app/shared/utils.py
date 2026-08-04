"""Cross-module helpers shared by more than one feature module."""

from fastapi import HTTPException


def _rl_error(tool: str, limit: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Daily limit of {limit} {tool} uses reached. Resets at midnight UTC."
    )
