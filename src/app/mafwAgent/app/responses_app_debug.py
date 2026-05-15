"""Debug entrypoint: returns fixed text + env diagnostics. No AOAI call."""
from __future__ import annotations

import asyncio
import os
import platform
import sys

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    TextResponse,
)

app = ResponsesAgentServerHost()


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    user_text = await context.get_input_text()
    diag = {
        "echo": user_text,
        "py": sys.version.split()[0],
        "host": platform.node(),
        "AZURE_CLIENT_ID": os.environ.get("AZURE_CLIENT_ID", "<unset>"),
        "AZURE_OPENAI_ENDPOINT": os.environ.get("AZURE_OPENAI_ENDPOINT", "<unset>"),
        "AZURE_SEARCH_ENDPOINT": os.environ.get("AZURE_SEARCH_ENDPOINT", "<unset>"),
        "IDENTITY_ENDPOINT": os.environ.get("IDENTITY_ENDPOINT", "<unset>"),
        "IDENTITY_HEADER": "<set>" if os.environ.get("IDENTITY_HEADER") else "<unset>",
        "MSI_ENDPOINT": os.environ.get("MSI_ENDPOINT", "<unset>"),
    }
    # Try to acquire a token to verify MI works
    try:
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()
        tok = cred.get_token("https://cognitiveservices.azure.com/.default")
        diag["token_ok"] = True
        diag["token_expires"] = tok.expires_on
    except Exception as exc:  # noqa: BLE001
        diag["token_ok"] = False
        diag["token_err"] = f"{type(exc).__name__}: {exc}"[:1500]

    text = "\n".join(f"{k}={v}" for k, v in diag.items())
    return TextResponse(context, request, text=text)


if __name__ == "__main__":
    app.run()
