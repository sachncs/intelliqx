"""AWS CDK stack: observability (CloudWatch + X-Ray)."""

from __future__ import annotations

from aws_cdk import Stack


class ObservabilityStack(Stack):
    """Observability stack: CloudWatch dashboards, alarms, X-Ray."""
