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

"""CFX leaf powered by PyCFX sessions."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable, Literal, Optional, cast
from ansys.cfx.mcp.cfx.backend import CFXBackend
from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.base import FluidsLeafMCP
from ansys.cfx.mcp.common.errors import typed_guard
from ansys.cfx.mcp.common.models import ConnectResult


class CFXMCP(FluidsLeafMCP):
    """CFX MCP leaf server implementation."""

    leaf_name = "cfx"
    default_backend_kind = "pycfx"
    component_label = "cfx"

    #: The base class asks leaves to override this with a domain-specific
    #: description; CFX never did, and benchmarking found the generic wording
    #: was the connector's ONLY stranded task - "How do I set up a rotating
    #: domain in CFX?" retrieved set_setup/get_setup instead. Deliberately
    #: avoids the bare verb "write", which is what let office's
    #: xlsx_write_cells match "Write me a haiku".
    error_remediation_description: str = (
        "Answer a how-to or troubleshooting question about CFX in prose. "
        "Use it to explain a workflow, walk through configuring a model "
        "feature such as a rotating domain or a mesh interface, or "
        "diagnose an error message and suggest a remedy. Returns a "
        "Markdown explanation for the user to read; it does not change "
        "the model."
    )

    #: The shared catalogue plus the CFX-specific toolsets. `build_toolsets()`
    #: filters by `self._exposed`, so a tool missing from here is advertised by
    #: `toolsets://definition` as if it did not exist - which is how the surface
    #: added in c74703d stayed invisible to the resource that describes it.
    #: CFX-only names live here rather than in the shared base so other leaves
    #: do not inherit them.
    _TOOLSET_CATALOGUE = {
        **{k: v for k, v in FluidsLeafMCP._TOOLSET_CATALOGUE.items() if k != "visualization"},
        "api-discovery": {
            **FluidsLeafMCP._TOOLSET_CATALOGUE["api-discovery"],
            "tools": [
                *FluidsLeafMCP._TOOLSET_CATALOGUE["api-discovery"]["tools"],
                "list_cfx_api_categories",
            ],
        },
        "cfx-session": {
            "description": "Tools for opening and closing live CFX sessions.",
            "skill": (
                "Use connect_cfx to launch CFX-Pre or attach to a running "
                "instance; it takes explicit ip/port/password or a "
                "server-information file rather than a free-form dict. "
                "Call disconnect_cfx to close every session and release "
                "the licence."
            ),
            "tools": ["connect_cfx", "disconnect_cfx"],
        },
        "cfx-setup": {
            "description": "Tools for reading and modifying the CFX case setup.",
            "skill": (
                "Call get_setup for a compact snapshot of named objects, "
                "state and solver status. Use set_setup to change a value "
                "at a CCL path, such as a domain turbulence model or a "
                "boundary condition. Use save_case to persist the case "
                "to a .cfx file. Use execute_ccl to inject raw CCL blocks "
                "directly into CFX-Pre, Solver, or Post. Use manage_expressions "
                "to list, get, set, or delete CEL expressions. Use inspect_mesh "
                "to inspect mesh topology, element counts, bounding boxes, and domains."
            ),
            "tools": [
                "get_setup",
                "set_setup",
                "save_case",
                "execute_ccl",
                "manage_expressions",
                "inspect_mesh",
            ],
        },
        "cfx-solve": {
            "description": "Tools for running and monitoring the CFX solver.",
            "skill": (
                "Use start_solve to launch CFX-Solver from a .def file with "
                "support for parallel execution, double precision, and restart files, "
                "get_solve_status to poll whether it is still running, "
                "get_convergence_status to monitor iteration residuals and domain imbalances, "
                "stop_solve to abort a run, and get_results to obtain the "
                ".res file once the run has finished."
            ),
            "tools": [
                "start_solve",
                "get_solve_status",
                "get_convergence_status",
                "stop_solve",
                "get_results",
            ],
        },
        "cfx-post": {
            "description": "Tools for quantitative extraction and visualization in CFX / CFD-Post.",
            "skill": (
                "Use evaluate_post_expression to calculate quantitative engineering metrics "
                "(massFlowAve, areaAve, force, torque, pressure drops) on boundary locators. "
                "Use screenshot to capture high-resolution viewport images, contour plots, and vector fields."
            ),
            "tools": ["evaluate_post_expression", "screenshot"],
        },
    }

    def __init__(
        self, *, expose_tools: Optional[Iterable[str]] = None, **fastmcp_kwargs: Any
    ) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        expose_tools : Optional[Iterable[str]], default: None
            Optional tool-name allow-list. When ``None``, the standard CFX tools are exposed.
        fastmcp_kwargs : Any
            Additional keyword arguments forwarded to FastMCP.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        backends: dict[str, Backend] = {"pycfx": CFXBackend()}
        super().__init__(
            backends=backends,
            expose_tools=expose_tools
            or (
                # Shared PyAnsys base tools.
                "session_status",
                "cfx_workflow",
                "cfx_model_context",
                "run_code",
                "validate_code",
                "find_api",
                "get_help",
                "error_remediation",
                # CFX-specific tools.
                "connect_cfx",
                "get_setup",
                "set_setup",
                "save_case",
                "start_solve",
                "get_solve_status",
                "stop_solve",
                "get_results",
                "disconnect_cfx",
                "list_cfx_api_categories",
                "evaluate_post_expression",
                "get_convergence_status",
                "execute_ccl",
                "manage_expressions",
                "inspect_mesh",
                "screenshot",
            ),
            **fastmcp_kwargs,
        )

    def _register_tools(self) -> None:
        """Register MCP tools exposed by the leaf server.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        super()._register_tools()
        if "cfx_workflow" in self._exposed:
            self._tool_cfx_workflow()
        if "cfx_model_context" in self._exposed:
            self._tool_cfx_model_context()
        # CFX manifest tools
        if "connect_cfx" in self._exposed:
            self._tool_connect_cfx()
        if "get_setup" in self._exposed:
            self._tool_get_setup()
        if "set_setup" in self._exposed:
            self._tool_set_setup()
        if "save_case" in self._exposed:
            self._tool_save_case()
        if "start_solve" in self._exposed:
            self._tool_start_solve()
        if "get_solve_status" in self._exposed:
            self._tool_get_solve_status()
        if "stop_solve" in self._exposed:
            self._tool_stop_solve()
        if "get_results" in self._exposed:
            self._tool_get_results()
        if "disconnect_cfx" in self._exposed:
            self._tool_disconnect_cfx()
        if "get_version" in self._exposed:
            self._tool_get_version()
        if "list_cfx_api_categories" in self._exposed:
            self._tool_list_cfx_api_categories()
        if "search_cfx_api" in self._exposed:
            self._tool_search_cfx_api()
        if "query_cfx_registry" in self._exposed:
            self._tool_query_cfx_registry()
        if "evaluate_post_expression" in self._exposed:
            self._tool_evaluate_post_expression()
        if "get_convergence_status" in self._exposed:
            self._tool_get_convergence_status()
        if "execute_ccl" in self._exposed:
            self._tool_execute_ccl()
        if "manage_expressions" in self._exposed:
            self._tool_manage_expressions()
        if "inspect_mesh" in self._exposed:
            self._tool_inspect_mesh()

    def _tool_cfx_workflow(self) -> None:
        """Register the ``cfx_workflow`` MCP tool for lifecycle actions.

        Returns
        -------
        None
            No value is returned. The tool is added to the FastMCP server.
        """

        @self.tool(
            name="cfx_workflow",
            description=(
                "Run one focused CFX lifecycle or artifact action. "
                "Actions and parameter mapping:\n"
                "- 'start_pre': params={'case_file_name': str, 'product_version': str, 'ui_mode': str}\n"
                "- 'import_mesh': params={'path': str} (or 'mesh_file')\n"
                "- 'write_def': params={'path': str} (or 'def_file')\n"
                "- 'start_solver': params={'def_file': str, 'partitions': int, 'double_precision': bool, ...}\n"
                "- 'wait_solver': params={'interval': int, 'timeout': int}\n"
                "- 'get_results_file': params={}\n"
                "- 'open_post': params={'results_file': str}\n"
                "- 'status': params={}\n"
                "- 'convergence': params={'max_history': int}\n"
                "- 'evaluate_expression': params={'expression': str}\n"
                "- 'inspect_mesh': params={}\n"
                "- 'execute_ccl': params={'ccl': str, 'session_type': 'auto'|'pre'|'solver'|'post'}\n"
                "- 'manage_expressions': params={'action': 'list'|'get'|'set'|'delete', 'name': str, 'definition': str}"
            ),
        )
        @typed_guard
        async def cfx_workflow(
            action: Literal[
                "start_pre",
                "import_mesh",
                "write_def",
                "start_solver",
                "wait_solver",
                "get_results_file",
                "open_post",
                "status",
                "convergence",
                "evaluate_expression",
                "inspect_mesh",
                "execute_ccl",
                "manage_expressions",
            ],
            params: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Run a focused CFX lifecycle or artifact action.

            Parameters
            ----------
            action : str
                Component-management action to apply.
            params : dict[str, Any] | None, default: None
                Action-specific parameters such as file paths, launch options, or timeout
                settings.

            Returns
            -------
            dict[str, Any]
                Status payload returned by the CFX workflow backend.
            """
            workflow = cast(
                Callable[..., Awaitable[dict[str, Any]]] | None,
                getattr(self.backend, "cfx_workflow", None),
            )
            if not callable(workflow):
                return {"status": "error", "message": "CFX workflow is unavailable."}
            return await workflow(action=action, params=params or {})

    def _tool_cfx_model_context(self) -> None:
        """Register the ``cfx_model_context`` MCP tool for compact model queries.

        Returns
        -------
        None
            No value is returned. The tool is added to the FastMCP server.
        """

        @self.tool(
            name="cfx_model_context",
            description=(
                "Return a targeted, compact CFX model context slice. "
                "Actions and parameter mapping:\n"
                "- 'summary': overview of active setup\n"
                "- 'list_named_objects': lists domains/boundaries\n"
                "- 'find_named_object': params={'name': str}\n"
                "- 'select_named_objects': params={'names': list[str]}\n"
                "- 'state': params={'paths': list[str]}\n"
                "- 'api_help': params={'path': str}\n"
                "- 'find_api': params={'query': str, 'kinds': list[str], 'under': str}\n"
                "- 'allowed_values': params={'paths': list[str]}\n"
                "- 'targeted_context': params={'paths_to_check': list[str], 'named_object_types': list[str]}"
            ),
        )
        @typed_guard
        async def cfx_model_context(
            action: Literal[
                "summary",
                "list_named_objects",
                "find_named_object",
                "select_named_objects",
                "state",
                "api_help",
                "find_api",
                "allowed_values",
                "targeted_context",
            ] = "summary",
            params: dict[str, Any] | None = None,
            max_items: int = 20,
        ) -> dict[str, Any]:
            """Return a targeted slice of active CFX model context.

            Parameters
            ----------
            action : str, default: 'summary'
                Component-management action to apply.
            params : dict[str, Any] | None, default: None
                Query-specific options such as paths, object names, or search text.
            max_items : int, default: 20
                Maximum number of context items to include in the response.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            context = cast(
                Callable[..., Awaitable[dict[str, Any]]] | None,
                getattr(self.backend, "cfx_model_context", None),
            )
            if not callable(context):
                return {"status": "error", "message": "CFX model context is unavailable."}
            return await context(
                action=action,
                params=params or {},
                max_items=max_items,
            )

    # ---- CFX manifest tools -----------------------------------------------

    def _tool_connect_cfx(self) -> None:
        """Register the ``connect_cfx`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="connect_cfx",
            description=(
                "Connect to a CFX session. Mode precedence: 'auto' (default) attempts attach "
                "if ANSYS_MCP_PORT/ANSYS_MCP_HOST or attach parameters (ip, port, server_info_file) "
                "are set; otherwise launches a local session via from_install. Explicit 'launch' or "
                "'attach' can be forced. Pass case_file_name/product_version for launch."
            ),
        )
        @typed_guard
        async def connect_cfx(
            mode: str = "auto",
            ip: Optional[str] = None,
            port: Optional[int] = None,
            password: Optional[str] = None,
            server_info_file: Optional[str] = None,
            case_file_name: Optional[str] = None,
            product_version: Optional[str] = None,
            solver_input_file: Optional[str] = None,
            results_file: Optional[str] = None,
            ui_mode: Optional[str] = None,
            start_timeout: int = 60,
        ) -> ConnectResult:
            """Connect to a CFX session.

            Parameters
            ----------
            mode : str, default: ``'auto'``
                Connection mode: ``'auto'``, ``'launch'``, or ``'attach'``.
            ip : Optional[str], default: None
                IP address for attach mode.
            port : Optional[int], default: None
                Port for attach mode.
            password : Optional[str], default: None
                Password for attach mode.
            server_info_file : Optional[str], default: None
                Server info file for attach mode.
            case_file_name : Optional[str], default: None
                Case file to open on launch.
            product_version : Optional[str], default: None
                Ansys product version.
            solver_input_file : Optional[str], default: None
                Solver input .def file for direct solver launch.
            results_file : Optional[str], default: None
                Results .res file for post-processing.
            ui_mode : Optional[str], default: None
                CFX UI mode.
            start_timeout : int, default: 60
                Timeout for session launch.

            Returns
            -------
            ConnectResult
                Connection result describing the selected backend session.
            """
            kwargs: dict[str, Any] = {}
            if ip is not None:
                kwargs["ip"] = ip
            if port is not None:
                kwargs["port"] = port
            if password is not None:
                kwargs["password"] = password
            if server_info_file is not None:
                kwargs["server_info_file"] = server_info_file
            if case_file_name is not None:
                kwargs["case_file_name"] = case_file_name
            if product_version is not None:
                kwargs["product_version"] = product_version
            if solver_input_file is not None:
                kwargs["solver_input_file"] = solver_input_file
            if results_file is not None:
                kwargs["results_file"] = results_file
            if ui_mode is not None:
                kwargs["ui_mode"] = ui_mode
            kwargs["start_timeout"] = start_timeout
            result = await self.backend.connect(mode=mode, **kwargs)
            if result.status == "ok":
                kind = self.default_backend_kind or next(iter(self._backends))
                self._active_kind = kind
            return result

    def _tool_get_setup(self) -> None:
        """Register the ``get_setup`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_setup",
            description=(
                "Return a summary of the current CFX setup including named objects, state, and "
                "solver status. @precondition: Active CFX session connected via connect_cfx."
            ),
        )
        @typed_guard
        async def get_setup() -> dict[str, Any]:
            """Return a summary of the current CFX setup.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            return await self.backend.summarize_setup()

    def _tool_set_setup(self) -> None:
        """Register the ``set_setup`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="set_setup",
            description=(
                "Set a value on a CFX setup path (e.g. domain turbulence model, boundary condition). "
                "Physical quantities with units must be specified as CCL strings with bracketed units "
                "(e.g. '10 [m s^-1]', '101325 [Pa]', '25 [C]', '1.2 [kg m^-3]'). "
                "@precondition: Active CFX-Pre session connected via connect_cfx."
            ),
        )
        @typed_guard
        async def set_setup(
            path: str,
            value: Any,
        ) -> dict[str, Any]:
            """Set a value on a CFX setup path.

            Parameters
            ----------
            path : str
                Dotted CFX path to set.
            value : Any
                Value to assign.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.set_state(path=path, value=value)

    def _tool_save_case(self) -> None:
        """Register the ``save_case`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="save_case",
            description=(
                "Save the current CFX-Pre case to a .cfx file. "
                "@precondition: Active CFX-Pre session with a loaded or configured case."
            ),
        )
        @typed_guard
        async def save_case(path: str) -> dict[str, Any]:
            """Save the current CFX case.

            Parameters
            ----------
            path : str
                Destination .cfx file path.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.save_case(path=path)

    def _tool_start_solve(self) -> None:
        """Register the ``start_solve`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="start_solve",
            description=(
                "Start the CFX-Solver run from a .def input file with support for parallel "
                "execution partitions, double precision, and restart initial conditions. "
                "@precondition: CFX solver input .def file generated or specified."
            ),
        )
        @typed_guard
        async def start_solve(
            def_file: str,
            partitions: int = 1,
            parallel_mode: str = "local",
            double_precision: bool = False,
            initial_file: Optional[str] = None,
            additional_arguments: str = "",
            product_version: Optional[str] = None,
            cleanup_on_exit: bool = True,
        ) -> dict[str, Any]:
            """Start the CFX-Solver run.

            Parameters
            ----------
            def_file : str
                Path to the CFX solver input .def file.
            partitions : int, default: 1
                Number of parallel solver partitions (processes/cores). Default 1 runs serially.
            parallel_mode : str, default: 'local'
                CFX parallel execution mode ('local', 'distributed', etc.).
            double_precision : bool, default: False
                Run solver in double precision mode (-double). Recommended for conjugate heat transfer or small pressure gradients.
            initial_file : Optional[str], default: None
                Path to a previous results (.res) or backup (.bak) file for continuation restart (-initial).
            additional_arguments : str, default: ''
                Additional custom command-line arguments to pass directly to cfx5solve.
            product_version : Optional[str], default: None
                Ansys product version to use.
            cleanup_on_exit : bool, default: True
                Whether to clean up the solver process on exit.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.start_solve(
                def_file=def_file,
                partitions=partitions,
                parallel_mode=parallel_mode,
                double_precision=double_precision,
                initial_file=initial_file,
                additional_arguments=additional_arguments,
                product_version=product_version,
                cleanup_on_exit=cleanup_on_exit,
            )

    def _tool_get_solve_status(self) -> None:
        """Register the ``get_solve_status`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_solve_status",
            description="Return CFX-Solver run status including whether it is running, results file, and session info.",
        )
        @typed_guard
        async def get_solve_status() -> dict[str, Any]:
            """Return CFX-Solver run status.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            return await self.backend.solver_status()

    def _tool_stop_solve(self) -> None:
        """Register the ``stop_solve`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="stop_solve",
            description=(
                "Stop the active CFX-Solver run. "
                "@precondition: Active running CFX-Solver session."
            ),
        )
        @typed_guard
        async def stop_solve(wait: bool = True) -> dict[str, Any]:
            """Stop the active CFX-Solver run.

            Parameters
            ----------
            wait : bool, default: True
                Whether to wait until the solver acknowledges the stop.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.stop_solve(wait=wait)

    def _tool_get_results(self) -> None:
        """Register the ``get_results`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_results",
            description=(
                "Return the .res results file path from the active solver session. "
                "@precondition: Solved CFX case or loaded .res results file."
            ),
        )
        @typed_guard
        async def get_results() -> dict[str, Any]:
            """Return the results file path.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.get_results()

    def _tool_disconnect_cfx(self) -> None:
        """Register the ``disconnect_cfx`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="disconnect_cfx",
            description="Disconnect all active CFX sessions and release resources.",
        )
        @typed_guard
        async def disconnect_cfx() -> dict[str, Any]:
            """Disconnect all CFX sessions.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            if self._active_kind is not None:
                await self.backend.disconnect()
                self._active_kind = None
            return {"status": "ok", "message": "All CFX sessions disconnected."}

    def _tool_get_version(self) -> None:
        """Register the ``get_version`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_version",
            description="Return the Ansys CFX / PyCFX version information.",
        )
        @typed_guard
        async def get_version() -> dict[str, Any]:
            """Return CFX version information.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.get_version()

    def _tool_list_cfx_api_categories(self) -> None:
        """Register the ``list_cfx_api_categories`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="list_cfx_api_categories",
            description="List the available CFX API categories (Pre, Solver, Post, etc.) and their descriptions.",
        )
        @typed_guard
        async def list_cfx_api_categories() -> dict[str, Any]:
            """List CFX API categories.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.list_cfx_api_categories()

    def _tool_search_cfx_api(self) -> None:
        """Register the ``search_cfx_api`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="search_cfx_api",
            description="Search the CFX API catalog by keyword to find matching paths, kinds, and descriptions.",
        )
        @typed_guard
        async def search_cfx_api(
            query: str,
            top_k: int = 10,
            kinds: Optional[list[str]] = None,
            under: Optional[str] = None,
        ) -> list[dict[str, Any]]:
            """Search the CFX API catalog.

            Parameters
            ----------
            query : str
                Search query for ranking CFX API or object matches.
            top_k : int, default: 10
                Maximum number of results to return.
            kinds : Optional[list[str]], default: None
                Optional kind filter.
            under : Optional[str], default: None
                Optional CFX path prefix filter.

            Returns
            -------
            list[dict[str, Any]]
                List of matching API catalog entries.
            """
            return await self.backend.find_api(query=query, top_k=top_k, kinds=kinds, under=under)

    def _tool_query_cfx_registry(self) -> None:
        """Register the ``query_cfx_registry`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="query_cfx_registry",
            description=(
                "Query the CFX API registry for detailed information about a specific path, "
                "including allowed values, active status, and help text."
            ),
        )
        @typed_guard
        async def query_cfx_registry(
            path: str,
        ) -> dict[str, Any]:
            """Query the CFX API registry for a specific path.

            Parameters
            ----------
            path : str
                CFX path to query.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            return await self.backend.get_help(path=path)

    def _tool_evaluate_post_expression(self) -> None:
        """Register the ``evaluate_post_expression`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="evaluate_post_expression",
            description=(
                "Evaluate a quantitative CEL expression in CFX / CFD-Post on the loaded results. "
                "Supports standard CFD-Post quantitative functions such as "
                "'massFlowAve(Total Pressure)@inlet', 'areaAve(Pressure)@outlet', "
                "'force_z()@blade', 'torque_z()@rotor', and custom arithmetic expressions. "
                "@precondition: Active CFX-Post session with loaded .res or results file."
            ),
        )
        @typed_guard
        async def evaluate_post_expression(
            expression: str,
        ) -> dict[str, Any]:
            """Evaluate a CEL expression in CFX-Post.

            Parameters
            ----------
            expression : str
                The CEL expression to evaluate (e.g. 'massFlowAve(Total Pressure)@inlet').

            Returns
            -------
            dict[str, Any]
                Structured response payload containing the evaluated numerical value, units, and status.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.evaluate_post_expression(expression=expression)

    def _tool_get_convergence_status(self) -> None:
        """Register the ``get_convergence_status`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_convergence_status",
            description=(
                "Parse and return live CFX-Solver iteration progress, residual histories "
                "(RMS and Max for Momentum, Continuity, Energy, Turbulence), and domain "
                "conservation imbalances from the solver .out file. "
                "@precondition: Active or completed CFX-Solver run with an output file."
            ),
        )
        @typed_guard
        async def get_convergence_status(
            max_history: int = 10,
        ) -> dict[str, Any]:
            """Get live CFX-Solver convergence status and residual history.

            Parameters
            ----------
            max_history : int, default: 10
                Maximum number of recent outer loop iterations to return in the residual history.

            Returns
            -------
            dict[str, Any]
                Structured response payload with current iteration, residuals, imbalances, and convergence flag.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.get_convergence_status(max_history=max_history)

    def _tool_execute_ccl(self) -> None:
        """Register the ``execute_ccl`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="execute_ccl",
            description=(
                "Inject and execute a raw multiline CCL (CFX Command Language) statement "
                "or block directly into CFX-Pre, Solver, or Post. Allows power users to set "
                "complex physical models, boundary definitions, materials, solver parameters, "
                "or post-processing objects. "
                "@precondition: Active CFX session (Pre, Solver, or Post)."
            ),
        )
        @typed_guard
        async def execute_ccl(
            ccl: str,
            session_type: Literal["auto", "pre", "solver", "post"] = "auto",
        ) -> dict[str, Any]:
            """Execute a raw CCL statement or block.

            Parameters
            ----------
            ccl : str
                The multiline CCL command block to execute.
            session_type : Literal['auto', 'pre', 'solver', 'post'], default: 'auto'
                Target session type for CCL execution. 'auto' selects in order: Pre -> Post -> Solver.

            Returns
            -------
            dict[str, Any]
                Structured response payload indicating success or execution error.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.execute_ccl(ccl=ccl, session_type=session_type)

    def _tool_manage_expressions(self) -> None:
        """Register the ``manage_expressions`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="manage_expressions",
            description=(
                "Manage CFX Expression Language (CEL) expressions in CFX-Pre or Post. "
                "Supports listing all defined expressions, getting a specific expression definition, "
                "creating or updating an expression with syntax/unit validation, and deleting expressions. "
                "@precondition: Active CFX-Pre or CFX-Post session."
            ),
        )
        @typed_guard
        async def manage_expressions(
            action: Literal["list", "get", "set", "delete"] = "list",
            name: Optional[str] = None,
            definition: Optional[str] = None,
            session_type: Literal["auto", "pre", "post"] = "auto",
        ) -> dict[str, Any]:
            """Manage CEL expressions.

            Parameters
            ----------
            action : Literal['list', 'get', 'set', 'delete'], default: 'list'
                Expression operation to perform.
            name : Optional[str], default: None
                Name of the CEL expression (required for 'get', 'set', 'delete').
            definition : Optional[str], default: None
                CEL expression formula/definition with units (e.g. '10.5 [m s^-1]' or 'Total Pressure * 2') (required for 'set').
            session_type : Literal['auto', 'pre', 'post'], default: 'auto'
                Session type to manage expressions in.

            Returns
            -------
            dict[str, Any]
                Structured response payload with expression list or operation result.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.manage_expressions(
                action=action,
                name=name,
                definition=definition,
                session_type=session_type,
            )

    def _tool_inspect_mesh(self) -> None:
        """Register the ``inspect_mesh`` MCP tool.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="inspect_mesh",
            description=(
                "Inspect mesh topology, element counts (nodes, elements), bounding box dimensions, "
                "mesh assembly status, and domain association in the active CFX-Pre case. "
                "@precondition: Active CFX-Pre session with loaded mesh or case."
            ),
        )
        @typed_guard
        async def inspect_mesh() -> dict[str, Any]:
            """Inspect mesh topology and metrics.

            Returns
            -------
            dict[str, Any]
                Structured response payload containing mesh metrics, node/element counts, and domain mapping.
            """
            backend = cast(CFXBackend, self.backend)
            return await backend.inspect_mesh()


__all__ = ["CFXMCP"]
