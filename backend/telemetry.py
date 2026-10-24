"""Tracing for the agent desk: OpenTelemetry, exported to Azure Application Insights.

Microsoft Agent Framework already emits a span for every workflow run, executor step, agent run, model call
and tool call (the OpenTelemetry GenAI conventions), and agents.py adds one span per pipeline with its outcome.
With APPLICATIONINSIGHTS_CONNECTION_STRING set, they all go to Application Insights, where the Foundry
project's Tracing page and Application Insights' transaction search show every run end to end: which agents
ran, how long each model call took, the tokens used, which tools were called and what the fact-checker decided.
Without it nothing is exported and nothing changes.
"""
import logging
import os

log = logging.getLogger("secondtouch")


def setup():
    """Send traces to Application Insights when it is configured. Returns True when tracing is on."""
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if not conn:
        return False
    try:
        from agent_framework.observability import enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        log.warning("APPLICATIONINSIGHTS_CONNECTION_STRING is set but azure-monitor-opentelemetry is not installed")
        return False
    os.environ.setdefault("OTEL_SERVICE_NAME", "secondtouch")
    configure_azure_monitor(connection_string=conn)
    # prompts and replies stay out of the traces unless asked for: the timings, tokens and tools are enough
    enable_instrumentation(enable_sensitive_data=os.getenv("TRACE_CONTENT") == "1")
    log.info("Tracing the agent desk to Application Insights")
    return True
