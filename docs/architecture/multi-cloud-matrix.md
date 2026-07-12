# AQIP Multi-Cloud Matrix

The platform supports three deployment targets: AWS, GCP, and
Modal. Each lib under `libs/aqip-*` exposes a cloud-specific
adapter that satisfies the same interface, so agent code is
portable without changes. The matrix below maps each lib to its
adapters.

| Lib | Abstract | AWS | GCP | Modal | Local / Dev |
|---|---|---|---|---|---|
| `aqip-events` | `EventBus` | `AWSEventBridgeBus` (EventBridge + SQS) | `GCPPubSubBus` (Pub/Sub) | `ModalQueueBus` (`modal.Queue`) | `InMemoryEventBus` |
| `aqip-storage` | `ObjectStore` | `S3ObjectStore` | `GCSObjectStore` | `ModalVolumeObjectStore` | `InMemoryObjectStore` / `LocalFileSystemObjectStore` |
| `aqip-state` | `StateStore` | `ElastiCacheStateStore` | `MemorystoreStateStore` | `ModalDictStateStore` | `InMemoryStateStore` |
| `aqip-vector` | `VectorIndex` (Protocol) | `ZvecIndex` (persisted to S3 / GCS / Volume) | (same zvec binary) | (same zvec binary) | `InMemoryVectorIndex` |
| `aqip-llm` | `LLMClient` | `BedrockLLMClient` | `VertexLLMClient` | `VLLMModalLLMClient` | `FakeLLMClient` |
| `aqip-compute` | `ComputeRuntime` | `AWSLambdaComputeRuntime` | `GCPFunctionsComputeRuntime` | `ModalComputeRuntime` | `InProcessComputeRuntime` |
| `aqip-portability` | `CloudAdapter` | `AWSAdapter` | `GCPAdapter` | `ModalAdapter` | `LocalAdapter` |

## Selection mechanism

The active profile is controlled by environment variables:

* `AQIP_CLOUD` (default `local`) — selects the `CloudAdapter`. Drives
  nothing on its own; consumers read it indirectly via
  `aqip_portability.get_adapter()`.
* `AQIP_LLM_BACKEND` (default `fake`) — selects the LLM backend.
  See `aqip_llm.client.get_llm_client`.
* `AQIP_OBJECT_STORE` (default `memory`, or `fs:<path>`) — selects
  the object store. See `aqip_storage.store.get_object_store`.
* `AQIP_VECTOR_DIM` (default `768`) — sets the in-memory vector
  index's dimension. The zvec index takes its dimension at
  construction time.

Cloud-specific SDKs (`boto3`, `google-cloud-*`, `modal`) are
**lazy-imported**. The libs import cleanly on machines without any
of them installed; the adapter's `_available` flag stays `False`
and every method raises a clear `RuntimeError`.

## Cross-cloud compatibility

Agent code **never** imports a cloud SDK directly. The only
allowed import paths are the abstract interfaces and the
`get_*_singleton` helpers, all of which return either a real
adapter (when credentials are available) or an in-memory
fallback (when they are not). This is enforced by
`tests/cross_cloud/`, which parameterises the same test across
the four profiles and asserts that every agent produces identical
structured output regardless of which cloud it's "running" on.

## Cross-cloud composition

A platform deployment can mix and match libs across clouds —
e.g. AWS Lambda for compute, GCS for object storage, Modal for
vLLM. The integration is straightforward:

1. `AQIP_CLOUD=aws` selects the AWS compute adapter.
2. The `S3ObjectStore` is constructed explicitly in application
   bootstrap; the `AQIP_OBJECT_STORE` env var is ignored.
3. The `VLLMModalLLMClient` is constructed explicitly with a
   `AQIP_VLLM_URL` env var; the global `get_llm_client` is unused.

This pattern is documented for production deployments; the
default scaffolding (and all tests) uses one cloud per
deployment.
