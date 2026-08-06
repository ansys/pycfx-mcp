Configuration
=============

Configure PyCFX-MCP with command-line options and environment variables.
You can run the MCP server over STDIO or Streamable HTTP. Optional LLM
settings are used only by the ``codegen`` fallback path when deterministic CFX
recipes do not match your request.

General settings
----------------

.. list-table:: **Server command settings**
   :header-rows: 1
   :widths: 30 70

   * - Setting
     - Description
   * - ``--transport``
     - MCP transport to use. Supported values are ``stdio`` and ``http``.
       The default is ``stdio``.
   * - ``--host``
     - Host interface for HTTP transport. The default is ``127.0.0.1``.
   * - ``--port``
     - HTTP port. A value of ``0`` uses the server default of ``8000`` for HTTP
       transport.
   * - ``--backend``
     - Default backend kind until ``connect`` is called. This package ships the
       ``pycfx`` backend.
   * - ``--log-level``
     - Python logging level for the server process. The default is ``INFO``.

Model settings
--------------

Server-side LLM access is optional and limited to ``codegen``. The fallback is
provider agnostic. It can call native provider APIs through LiteLLM or a direct
OpenAI-compatible HTTP endpoint. Other tools, including ``cfx_workflow``,
``cfx_model_context``, ``validate_code``, and ``run_code``, do not call a
server-side LLM.

Quick start
~~~~~~~~~~~

Use an OpenAI key:

.. code-block:: powershell

   $env:OPENAI_API_KEY = "<your-openai-key>"
   $env:LLM_PROVIDER = "openai"
   $env:LLM_MODEL = "gpt-4o"

Use an Anthropic Claude key:

.. code-block:: powershell

   $env:ANTHROPIC_API_KEY = "<your-anthropic-key>"
   $env:LLM_PROVIDER = "anthropic"
   $env:LLM_MODEL = "claude-3-5-sonnet"

Use a Google Gemini key:

.. code-block:: powershell

   $env:GEMINI_API_KEY = "<your-gemini-key>"
   $env:LLM_PROVIDER = "gemini"
   $env:LLM_MODEL = "gemini-1.5-pro"

Use an OpenAI-compatible endpoint:

.. code-block:: powershell

   $env:LLM_ENDPOINT = "http://localhost:4000/v1"
   $env:LLM_API_KEY = "<your-key>"
   $env:LLM_MODEL = "gpt-4o"

For native provider APIs, install the ``providers`` extra once:

.. code-block:: bash

   pip install "ansys-cfx-mcp[providers]"

Full model reference
~~~~~~~~~~~~~~~~~~~~

.. list-table:: **LLM environment variables**
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``LLM_PROVIDER``
     - Explicit provider name. Supported values are ``openai``, ``azure``,
       ``anthropic``, ``gemini``, and ``compat``.
   * - ``LLM_TRANSPORT``
     - Transport override. Supported values are ``auto``, ``litellm``, and
       ``openai_compat``. The default is ``auto``.
   * - ``LLM_ENDPOINT``
     - OpenAI-compatible chat completion endpoint. When set, ``auto`` uses
       direct HTTP transport.
   * - ``LLM_API_KEY``
     - API key for direct HTTP transport or a custom provider endpoint.
   * - ``OPENAI_API_KEY``
     - API key for native OpenAI calls through LiteLLM.
   * - ``ANTHROPIC_API_KEY``
     - API key for native Anthropic Claude calls through LiteLLM.
   * - ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``
     - API key for native Google Gemini calls through LiteLLM.
   * - ``AZURE_API_KEY``
     - API key for native Azure OpenAI calls through LiteLLM.
   * - ``LLM_MODEL``
     - Model identifier. The default is ``gpt-4o-mini``.
   * - ``LLM_MAX_RETRIES``
     - Maximum retry attempts for LLM calls. The default is ``3``.
   * - ``LLM_TIMEOUT_SECONDS``
     - Request timeout in seconds. The default is ``60``.
   * - ``LLM_AUTH_STYLE``
     - Authorization header style for direct HTTP calls. Set to
       ``azure-api-key`` for endpoints that require an ``api-key`` header.
   * - ``LLM_MAX_TOKENS_PARAM``
     - Override the parameter name for the maximum token request.
   * - ``LLM_SEND_TEMPERATURE``
     - Boolean flag that controls whether ``temperature`` is sent to the model.

Transport security and network egress
-------------------------------------

.. list-table:: **Security-related settings**
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``LLM_CA_BUNDLE``
     - Path to a custom certificate authority bundle for outbound LLM HTTPS
       requests.
   * - ``SSL_CERT_FILE``
     - Standard Python certificate bundle override. Used when ``LLM_CA_BUNDLE``
       is not set.
   * - ``REQUESTS_CA_BUNDLE``
     - Requests certificate bundle override. This setting is used when ``LLM_CA_BUNDLE``
       and ``SSL_CERT_FILE`` are not set.
   * - ``LLM_TLS_INSECURE``
     - Disable TLS certificate verification for outbound LLM calls when set to
       ``true``, ``1``, ``yes``, or ``on``. Prefer a custom CA bundle instead.

Server command-line tool options
--------------------------------

Run this command to inspect supported command-line tool options for your
installed version:

.. code-block:: bash

   ansys-cfx-mcp --help

To start PyCFX-MCP over STDIO:

.. code-block:: bash

   ansys-cfx-mcp --transport stdio

To start PyCFX-MCP over HTTP on the local host interface:

.. code-block:: bash

   ansys-cfx-mcp --transport http --host 127.0.0.1 --port 8000

.. warning::

   PyCFX-MCP does not add authentication or TLS to HTTP transport. Use HTTP
   only for trusted local integrations or behind infrastructure that provides
   authentication and TLS.

Next steps
----------

- Configure an MCP client as described in :doc:`../getting_started/ide_configuration`.
- Launch your first workflow as described in :doc:`../getting_started/quick_start`.
- Review the descriptions of available tools in :doc:`tools_and_capabilities`.
