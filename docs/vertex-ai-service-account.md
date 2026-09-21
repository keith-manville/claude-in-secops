# Service account setup for Claude on Vertex AI

This guide creates the Google Cloud service account the Claude integration uses when
**Provider** is set to `Vertex AI`, grants it the minimum permissions, and produces the key file
you paste into the **Service Account JSON** parameter. Google now brands Vertex AI's model
serving as the Gemini Enterprise Agent Platform; the API, roles and endpoints below are the same.

## Permissions summary

| Who | Role | Why |
| --- | --- | --- |
| **The integration's service account** (runtime) | `roles/aiplatform.user` (Vertex AI User), or a custom role containing only `aiplatform.endpoints.predict` | Sends `rawPredict` and `count-tokens` requests to Claude models. This is the only permission the integration exercises. |
| **A human administrator** (one-time setup) | `roles/serviceusage.serviceUsageAdmin` | Enables the Vertex AI API (`aiplatform.googleapis.com`) in the project. |
| **A human administrator** (one-time setup) | `roles/consumerprocurement.entitlementManager` (Consumer Procurement Entitlement Manager) | Accepts Anthropic's terms and enables each Claude model in Model Garden. The service account does not need this role. |
| **A human administrator** (one-time setup) | `roles/iam.serviceAccountAdmin` and `roles/iam.serviceAccountKeyAdmin` (or Project IAM Admin) | Creates the service account, grants it the role, and issues the key. |

Google's documentation states the requirement directly: to make prompt requests to partner
models a principal needs the `aiplatform.endpoints.predict` permission, which is included in the
Vertex AI User role, and enabling partner models in Model Garden requires the Consumer
Procurement Entitlement Manager role. The service account only needs the first.

Do **not** grant the service account `roles/aiplatform.admin`, `roles/editor` or `roles/owner`.
Nothing in the integration reads, writes or deploys Vertex AI resources.

## Prerequisites

- The [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated as an
  administrator of the project (`gcloud auth login`).
- Billing enabled on the project.
- If your organization uses the `iam.disableServiceAccountKeyCreation` constraint, an
  organization policy administrator must exempt this project (or you must use Application
  Default Credentials instead of a key, see [Alternatives to a key file](#alternatives-to-a-key-file)).

## Step 1: Set variables

```bash
export PROJECT_ID="my-secops-project"
export SA_NAME="secops-claude"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}"
```

## Step 2: Enable the Vertex AI API

```bash
gcloud services enable aiplatform.googleapis.com
```

If your organization restricts service usage, an organization policy administrator must also
allow `cloudcommerceconsumerprocurement.googleapis.com`, which Model Garden uses when a Claude
model is enabled.

## Step 3: Enable the Claude model in Model Garden

This is a one-time step done by a human with the Consumer Procurement Entitlement Manager role,
because it accepts Anthropic's terms of service for the project.

```bash
# Grant yourself (or the person doing the setup) the entitlement manager role.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="user:admin@example.com" \
  --role="roles/consumerprocurement.entitlementManager"
```

Then open the model card in the console and click **Enable**, for example
[Claude Opus 5](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-opus-5)
or [Claude Sonnet 5](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-sonnet-5).
There is no `gcloud` command for accepting the terms; the console is required for this step.

## Step 4: Create the service account

```bash
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="Google SecOps SOAR - Claude integration" \
  --description="Used by the Claude integration in Google SecOps SOAR to call Claude on Vertex AI"
```

## Step 5: Grant the runtime permission

Option A, the predefined **Vertex AI User** role (simplest, what Google's documentation
recommends):

```bash
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user" \
  --condition=None
```

Option B, a custom role with only the single permission the integration needs. Prefer this if
your security policy requires least privilege; Vertex AI User also grants read access to other
Vertex AI resources in the project.

```bash
gcloud iam roles create claudeSecOpsInvoker \
  --project="${PROJECT_ID}" \
  --title="Claude on Vertex AI invoker" \
  --description="Send prediction and token count requests to Claude models on Vertex AI" \
  --permissions="aiplatform.endpoints.predict" \
  --stage="GA"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="projects/${PROJECT_ID}/roles/claudeSecOpsInvoker" \
  --condition=None
```

Verify the binding:

```bash
gcloud projects get-iam-policy "${PROJECT_ID}" \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:${SA_EMAIL}" \
  --format="table(bindings.role)"
```

## Step 6: Create the key file

```bash
gcloud iam service-accounts keys create "./${SA_NAME}-key.json" \
  --iam-account="${SA_EMAIL}"
```

The file starts with `{"type": "service_account"`. Paste its **entire contents** into the
**Service Account JSON** parameter of the Claude integration instance in Google SecOps, then
delete the local copy:

```bash
rm "./${SA_NAME}-key.json"
```

## Step 7: Test the service account before configuring SecOps

Impersonate the service account and send the same token count request the integration's
**Ping** action sends. A JSON response with `input_tokens` confirms the API, model enablement,
role and region are all correct.

```bash
export REGION="global"
export MODEL_ID="claude-opus-5"

# global uses aiplatform.googleapis.com; a specific region uses ${REGION}-aiplatform.googleapis.com
export ENDPOINT="aiplatform.googleapis.com"

curl -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token --impersonate-service-account="${SA_EMAIL}")" \
  -H "Content-Type: application/json" \
  "https://${ENDPOINT}/v1/projects/${PROJECT_ID}/locations/${REGION}/publishers/anthropic/models/count-tokens:rawPredict" \
  -d "{\"model\": \"${MODEL_ID}\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}]}"
```

Impersonation requires your own account to hold `roles/iam.serviceAccountTokenCreator` on the
service account:

```bash
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="user:admin@example.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

Expected failure messages and their causes:

| Response | Cause |
| --- | --- |
| `403 ... Permission 'aiplatform.endpoints.predict' denied` | Step 5 was skipped or bound to the wrong principal. |
| `403 ... Vertex AI API has not been used in project` | Step 2 was skipped. |
| `404 ... Publisher Model ... not found` or `... is not enabled` | The model is not enabled in Model Garden for this project (Step 3), or the model ID is wrong. |
| `403 ... consumer procurement` | The organization policy blocks `cloudcommerceconsumerprocurement.googleapis.com`. |

## Key hygiene

- Keys never expire on their own. Rotate them on your normal credential schedule:

  ```bash
  gcloud iam service-accounts keys list --iam-account="${SA_EMAIL}"
  gcloud iam service-accounts keys create "./${SA_NAME}-key.json" --iam-account="${SA_EMAIL}"
  # paste the new key into the SecOps integration instance, click Test, then revoke the old key
  gcloud iam service-accounts keys delete OLD_KEY_ID --iam-account="${SA_EMAIL}"
  ```

- Use a dedicated service account per SecOps environment if different teams own them, so a
  compromised key can be revoked without affecting the others.
- Enable request/response logging on Vertex AI if you need an audit trail of prompts and
  completions; Anthropic recommends keeping at least 30 days.

## Alternatives to a key file

If the SecOps execution environment already runs with Google Cloud credentials, leave
**Service Account JSON** empty and the integration uses Application Default Credentials. This
applies when the actions run on a remote agent hosted on Compute Engine or GKE with an attached
service account. Grant that attached service account the same runtime role from Step 5. Google
SecOps SaaS tenants without a remote agent do not have such credentials and need the key file.

## Removing access

```bash
gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"

gcloud iam service-accounts delete "${SA_EMAIL}"
```
