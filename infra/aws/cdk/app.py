"""AWS CDK app for AQIP Phase 1.

Stacks:
- ApiStack: API Gateway + Lambda
- EventStack: EventBridge + SQS
- StorageStack: S3 + DynamoDB + ElastiCache
- ComputeStack: Step Functions
- ObservabilityStack: CloudWatch + X-Ray
"""

from aws_cdk import App

from infra.aws.cdk.stacks.api_stack import ApiStack
from infra.aws.cdk.stacks.compute_stack import ComputeStack
from infra.aws.cdk.stacks.event_stack import EventStack
from infra.aws.cdk.stacks.observability_stack import ObservabilityStack
from infra.aws.cdk.stacks.storage_stack import StorageStack


def build_app() -> App:
    app = App()
    env_name = app.node.try_get_context("env") or "dev"
    region = app.node.try_get_context("region") or "us-east-1"

    storage = StorageStack(app, f"aqip-storage-{env_name}", env_name=env_name, region=region)
    events = EventStack(app, f"aqip-events-{env_name}", env_name=env_name, region=region, storage=storage)
    compute = ComputeStack(
        app, f"aqip-compute-{env_name}", env_name=env_name, region=region, storage=storage, events=events
    )
    api = ApiStack(
        app,
        f"aqip-api-{env_name}",
        env_name=env_name,
        region=region,
        storage=storage,
        events=events,
        compute=compute,
    )
    ObservabilityStack(
        app,
        f"aqip-obs-{env_name}",
        env_name=env_name,
        region=region,
        storage=storage,
        events=events,
        compute=compute,
        api=api,
    )
    return app


app = build_app()
app.synth()