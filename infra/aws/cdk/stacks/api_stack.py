"""AWS CDK stack: API Gateway + Lambda for IntelliqX API."""

from __future__ import annotations

from aws_cdk import Stack


class ApiStack(Stack):
    """Public-facing API: API Gateway + Lambda."""
