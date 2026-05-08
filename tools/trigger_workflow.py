"""
tools/trigger_workflow.py
=========================
CLI tool for manually dispatching an IngestionWorkflow to a running Temporal
cluster.

Purpose
-------
Used during local development and integration testing to push a synthetic
``PackageMetadata`` payload into the Temporal task queue without waiting for
a real binary generation system event.

Usage::

    # Trigger with minimal required arguments
    python tools/trigger_workflow.py --name snapd --version 2.63.1 \\
        --upstream-url https://github.com/canonical/snapd \\
        --install-method snap

    # Trigger with all options
    python tools/trigger_workflow.py \\
        --name lxd \\
        --version 5.21.0 \\
        --upstream-url https://github.com/canonical/lxd \\
        --install-method snap \\
        --snap-channel latest/stable \\
        --additional-context "Migration notes: see internal wiki" \\
        --temporal-host localhost:7233 \\
        --task-queue docs-pipeline \\
        --wait

The ``--wait`` flag blocks until the workflow completes and prints the result
status to stdout.
"""

import asyncio
from typing import Optional

import typer
from temporalio.client import Client

from models.package import PackageMetadata

app = typer.Typer(
    name="trigger-workflow",
    help="Manually dispatch an IngestionWorkflow to the Temporal cluster.",
)


@app.command()
def main(
    name: str = typer.Option(..., help="Package name (e.g. 'snapd')"),
    version: str = typer.Option(..., help="Package version (e.g. '2.63.1')"),
    upstream_url: str = typer.Option(..., help="HTTPS URL of upstream repository"),
    install_method: str = typer.Option(
        ..., help="Installation method: snap, deb, or both"
    ),
    snap_channel: Optional[str] = typer.Option(
        None, help="Snap Store channel (required if install_method=snap)"
    ),
    architecture: Optional[str] = typer.Option(
        None, help="Target architecture (e.g. amd64)"
    ),
    additional_context: Optional[str] = typer.Option(
        None, help="Additional context to inject into the LLM prompt"
    ),
    temporal_host: str = typer.Option(
        "localhost:7233", help="Temporal frontend host:port"
    ),
    task_queue: str = typer.Option(
        "docs-pipeline", help="Temporal task queue name"
    ),
    wait: bool = typer.Option(
        False, "--wait", help="Block until the workflow completes"
    ),
) -> None:
    """
    Build a ``PackageMetadata`` payload and dispatch it as an IngestionWorkflow.

    Parameters
    ----------
    name : str
        The canonical package name.
    version : str
        The package version string.
    upstream_url : str
        HTTPS URL of the upstream source repository.
    install_method : str
        Distribution channel: ``"snap"``, ``"deb"``, or ``"both"``.
    snap_channel : Optional[str]
        Snap Store channel; required when ``install_method`` is ``"snap"``.
    architecture : Optional[str]
        Target CPU architecture; ``None`` for architecture-independent packages.
    additional_context : Optional[str]
        Free-form extra context injected verbatim into the LLM system prompt.
    temporal_host : str
        ``host:port`` of the Temporal frontend gRPC service.
    task_queue : str
        Name of the Temporal task queue to dispatch the workflow on.
    wait : bool
        If ``True``, block until the workflow completes and print the result.
    """
    asyncio.run(
        _dispatch(
            name=name,
            version=version,
            upstream_url=upstream_url,
            install_method=install_method,
            snap_channel=snap_channel,
            architecture=architecture,
            additional_context=additional_context,
            temporal_host=temporal_host,
            task_queue=task_queue,
            wait=wait,
        )
    )


async def _dispatch(
    name: str,
    version: str,
    upstream_url: str,
    install_method: str,
    snap_channel: Optional[str],
    architecture: Optional[str],
    additional_context: Optional[str],
    temporal_host: str,
    task_queue: str,
    wait: bool,
) -> None:
    """
    Async implementation: connect to Temporal, build the payload, and start
    the IngestionWorkflow.

    This is separated from ``main()`` so it can be called directly in tests.
    """
    raise NotImplementedError


if __name__ == "__main__":
    app()
