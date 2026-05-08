"""
charm/src/charm.py
==================
Charmed Operator for deploying the Ubuntu Package Documentation Pipeline
worker on a Juju-managed Charmed Temporal cluster.

Purpose
-------
This charm deploys and manages the lifecycle of the Temporal worker process
(``src/main.py``) as a Juju application unit.  It integrates with:

  - The existing Charmed Temporal cluster (via the ``temporal-worker``
    Juju relation) to configure the Temporal frontend address and namespace.
  - Juju secrets or config options for injecting the Git PAT and LLM API key
    without exposing them in the charm config bundle.
  - Standard Juju hooks (``install``, ``start``, ``stop``, ``config-changed``,
    ``upgrade-charm``) to manage the worker process.

Configuration options (see ``charm/metadata.yaml``)
-----------------------------------------------------
  temporal-host        : host:port of the Temporal frontend (e.g. temporal:7233)
  temporal-namespace   : Temporal namespace (default: "default")
  task-queue           : Temporal task queue name (default: "docs-pipeline")
  llm-base-url         : Base URL of the OpenAI-compliant endpoint
  llm-model            : Model identifier to request from the LLM endpoint
  docs-repo-url        : HTTPS URL of the docs output Git repository
  max-clone-size-mb    : Maximum repository size for shallow cloning

Secrets (Juju secrets, not config)
------------------------------------
  git-pat              : Personal Access Token for docs repo commits
  llm-api-key          : API key for the LLM endpoint

Relations
---------
  temporal-worker      : Provides Temporal cluster connection details
"""

import logging
import subprocess
import sys
from pathlib import Path

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

logger = logging.getLogger(__name__)


class DocsPipelineCharm(CharmBase):
    """
    Juju charm that manages the lifecycle of the documentation pipeline
    Temporal worker.

    Event handlers
    --------------
    on.install          : Install Python dependencies from requirements.txt.
    on.start            : Start the Temporal worker process.
    on.stop             : Gracefully stop the worker process.
    on.config_changed   : Restart the worker when configuration is updated.
    on.upgrade_charm    : Re-install dependencies and restart the worker.
    """

    def __init__(self, *args):
        super().__init__(*args)

        # Register event handlers
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

    def _on_install(self, event) -> None:
        """
        Install Python dependencies when the charm is first deployed.

        Runs ``pip install -r requirements.txt`` from the charm's source
        directory.  Sets the unit to ``MaintenanceStatus`` during installation
        and ``BlockedStatus`` on failure.

        Parameters
        ----------
        event : ops.InstallEvent
            The Juju install hook event (unused directly).
        """
        raise NotImplementedError

    def _on_start(self, event) -> None:
        """
        Start the Temporal worker process.

        Launches ``python src/main.py`` as a background subprocess, injecting
        all required environment variables from charm config and Juju secrets.
        Sets the unit to ``ActiveStatus`` on success.

        Parameters
        ----------
        event : ops.StartEvent
            The Juju start hook event (unused directly).
        """
        raise NotImplementedError

    def _on_stop(self, event) -> None:
        """
        Gracefully stop the Temporal worker process.

        Sends SIGTERM to the worker process and waits for it to drain in-flight
        activities before exiting.

        Parameters
        ----------
        event : ops.StopEvent
            The Juju stop hook event (unused directly).
        """
        raise NotImplementedError

    def _on_config_changed(self, event) -> None:
        """
        Restart the worker with the updated configuration.

        Called whenever a Juju config option is changed via ``juju config``.
        Stops the current worker process and starts a new one with the updated
        environment variables.

        Parameters
        ----------
        event : ops.ConfigChangedEvent
            The Juju config-changed hook event (unused directly).
        """
        raise NotImplementedError

    def _on_upgrade_charm(self, event) -> None:
        """
        Re-install dependencies and restart the worker on charm upgrade.

        Parameters
        ----------
        event : ops.UpgradeCharmEvent
            The Juju upgrade-charm hook event (unused directly).
        """
        raise NotImplementedError

    def _build_worker_env(self) -> dict:
        """
        Assemble the environment variable dict for the worker subprocess.

        Reads Temporal connection details from charm config and resolves
        secrets (Git PAT, LLM API key) from Juju secret storage.

        Returns
        -------
        dict
            A dict of environment variable names to values, suitable for
            passing as the ``env`` argument to ``subprocess.Popen``.
        """
        raise NotImplementedError

    def _is_worker_running(self) -> bool:
        """
        Check whether the worker subprocess is currently alive.

        Returns
        -------
        bool
            ``True`` if the worker process exists and has not exited.
        """
        raise NotImplementedError


if __name__ == "__main__":
    main(DocsPipelineCharm)
