# Installing the Claude integration through the Google SecOps GUI

This guide walks through installing the Claude integration in Google Security Operations (SecOps)
SOAR using only the web console: importing the integration package in the IDE, configuring an
instance in the Content Hub, and verifying it with the built-in **Ping** action.

For a scripted install with the Content Hub `mp` CLI (`mp login` and `mp push`), see the
[README](../README.md).

## Before you start

You need:

- **A Google SecOps SOAR instance** where your user can open **Response > IDE** and configure
  integrations. Custom integration import requires the permissions of an administrator or an
  equivalent custom role.
- **Credentials for one of the two providers:**
  - *Anthropic API*: an API key created in the [Claude Console](https://platform.claude.com) under
    API keys.
  - *Vertex AI*: a Google Cloud project with the Vertex AI API enabled, the Claude model enabled
    in **Vertex AI > Model Garden**, and a JSON key for a service account that has the
    **Vertex AI User** role. If the SecOps execution environment already runs with Application
    Default Credentials that can call Vertex AI, the key file is optional.

  Secrets are only ever stored in the integration configuration, which SecOps keeps as password
  fields.
- **Outbound HTTPS access** from the SecOps execution environment (or the remote agent that runs
  the actions) to `api.anthropic.com` for the Anthropic API, or to `aiplatform.googleapis.com`
  (or `<region>-aiplatform.googleapis.com`) and `oauth2.googleapis.com` for Vertex AI.
- **The integration package**, a ZIP file named like `Claude20260921.zip`. Either download it from
  your team's release location or build it yourself as described in the next section.

## Step 1: Get the integration package

Skip this step if you already have the ZIP.

The package is produced with the Content Hub `mp` CLI. On a machine with Python 3.11 and
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed:

```bash
git clone https://github.com/keith-manville/claude-in-secops.git
cd claude-in-secops
uv tool install mp --from "git+https://github.com/chronicle/content-hub.git#subdirectory=packages/mp"
mp config --root-path "$(pwd)"
mp pack integration claude
```

The last command writes `out/pack/Claude<date>.zip`. The file is about 28 MB because it bundles
the 42 Python wheels the integration depends on (the Anthropic SDK, TIPCommon and their
dependencies), so the SecOps platform does not need to download anything at install time.

## Step 2: Import the package in the IDE

1. In the main menu, go to **Response > IDE**.
2. Click the **Import** icon in the IDE toolbar.
3. Select the ZIP file and confirm.
4. **Claude** now appears in the IDE item list. The settings icon next to its name marks it as a
   custom integration. Click the icon to review what was imported:
   - **Description and icon** for the Content Hub card.
   - **Python dependencies**, listing the bundled wheels.
   - **Integration parameters** (API Root, API Key, Model, and so on).
   - Five actions: **Ping**, **Ask Claude**, **Summarize Alert**, **Assess Entities** and
     **Extract Indicators**, plus the **Claude - Alert Triage** widget.
5. Make sure the **Enable/Disable** toggle for the integration is set to **ON**, then click
   **Save**.

If the import reports a dependency error, or an action later fails with a
`ModuleNotFoundError` or a repeating `errorCode: 2000`, the package was not built with `mp`.
Re-create it with `mp pack integration claude` and import it again. Importing the same
integration again replaces the previous version.

## Step 3: Configure an instance in the Content Hub

1. Open the **Content Hub** (labelled **Marketplace** in older releases) and search for
   **Claude**. Custom integrations are listed together with the commercial ones.
2. Open the integration card and click **Configure** (or the **+** button) to add an instance.
3. Choose the **environment** the instance belongs to. Add one instance per environment that
   should be able to call Claude, or select the shared environment if all environments should
   use the same key.
4. Fill in the parameters:

   | Parameter | Value |
   | --- | --- |
   | Provider | `Anthropic API` or `Vertex AI`. |
   | API Root | Anthropic API only. Leave as `https://api.anthropic.com` unless you route traffic through a gateway that exposes the Anthropic Messages API. |
   | API Key | Anthropic API only. Your Anthropic API key. |
   | GCP Project ID | Vertex AI only. The Google Cloud project ID. |
   | GCP Region | Vertex AI only. `global` is recommended; regional values such as `us-east5` also work. |
   | Service Account JSON | Vertex AI only. Paste the full contents of the service account key file. Leave empty to use Application Default Credentials. |
   | Model | The default model ID for all actions, for example `claude-opus-5`. On Vertex AI use the ID shown in Model Garden; dated snapshots use an `@` separator, for example `claude-opus-4-5@20251101`. Individual playbook steps can override it. |
   | Max Output Tokens | Default `8192`. The largest response Claude may generate per request. Values above `20000` are rejected. |
   | Effort | Default `high`. One of `low`, `medium`, `high`, `xhigh`, `max`, or `Default` to let the model decide. Lower values are faster and cheaper. |
   | Adaptive Thinking | Leave enabled. Disable only for models that do not support adaptive thinking, such as Claude Haiku 4.5. |
   | Request Timeout | Default `300` seconds. Must be smaller than the action timeout you set in playbooks. |
   | Verify SSL | Leave enabled. |
   | Run Remotely | Enable only if this instance should execute on a remote agent. |

5. Click **Save**, then **Test**. The test runs the **Ping** action with the saved
   configuration. On the Anthropic API it retrieves the configured model; on Vertex AI it sends a
   token count request, which validates the project, region, credentials and model without
   generating output. A green check mark means the call succeeded. A red X shows the error
   message. See [Troubleshooting](#troubleshooting).

## Step 4: Verify with a manual action

1. Open any case and select an alert.
2. Click **Manual Action**, choose the **Claude** integration and the **Ping** action, and run it.
3. Run **Ask Claude** with a short prompt such as `Reply with the word OK.` The case wall shows
   the result and the **JsonResult** contains the response text, the model that answered, the
   stop reason and token usage.

## Step 5: Use the actions in playbooks

Add a **Claude** step to a playbook like any other integration action. Useful patterns:

- **Summarize Alert** early in a triage playbook. Branch on
  `[Summarize Alert.JsonResult.verdict]` (`Malicious`, `Suspicious`, `Benign`, `Inconclusive`)
  or `[Summarize Alert.JsonResult.suggested_severity]`. The action creates a case insight by
  default.
- **Assess Entities** after your enrichment steps, so Claude can reason over the enrichment
  properties other integrations attached. Results are written back as `Claude_*` entity fields
  and can mark malicious entities as suspicious.
- **Extract Indicators** on an email body or ticket text, with **Add Indicators As Entities**
  enabled, to turn a free-text report into entities the rest of the playbook can act on.
- **Ask Claude** with a JSON Schema when a later step needs a specific structure; the parsed
  object is returned under `JsonResult.structured_output`.

To show the triage summary in the alert view, add the **Claude - Alert Triage** widget to the
playbook step for **Summarize Alert** through the step's widget settings.

Set the playbook step timeout higher than the integration's **Request Timeout**. Actions that
call Claude once per entity, such as **Assess Entities**, need proportionally more time.

## Updating the integration

1. Build or download the new package.
2. Import it in **Response > IDE** as in Step 2. The new version replaces the old one and keeps
   the configured instances.
3. Re-run **Test** on each instance.

Content Hub updates never overwrite or delete custom integrations, so the Claude integration is
only changed when you import a new package yourself.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| **Test** shows a red X with `Authentication with the Claude API failed (HTTP 401)` | The API key is wrong, revoked or from a different organization. Paste a new key from the Claude Console and save again. |
| `The requested resource was not found (HTTP 404)` | The **Model** value is not a valid model ID, the **API Root** points to the wrong service, or on Vertex AI the model is not enabled in Model Garden for that project and region. |
| `"GCP Project ID" must be provided when "Provider" is "Vertex AI"` | Fill in the project ID, or switch **Provider** back to `Anthropic API`. |
| `"Service Account JSON" is not valid JSON` or `must be the contents of a service account key file` | Paste the entire key file downloaded from the Google Cloud console (it starts with `{"type": "service_account"`), not the client email or a user credential file. |
| `The API Key does not have permission to perform this request (HTTP 403)` on Vertex AI | The service account lacks the **Vertex AI User** role, or the Vertex AI API is not enabled in the project. |
| `The request to the Claude API timed out` | Raise **Request Timeout** and the playbook step timeout, or lower **Max Output Tokens** and **Effort**. |
| `Failed to connect to the Claude API` | The execution environment cannot reach `api.anthropic.com:443`. Check firewall and proxy rules; for remote agents, check the agent host. |
| `The Claude API rate limit was exceeded (HTTP 429)` | The organization's rate limit was hit. The SDK retries twice automatically; spread out playbook runs or raise the limit in the Claude Console. |
| `Claude declined to process the request (category: ...)` | Claude's safety classifiers refused the prompt. The output message includes the category and explanation. Rephrase the prompt or narrow the input. |
| Actions fail with `ModuleNotFoundError` or a looping `errorCode: 2000` | The dependencies were not bundled. Re-create the ZIP with `mp pack integration claude` and import it again. |
| `"Max Output Tokens" must be between 1 and 20000` | Requests are sent without streaming, which caps the output size. Lower the value. |

## Removing the integration

1. In the **Content Hub**, delete the configured instances.
2. In **Response > IDE**, select the **Claude** integration and delete it. Playbooks that used its
   actions will show the steps as missing until they are edited.
