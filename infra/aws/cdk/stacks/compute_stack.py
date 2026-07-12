"""AWS CDK stack: compute (Step Functions, Lambda, Fargate)."""

from __future__ import annotations

from aws_cdk import Stack


class ComputeStack(Stack):
    """Compute: Step Functions + Lambda + ECS Fargate for long agents."""