"""AWS CDK stack: storage (S3, DynamoDB, ElastiCache)."""

from __future__ import annotations

from aws_cdk import Stack


class StorageStack(Stack):
    """Storage stack: S3 buckets, DynamoDB tables, ElastiCache cluster."""
