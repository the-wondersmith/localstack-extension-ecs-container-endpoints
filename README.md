LocalStack ECS Container Metadata Endpoints Extension
===============================
[![Install LocalStack Extension](https://cdn.localstack.cloud/gh/extension-badge.svg)](https://app.localstack.cloud/extensions/remote?url=git+https://github.com/the-wondersmith/localstack-extension-ecs-container-endpoints/#egg=localstack_extension_ecs_container_endpoints)

[//]: # (https://github.com/awslabs/amazon-ecs-local-container-endpoints)

An extension enabling LocalStack to provide local versions of
the [ECS Task IAM Roles endpoint](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) and
the [ECS Task Metadata Endpoints](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-metadata-endpoint.html).
Get the full [`amazon-ecs-local-container-endpoints`](https://github.com/awslabs/amazon-ecs-local-container-endpoints)
functionality directly in LocalStack without needing to have additional containers running!

The `amazon-ecs-local-container-endpoints` API is served through both the hostname
`http://metadata.ecs.localhost.localstack.cloud:4566` and
the [official "well-known" IP address](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-metadata-endpoint-v2.html#task-metadata-endpoint-v2-paths)
`http://169.254.170.2`.

## Install

Install the extension by running:

```bash
localstack extensions install localstack-extension-ecs-container-endpoints
```

## Usage

### Configuration

The extension passes all environment variables prefixed with `ECS_LOCAL_CONTAINER_ENDPOINTS_` (&#42;with a few
exceptions)
through to the
`amazon-ecs-local-container-endpoints`
process. See
the [upstream docs](https://github.com/awslabs/amazon-ecs-local-container-endpoints/blob/mainline/docs/configuration.md#environment-variables)
for information on configuring `amazon-ecs-local-container-endpoints`.

> [!IMPORTANT]
> Some environment variables are forcibly set to ensure the`amazon-ecs-local-container-endpoints` process
> targets the running LocalStack instance. Specifically, the following environment variables will be ignored:
> - IAM_ENDPOINT
> - STS_ENDPOINT
> - ECS_LOCAL_METADATA_PORT

## Licensing

* `amazon-ecs-local-container-endpoints` is licensed under
  the [Apache License 2.0](https://github.com/awslabs/amazon-ecs-local-container-endpoints/blob/mainline/LICENSE)
* A pre-built `amazon-ecs-local-container-endpoints` binary is (effectively) vendored with this extension, slight
  modifications are made during the build process
  to make it compile properly for supported operating systems and processor architectures. The modifications retain the
  Apache License 2.0
  license.
* The extension code is licensed under the [AGPL-3.0-or-later](LICENSE.txt)
