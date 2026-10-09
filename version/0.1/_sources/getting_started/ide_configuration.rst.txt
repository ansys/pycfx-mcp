IDE and client configuration
============================

You can launch PyCFX-MCP from any MCP-compatible client that supports STDIO or
Streamable HTTP servers. Use STDIO for local IDE integrations because the
client owns the server process lifecycle.

Claude Code
-----------

For Claude Code, register the STDIO server with the package command:

.. code-block:: powershell

    claude mcp add --transport stdio pycfx -- ansys-cfx-mcp

To run directly from the source repository with uvx:

.. code-block:: powershell

    claude mcp add --transport stdio pycfx -- uvx --from git+https://github.com/ansys/pycfx-mcp ansys-cfx-mcp

For a local Windows checkout, use the virtual environment entry point:

.. code-block:: powershell

    claude mcp add --transport stdio pycfx -- .venv/Scripts/ansys-cfx-mcp.exe

Visual Studio Code
------------------

For Visual Studio Code MCP support, add PyCFX-MCP to the ``.vscode/mcp.json`` file.
For an installed package, use the console command:

.. code-block:: json

    {
       "servers": {
          "pycfx": {
             "type": "stdio",
             "command": "ansys-cfx-mcp"
          }
       }
    }

For a local Windows checkout, point Visual Studio Code to the virtual
environment entry point:

.. code-block:: json

    {
       "servers": {
          "pycfx": {
             "type": "stdio",
             "command": ".venv/Scripts/ansys-cfx-mcp.exe"
          }
       }
    }

Claude Desktop
--------------

For Claude Desktop, add the server under ``mcpServers`` in the Claude Desktop
configuration file:

.. code-block:: json

    {
       "mcpServers": {
          "pycfx": {
             "command": "ansys-cfx-mcp"
          }
       }
    }

For a local Windows checkout, use the virtual environment executable path:

.. code-block:: json

    {
       "mcpServers": {
          "pycfx": {
             "command": ".venv/Scripts/ansys-cfx-mcp.exe"
          }
       }
    }

Cursor
------

Cursor supports MCP server entries similar to Visual Studio Code. Add
PyCFX-MCP as a STDIO server:

.. code-block:: json

    {
       "mcpServers": {
          "pycfx": {
             "command": "ansys-cfx-mcp"
          }
       }
    }

For a local checkout, set ``command`` to the virtual environment executable
and then restart Cursor.

Environment variables
---------------------

Client-launched STDIO servers inherit the environment from the client process.
Set provider keys and LLM routing variables before you launch the client when
you want optional ``codegen`` LLM fallback.

.. list-table:: **Common environment variables**
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``OPENAI_API_KEY``
     - API key for native OpenAI model calls through the ``providers`` extra.
   * - ``ANTHROPIC_API_KEY``
     - API key for native Anthropic Claude model calls through the ``providers`` extra.
   * - ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``
     - API key for native Google Gemini model calls through the ``providers`` extra.
   * - ``AZURE_API_KEY``
     - API key for Azure OpenAI model calls through the providers extra.
   * - ``LLM_PROVIDER``
     - Explicit provider name, such as ``openai``, ``azure``, ``anthropic``, ``gemini``, or ``compat``.
   * - ``LLM_MODEL``
     - Model identifier, such as ``gpt-4o``, ``claude-3-5-sonnet``, or ``gemini-1.5-pro``. The default is ``gpt-4o-mini``.
   * - ``LLM_ENDPOINT``
     - OpenAI-compatible endpoint URL for direct HTTP transport.
   * - ``LLM_API_KEY``
     - API key for ``LLM_ENDPOINT`` direct HTTP transport.

For the full reference, see :doc:`../user_guide/configuration`.

HTTP transport
--------------

Use STDIO for most local client integrations. For Streamable HTTP transport, start PyCFX-MCP
yourself and configure your client to use the local endpoint:

.. code-block:: powershell

    ansys-cfx-mcp --transport http --host 127.0.0.1 --port 8000

.. warning::

    HTTP transport is intended for trusted local integrations. Put it behind
    authentication and TLS before using it across a network boundary.

Toolset discovery
-----------------

PyCFX-MCP exposes a ``toolsets://definition`` resource for clients or
conductors that discover related tool groups. The default CFX toolsets group
connection management, CFX workflow routing, CFX model context, code
generation, and code execution.

Next steps
----------

- Launch PyCFX-MCP and connect to CFX as described in :doc:`quick_start`.
- Review the tool behavior described in :doc:`../user_guide/tools_and_capabilities`.
- Configure provider and transport settings as described in :doc:`../user_guide/configuration`.
