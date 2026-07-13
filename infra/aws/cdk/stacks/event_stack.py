"""AWS CDK stack: events (EventBridge + SQS)."""

from __future__ import annotations

from aws_cdk import Stack


class EventStack(Stack):
    """Event bus and queues for IntelliqX."""
