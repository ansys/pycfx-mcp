# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MCP-side session wrapper for a PyCFX Solver session."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

_LOG = logging.getLogger(__name__)


def parse_cfx_out_file(out_path: Path | str, max_history: int = 10) -> dict[str, Any]:
    """Parse a CFX-Solver .out text file for convergence residuals and imbalances.

    Parameters
    ----------
    out_path : Path | str
        Path to the solver .out text file.
    max_history : int, default: 10
        Maximum number of recent iteration records to retain.

    Returns
    -------
    dict[str, Any]
        Parsed convergence status with latest iteration, residuals, and imbalances.
    """
    p = Path(out_path)
    if not p.is_file():
        return {"status": "error", "message": f"Solver output file not found: {out_path}"}

    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return {"status": "error", "message": f"Failed reading {out_path}: {exc}"}

    iteration = 0
    history: list[dict[str, Any]] = []
    current_iter_residuals: dict[str, dict[str, float]] = {}
    current_imbalances: dict[str, float] = {}
    converged = False
    in_residual_table = False

    iter_re = re.compile(r"(?:Outer Loop Iteration|TIMESTEP)\s*=\s*(\d+)", re.IGNORECASE)
    res_row_re = re.compile(
        r"\|\s*([A-Za-z0-9\-_]+)\s*\|\s*[\d\.\+\-Ee]*\s*\|\s*([\d\.\+\-Ee]+)\s*\|\s*([\d\.\+\-Ee]+)\s*\|[^\|]*\|\s*([\d\.\+\-Ee]*)\s*%?\s*\|"
    )

    for line in lines:
        if "Solving completed normally" in line:
            converged = True
        m_iter = iter_re.search(line)
        if m_iter:
            if current_iter_residuals:
                history.append(
                    {
                        "iteration": iteration,
                        "residuals": current_iter_residuals,
                        "imbalances": current_imbalances,
                    }
                )
                current_iter_residuals = {}
                current_imbalances = {}
            iteration = int(m_iter.group(1))
            in_residual_table = False
            continue

        if "+------------+------+" in line or "|  Equation  |" in line:
            in_residual_table = True
            continue

        if in_residual_table and line.startswith("|"):
            m_res = res_row_re.search(line)
            if m_res:
                eq = m_res.group(1).strip()
                try:
                    rms = float(m_res.group(2))
                    mx = float(m_res.group(3))
                    current_iter_residuals[eq] = {"rms": rms, "max": mx}
                    if m_res.group(4) and m_res.group(4).strip():
                        current_imbalances[eq] = float(m_res.group(4).strip())
                except ValueError:
                    pass

    if current_iter_residuals:
        history.append(
            {
                "iteration": iteration,
                "residuals": current_iter_residuals,
                "imbalances": current_imbalances,
            }
        )

    latest_residuals = history[-1]["residuals"] if history else {}
    latest_imbalances = history[-1]["imbalances"] if history else {}

    return {
        "status": "ok",
        "iteration": iteration,
        "converged": converged,
        "residuals": latest_residuals,
        "imbalances": latest_imbalances,
        "history": history[-max_history:] if max_history > 0 else history,
        "out_file": str(p),
    }


class SolverSession:
    """Wrapper for a live PyCFX Solver session.

    Consumes a DEF file from CFX-Pre and produces an RES results file
    for CFD-Post.

    .. note::
        The CFX Solver does not support IP address/port/password attachment.
        It can only be launched from a DEF file with ``from_install()``.
    """

    def __init__(
        self,
        session: Any,
        *,
        mode: str = "launch",
        solver_input_file: str | None = None,
        partitions: int = 1,
        parallel_mode: str = "local",
        double_precision: bool = False,
        initial_file: str | None = None,
    ) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        session : Any
            PyCFX session or wrapper object managed by this helper.
        mode : str, default: ``'launch'``
            Mode that controls how the operation runs.
        solver_input_file : str | None, default: None
            CFX DEF file path associated with the solver run.
        partitions : int, default: 1
            Number of parallel partitions/cores allocated to the run.
        parallel_mode : str, default: ``'local'``
            Parallel execution mode ('local', 'distributed', 'serial').
        double_precision : bool, default: False
            Whether the solver was started with double precision.
        initial_file : str | None, default: None
            Checkpoint or initial results file used for continuation.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        self._session = session
        self.mode = mode
        self.solver_input_file = solver_input_file
        self.partitions = partitions
        self.parallel_mode = parallel_mode
        self.double_precision = double_precision
        self.initial_file = initial_file

    @classmethod
    def launch(
        cls,
        solver_input_file: str,
        *,
        product_version: str | None = None,
        cleanup_on_exit: bool = True,
        partitions: int = 1,
        parallel_mode: str = "local",
        double_precision: bool = False,
        initial_file: str | None = None,
        additional_arguments: str = "",
        **extra_kwargs: Any,
    ) -> "SolverSession":
        """Launch the CFX-Solver from a solver input file and wrap the session.

        Parameters
        ----------
        solver_input_file : str
            CFX DEF file for starting the solver session.
        product_version : str | None, default: None
            Optional Ansys product version to launch.
        cleanup_on_exit : bool, default: ``True``
            Whether PyCFX should clean up the launched process on exit.
        partitions : int, default: 1
            Number of parallel partitions to use.
        parallel_mode : str, default: 'local'
            Parallel execution mode.
        double_precision : bool, default: False
            Whether to run the solver in double precision mode.
        initial_file : str | None, default: None
            Path to an initial or restart .res file.
        additional_arguments : str, default: ''
            Additional command-line arguments passed to cfx5solve.

        Returns
        -------
        'SolverSession'
            Session wrapper connected to the requested CFX process.
        """
        import ansys.cfx.core as pycfx

        args_list: list[str] = []
        if partitions > 1:
            if parallel_mode == "local":
                args_list.append(f"-par-local -part {int(partitions)}")
            elif parallel_mode == "distributed":
                args_list.append(f"-par-dist -part {int(partitions)}")
            else:
                args_list.append(f"-part {int(partitions)}")
        if double_precision:
            args_list.append("-double")
        if initial_file:
            args_list.append(f'-initial "{initial_file}"')
        if additional_arguments:
            args_list.append(str(additional_arguments).strip())

        combined_additional = " ".join(args_list).strip()
        kwargs: dict[str, Any] = {
            "solver_input_file_name": solver_input_file,
            "cleanup_on_exit": cleanup_on_exit,
            "additional_arguments": combined_additional,
        }
        if product_version is not None:
            kwargs["product_version"] = product_version
        _LOG.info(
            "Launching solver with input: %s (additional_arguments=%s)",
            solver_input_file,
            combined_additional,
        )
        pysolve = pycfx.Solver.from_install(**kwargs)
        return cls(
            pysolve,
            mode="launch",
            solver_input_file=solver_input_file,
            partitions=partitions,
            parallel_mode=parallel_mode,
            double_precision=double_precision,
            initial_file=initial_file,
        )

    @property
    def raw(self) -> Any:
        """Underlying PyCFX CFX-Solver session object.

        Returns
        -------
        Any
            Raw PyCFX solver session used by generated code and backend helpers.
        """
        return self._session

    def start_run(self) -> None:
        """Start the solver run for the wrapped CFX-Solver session.

        Returns
        -------
        None
            No value is returned. The solver session begins running asynchronously.
        """
        _LOG.info("Starting solver run...")
        self._session.solution.start_run()

    def stop_run(self, wait: bool = True) -> None:
        """Stop the active CFX-Solver run.

        Parameters
        ----------
        wait : bool, default: True
            Whether to wait until the solver acknowledges the stop request.

        Returns
        -------
        None
            No value is returned. The solver run is requested to stop.
        """
        _LOG.info("Stopping solver run (wait=%s)...", wait)
        self._session.solution.stop_run(wait_for_run=wait)

    def wait_for_run(self, interval: int = 10, timeout: int = 86400) -> None:
        """Wait for the active CFX-Solver run to finish.

        Parameters
        ----------
        interval : int, default: 10
            Polling interval in seconds while waiting for completion.
        timeout : int, default: 86400
            Maximum number of seconds to wait for the solver.

        Returns
        -------
        None
            No value is returned. The call blocks until completion or timeout.
        """
        _LOG.info("Waiting for solver run (timeout=%ds)...", timeout)
        self._session.solution.wait_for_run(interval=interval, timeout=timeout)

    def get_results_file_name(self) -> str | None:
        """Return the results file produced by the wrapped solver session.

        Returns
        -------
        str | None
            Results-file path reported by PyCFX, or ``None`` if no result is available yet.
        """
        result = self._session.solution.get_results_file_name()
        return str(result) if result is not None else None

    def is_running(self) -> bool:
        """Check whether the wrapped CFX-Solver run is still running.

        Returns
        -------
        bool
            Whether the wrapped solver run is still active.
        """
        return bool(self._session.solution.is_running())

    def execute_ccl(self, command: str) -> None:
        """Execute a CCL command on the wrapped CFX-Solver session.

        Parameters
        ----------
        command : str
            CCL text or command to process.
        """
        if hasattr(self._session, "execute_ccl"):
            self._session.execute_ccl(command)

    def get_out_file_path(self) -> Path | None:
        """Locate the solver .out text file for the active run.

        Returns
        -------
        Path | None
            Path to the latest .out file, or None if none found.
        """
        candidates: list[Path] = []
        if self.solver_input_file:
            p = Path(self.solver_input_file)
            stem = p.stem
            parent = p.parent
            if parent.is_dir():
                candidates.extend(parent.glob(f"{stem}*.out"))
                candidates.extend(parent.glob(f"{stem}*.dir/*.out"))
        # Also check current working directory
        candidates.extend(Path(".").glob("*.out"))

        existing = [c for c in candidates if c.is_file()]
        if existing:
            existing.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return existing[0]
        return None

    def get_convergence_status(self, max_history: int = 10) -> dict[str, Any]:
        """Return current convergence residuals and imbalances from the solver output.

        Parameters
        ----------
        max_history : int, default: 10
            Maximum number of iteration history items to return.

        Returns
        -------
        dict[str, Any]
            Structured convergence status.
        """
        out_path = self.get_out_file_path()
        if out_path and out_path.is_file():
            parsed = parse_cfx_out_file(out_path, max_history=max_history)
            parsed["running"] = self.is_running()
            parsed["solver_input_file"] = self.solver_input_file
            parsed["partitions"] = self.partitions
            parsed["double_precision"] = self.double_precision
            return parsed

        return {
            "status": "ok",
            "running": self.is_running(),
            "iteration": 0,
            "converged": False,
            "residuals": {},
            "imbalances": {},
            "history": [],
            "solver_input_file": self.solver_input_file,
            "message": "Solver session active, output file not yet available.",
        }

    def exit(self) -> None:
        """Exit the wrapped CFX session and release its resources.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        if self._session:
            self._session.exit()
            self._session = None

    @property
    def is_active(self) -> bool:
        """Check whether the wrapped CFX session still appears active.

        Returns
        -------
        bool
            Whether the wrapped session appears to still be usable.
        """
        return self._session is not None
