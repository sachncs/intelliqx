"""AWS cloud adapter.

The adapter itself does not import ``boto3``; cloud-specific SDK access
lives in feature-specific libs (e.g. ``aqip-storage.aws``,
``aqip-events.aws``). The adapter just exposes the resolved config and
a typed entry point for AWS-specific helpers.
"""

from aqip_portability.adapter import CloudAdapter


class AWSAdapter(CloudAdapter):
    """AWS adapter.

    The class is intentionally a near-empty marker: real AWS access
    happens lazily inside the feature-specific libs (storage, events,
    state, llm, compute). Tests can assert the provider is AWS via
    ``adapter.is_aws`` without ever instantiating a boto3 client.
    """
