# Claude for Google SecOps SOAR

A community response integration that brings [Claude](https://www.anthropic.com/claude) into
Google Security Operations (SecOps) SOAR playbooks. It follows the structure and tooling of the
[Google SecOps Content Hub](https://github.com/chronicle/content-hub), so the integration directory
can be copied into a Content Hub fork and submitted as is.

The integration lives in
[`content/response_integrations/third_party/community/claude`](content/response_integrations/third_party/community/claude).

## Actions

| Action | What it does |
| --- | --- |
| **Ping** | Verifies the API key and the configured model by retrieving the model from the Claude API. |
| **Ask Claude** | Sends a prompt (and optional system prompt) to Claude and returns the response. Can constrain the answer to a JSON Schema, append the current alert as context, and save the answer as a case insight or comment. |
| **Summarize Alert** | Sends the case, alert, security events and entities to Claude and returns a structured triage: verdict, confidence, suggested severity, attack narrative, key findings, MITRE ATT&CK techniques, indicators and recommended actions. Creates an insight and comes with a predefined widget. |
| **Assess Entities** | Asks Claude to assess each entity in the alert scope using the enrichment already attached to it. Adds `Claude_*` enrichment fields, an entity insight, and can mark malicious entities as suspicious. |
| **Extract Indicators** | Extracts and normalizes IP addresses, domains, URLs, hashes, email addresses, file names, CVEs and ATT&CK technique IDs from free text (email bodies, threat reports). Can add them to the alert as entities. |

All prompts wrap alert data, entity data and user-supplied text in XML-style tags and instruct
Claude to treat that content as data rather than instructions, which limits prompt injection
through telemetry. Structured actions use the Claude API's JSON Schema output format, so results are
always valid JSON that playbooks can branch on, for example `[Summarize Alert.JsonResult.verdict]`.

## Integration configuration

The integration can reach Claude two ways, selected by the **Provider** parameter:

- **Anthropic API** (default): direct calls to `api.anthropic.com` with an Anthropic API key.
- **Vertex AI**: calls to Claude on Google Cloud Vertex AI, authenticated with a service account
  key (or the execution environment's Application Default Credentials). Useful when Claude usage
  should stay inside your Google Cloud project and billing.

| Parameter | Default | Description |
| --- | --- | --- |
| Provider | `Anthropic API` | `Anthropic API` or `Vertex AI`. |
| API Root | `https://api.anthropic.com` | Anthropic API only. Base URL of the Claude API or a compatible gateway. |
| API Key | | Anthropic API only. API key from the [Claude Console](https://platform.claude.com). |
| GCP Project ID | | Vertex AI only. Project with the Vertex AI API enabled and Claude models available in Model Garden. |
| GCP Region | `global` | Vertex AI only. Vertex AI location, for example `global`, `us-east5` or `europe-west1`. |
| Service Account JSON | | Vertex AI only. Contents of a service account key file for an account with the **Vertex AI User** role. Leave empty to use Application Default Credentials. |
| Model | `claude-opus-5` | Default model ID. Actions can override it. On Vertex AI, dated snapshots use an `@` separator, for example `claude-opus-4-5@20251101`. |
| Max Output Tokens | `8192` | Default output token limit per request (maximum 20000). |
| Effort | `high` | Reasoning effort (`low`, `medium`, `high`, `xhigh`, `max`, or `Default` to omit). |
| Adaptive Thinking | `true` | Sends adaptive extended thinking. Disable for models that do not support it, such as Claude Haiku 4.5. |
| Request Timeout | `300` | Timeout in seconds for one request to the Claude API. |
| Verify SSL | `true` | Validate the API's TLS certificate. |

Requests are sent through the official [`anthropic`](https://pypi.org/project/anthropic/) Python
SDK: `anthropic.Anthropic` for the Anthropic API and `anthropic.AnthropicVertex` for Vertex AI.
Refusals returned by Claude's safety classifiers fail the action with the refusal category and
explanation in the output message. On Vertex AI, **Ping** sends a token count request instead of
querying the Models API, which Vertex does not expose; it still exercises the project, region,
credentials and model.

### Setting up Vertex AI

1. In the Google Cloud console, enable the **Vertex AI API** in the project.
2. In **Vertex AI > Model Garden**, open the Claude model you want to use and click **Enable**.
3. Create a service account with the **Vertex AI User** (`roles/aiplatform.user`) role, or a
   custom role containing only `aiplatform.endpoints.predict`, and create a JSON key for it.
   [docs/vertex-ai-service-account.md](docs/vertex-ai-service-account.md) has the exact `gcloud`
   commands, the roles each step needs, and a `curl` test that mirrors the Ping action.
4. In the integration configuration set **Provider** to `Vertex AI`, fill in **GCP Project ID**,
   **GCP Region** and paste the key file contents into **Service Account JSON**.
5. Set **Model** to the ID shown in Model Garden and run **Ping**.

The SecOps execution environment (or remote agent) needs outbound HTTPS access to
`aiplatform.googleapis.com` (or the regional `<region>-aiplatform.googleapis.com` endpoint) and to
`oauth2.googleapis.com` for token exchange.

## Installing in Google SecOps

For a click-through walkthrough of the SecOps web console (import in the IDE, configure in the
Content Hub, test with Ping), see
[docs/install-google-secops-gui.md](docs/install-google-secops-gui.md).

1. Install `uv` and the Content Hub `mp` CLI:

   ```bash
   uv tool install mp --from "git+https://github.com/chronicle/content-hub.git#subdirectory=packages/mp"
   mp config --root-path "$(pwd)"
   ```

2. Package the integration (this also runs the build):

   ```bash
   mp pack integration claude
   ```

   The ZIP is written to `out/pack/Claude<date>.zip`.

3. Upload the resulting ZIP through **Response > IDE > Import** (custom integration) in Google
   SecOps, or push it directly to an instance with `mp login` and `mp push`:

   ```bash
   mp login --api-root https://{YOUR_INSTANCE}.siemplify-soar.com --api-key {YOUR_API_KEY}
   mp push integration claude
   ```

   Google recommends the `mp` workflow over manual IDE uploads for integrations that depend on
   TIPCommon, because `mp` packages the nested dependency tree automatically. Every dependency of
   this integration resolves to a pure-Python or `manylinux_2_17_x86_64` wheel, which is what the
   platform's dependency resolver requires.

4. Configure an instance of the **Claude** integration in the Content Hub tab and run **Ping**.
   Ping only uses the integration configuration, which is what the Content Hub **Test** button
   exercises.

To keep a private copy instead of contributing it upstream, place the directory under
`content/response_integrations/custom/` in a Content Hub clone, which is the location Google's
custom integration guide reserves for proprietary integrations.

## Development

```bash
cd content/response_integrations/third_party/community/claude
uv sync --dev
PYTHONPATH=.venv/lib/python3.11/site-packages/soar_sdk .venv/bin/python -m pytest tests
```

Or from the repository root, using the Content Hub tooling:

```bash
mp validate integration claude
mp test -i claude
mp check content/response_integrations/third_party/community/claude
```

`mp build` flattens `core/` into a single `Managers/` directory and rewrites relative imports, so
every relative import must point at one module directly inside `core/` or `actions/`. The test
`tests/test_defaults/test_build_imports.py` enforces that layout.

Tests never call the Claude API. The Anthropic SDK is pointed at an in-memory mock through an
`httpx2.MockTransport`, and the SOAR SDK session is routed to a mock platform that records the
insights, comments and entity updates each action produces.

The `packages/` directory vendors the TIPCommon, EnvironmentCommon and integration_testing wheels
from the Content Hub so the integration resolves its dependencies at the same relative paths it
would use inside a Content Hub checkout.

## Contributing the integration to the Content Hub

Copy `content/response_integrations/third_party/community/claude` into a fork of the Content Hub
at the same path, run `mp validate integration claude` and `mp test -i claude`, and open a pull
request. The integration follows the Content Hub
[response integration structure](https://github.com/chronicle/content-hub/blob/main/docs/content_deep_dive/response_integrations/response_integration_structure.md).

## License

Apache 2.0, see [LICENSE](LICENSE).
