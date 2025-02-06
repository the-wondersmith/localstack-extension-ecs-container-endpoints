from __future__ import annotations

import os
import re
import logging
import platform
import subprocess
from operator import methodcaller
from typing import IO, AnyStr, cast

from localstack import config, constants
from localstack.config import internal_service_url
from localstack.utils.net import get_free_tcp_port
from localstack.utils.urls import localstack_host
from localstack.extensions.api import Extension
from localstack.extensions.api.http import Router, RouteHandler, ProxyHandler
from localstack.packages import Package
from localstack.packages.core import PermissionDownloadInstaller, GitHubReleaseInstaller
from localstack.utils.platform import get_arch
from localstack.utils.threads import FuncThread, start_worker_thread
from more_itertools import collapse
from rolo.routing.router import E as ENDPOINT
from werkzeug.wrappers.response import Response

from localstack_extension_ecs_container_endpoints import (
    __version__ as extension_version,
)


LOG = logging.getLogger("localstack.extension.ecs-c-m-e")
URL_TEMPLATE = (
    "https://wondersmith.ngrok.io/amazon-ecs-local-container-endpoints-{os}-{arch}"
)
LOG_PATTERN = re.compile(
    r"time=\"[^\"]+\" level=(?P<level>[^ ]+) msg=(?P<message>\"?.+\"?)\s*$",
    flags=re.UNICODE | re.MULTILINE,
)


class EcsContainerEndpointsBinary(Package):
    """A class representing the ECS Container Endpoints binary.

    Handles the binary path and version management for the ECS Container Endpoints service.
    """

    def __init__(self, *_: any, **__: any):
        super().__init__("EcsContainerEndpoints", extension_version)

    @property
    def path(self) -> str | None:
        """Get the path to the locally-installed `amazon-ecs-local-container-endpoints` binary.

        Returns:
            str: The absolute path to the binary.
        """
        return self._get_installer(extension_version).get_executable_path()

    def get_versions(self) -> list[str]:
        """Get available versions of the `amazon-ecs-local-container-endpoints` binary.

        Returns:
            list: List of available version strings.
        """
        return [
            extension_version,
        ]

    def _get_installer(self, version: str) -> PermissionDownloadInstaller:
        """Get the installer for the `amazon-ecs-local-container-endpoints` binary.

        Returns:
            EcsContainerEndpointsBinaryInstaller: An installer instance.
        """
        return EcsContainerEndpointsBinaryInstaller(
            "amazon-ecs-local-container-endpoints",
            version,
        )


class EcsContainerEndpointsBinaryInstaller(PermissionDownloadInstaller):
    """Installer class for ECS Container Endpoints binary.

    Handles downloading and installation of the binary.
    """

    def _get_download_url(self) -> str:
        """Get the download URL for the binary.

        Returns:
            str: Download URL for the binary.
        """
        return URL_TEMPLATE.format(
            arch=get_arch(),
            os=platform.system().casefold(),
        )

    def _get_install_marker_path(self, install_dir: str) -> str:
        """Get the path for the installation marker file.

        Args:
            install_dir (str): The path to the local installation directory.

        Returns:
            str: Path to the installation marker file.
        """

        return os.path.join(install_dir, "amazon-ecs-local-container-endpoints")


class GHBinaryInstaller(GitHubReleaseInstaller):
    """GitHub binary installer class.

    Handles installation of `amazon-ecs-local-container-endpoints` binaries from GitHub releases.
    """

    def _get_github_asset_name(self) -> str:
        """Determines the name of the asset to download based on the local operating system and processor architecture.

        Returns:
            str: name of the asset to download from the GitHub repo's tag / version
        """
        os_name = platform.system().casefold()
        asset = f"amazon-ecs-local-container-endpoints-{os_name}-{get_arch()}"

        if os_name == "windows":
            asset += ".exe"

        return asset


ecs_container_endpoints = EcsContainerEndpointsBinary()


class ProxyRewriteHandler(ProxyHandler):
    """Handler for proxying (and optionally rewriting) requests
    to the extension's `amazon-ecs-local-container-endpoints` process."""

    rules: dict[re.Pattern[str], str] = {
        # The upstream `amazon-ecs-local-container-endpoints` project appears to be (effectively)
        # in maintenance mode, and hasn't had an update made or non-dependabot PR merged since
        # ~March 2023. There are, in fact, outstanding community PRs from 2020 that don't appear
        # as though they'll ever be merged.
        #
        # tl;dr it does not *appear* as though the maintainers (AWS Labs) have any intention of
        # actually adding support for the v4 endpoints, but the v3 endpoints appear to be largely
        # compatible, so we'll just set up the gateway routes to respond to v4 requests using the
        # v3 handlers.
        re.compile("^(/?)(v4/)(.*)$"): r"\1v3/\3",
    }

    def __call__(self, *args: any, **kwargs: any) -> Response:
        if isinstance((path := kwargs.pop("path", None)), str):
            for pattern, replacement in filter(
                lambda pair: pair[0].search(path),
                self.rules.items(),
            ):
                path = pattern.sub(replacement, path)

        kwargs["path"] = path

        LOG.debug(f"proxying request: [args: {args}, kwargs: {kwargs}]")

        return super().__call__(*args, **kwargs)


class EcsContainerEndpoints(Extension):
    """ECS Local Container Endpoints Localstack Extension.

    Manages the lifecycle and operation of a `amazon-ecs-local-container-endpoints` process as a service.
    """

    port: int = 0
    host_prefix: str = "metadata.ecs"
    name: str = "localstack-extension-ecs-container-endpoints"

    server_process: subprocess.Popen[str]

    stderr_forwarder: FuncThread
    stdout_forwarder: FuncThread

    @staticmethod
    def _forward_logs(*source: IO[AnyStr]) -> None:
        """Forward logs from the service to the logger.

        Args:
            source: The log stream(s) to forward.
        """

        for line in map(
            methodcaller("groupdict"),
            filter(
                None,
                map(LOG_PATTERN.search, map(str.strip, collapse(source, levels=2))),
            ),
        ):
            match line["level"]:
                case "info":
                    sink = LOG.info
                case "error":
                    sink = LOG.error
                case "warning":
                    sink = LOG.warning
                case _:
                    sink = LOG.debug

            sink(cast(str, line["message"]).removeprefix('"').removesuffix('"'))

    def on_extension_load(self) -> None:
        """Initialize the extension components.

        Called when LocalStack loads the extension.
        """
        LOG.setLevel(level=logging.DEBUG if config.DEBUG else logging.INFO)

        ecs_container_endpoints.install()

        LOG.debug("ECS container metadata endpoints extension loaded")

    def on_platform_start(self) -> None:
        """Start the `amazon-ecs-local-container-endpoints` server process.

        Called when LocalStack starts the main runtime.
        """
        LOG.info("starting ECS container metadata endpoints process ...")

        self.port = get_free_tcp_port()
        self.server_process = subprocess.Popen(
            [],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            executable=ecs_container_endpoints.path,
            env={
                # Set some sane defaults
                "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION")
                or constants.AWS_REGION_US_EAST_1,
                "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID")
                or constants.INTERNAL_AWS_ACCESS_KEY_ID,
                "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_ACCESS_KEY_ID")
                or constants.INTERNAL_AWS_SECRET_ACCESS_KEY,
                # Add user-supplied values, and allow them to
                # override the defaults if they're supplied
                **{
                    key.removeprefix("ECS_LOCAL_CONTAINER_ENDPOINTS_"): value
                    for key, value in os.environ.items()
                    if key.startswith("ECS_LOCAL_CONTAINER_ENDPOINTS_")
                },
                # Set (or overwrite) the "critical" values
                "ECS_LOCAL_METADATA_PORT": str(self.port),
                "IAM_ENDPOINT": internal_service_url(host="127.0.0.1"),
                "STS_ENDPOINT": internal_service_url(host="127.0.0.1"),
                "AWS_ENDPOINT_URL": internal_service_url(host="127.0.0.1"),
            },
        )

        self.stderr_forwarder = start_worker_thread(
            self._forward_logs,
            params=(self.server_process.stderr,),
            name="forward-container-endpoints-stderr",
        )
        self.stdout_forwarder = start_worker_thread(
            self._forward_logs,
            params=(self.server_process.stdout,),
            name="forward-container-endpoints-stdout",
        )

        LOG.debug(
            f"ECS container metadata endpoints process started on internal port {self.port}"
        )

    def on_platform_shutdown(self) -> None:
        """Stop and clean up the `amazon-ecs-local-container-endpoints` server process.

        Called when LocalStack is shutting down.
        Used to close the extension's resources (threads, processes, etc.).
        """
        if self.server_process.returncode is None:
            self.server_process.kill()

    def update_gateway_routes(self, router: Router[RouteHandler]) -> None:
        """Configure the extension's gateway routes.

        Called with the Router attached to the LocalStack gateway.
        Used to add "public" routes to the "internal" `amazon-ecs-local-container-endpoints` server process.

        Args:
            router (Router[RouteHandler]): the Router attached in the gateway
        """
        endpoint = cast(
            ENDPOINT,
            ProxyRewriteHandler(forward_base_url=f"http://127.0.0.1:{self.port}"),
        )

        router.add("/", host=f"{self.host_prefix}.<host>", endpoint=endpoint)
        router.add("/<path:path>", host=f"{self.host_prefix}.<host>", endpoint=endpoint)

    def on_platform_ready(self) -> None:
        """Log the extension's post-startup readiness.

        Called when LocalStack is ready and the Ready marker has been printed.
        """
        LOG.info(
            "Serving ECS container metadata endpoints at: %s",
            internal_service_url(host=f"{self.host_prefix}.{localstack_host().host}"),
        )
