# Provider integration notes

Status: written on 2026-11-02 from public documentation and third-party pages found with a web search tool. No key was available, no provider was called, and no network call was made. Every row is marked confirmed or unconfirmed. Nothing unconfirmed is implemented as fact (AGENTS.md 11.7).

"Confirmed" means the statement appears on a page published by the provider. "Third-party" means it appears only on a page written by someone else. "Unconfirmed" means no source was found.

## What was confirmed and what was not

| Route | Item | Status | Source |
|---|---|---|---|
| Meta Model API | Base URL `https://api.meta.ai/v1` | third-party | [OpenClaw Meta page](https://docs.openclaw.ai/pt-BR/providers/meta) |
| Meta Model API | Chat Completions surface at `/v1/chat/completions` | third-party | [Muse API guide](https://www.orcarouter.ai/blog/muse-api) |
| Meta Model API | Auth header `Authorization: Bearer <key>` | third-party | same two pages |
| Meta Model API | Response `usage` field names | unconfirmed (OpenAI-style `prompt_tokens`, `completion_tokens` assumed) | none |
| Meta Model API | Error body shape, `Retry-After` on 429 | unconfirmed | none |
| Meta Model API | `META_USE_CONTRIBUTOR_TIER` wire format | unconfirmed, not sent | none |
| Muse Voice Transcribe | Realtime WebSocket `wss://api.meta.ai/v1/asr/realtime` | third-party | [LiteLLM Meta page](https://docs.litellm.ai/docs/providers/meta.md) |
| Muse Voice Transcribe | Batch file endpoint | conflicting (LiteLLM says unsupported, another blog implies one exists) | [Muse Voice Transcribe blog](https://www.orcarouter.ai/it/blog/muse-voice-transcribe) |
| Baseten | Base URL `https://inference.baseten.co/v1`, `/chat/completions`, OpenAI-compatible | confirmed | [Baseten Model APIs](https://docs.baseten.co/development/model-apis/overview), [chat completions reference](https://docs.baseten.co/reference/inference-api/chat-completions.md) |
| Baseten | Exact auth header on the direct endpoint | unconfirmed (SDK key field shown; a gateway page shows Bearer) | [Cloudflare AI Gateway page](https://developers.cloudflare.com/ai-gateway/usage/providers/baseten/) |
| Baseten | Dedicated deployment URL for the Muse Spark Open model | unconfirmed | none |
| Modal | Endpoints are authenticated by default with proxy auth tokens | confirmed | [Modal endpoints guide](https://modal.com/docs/guide/endpoints) |
| Modal | Headers `Modal-Key` and `Modal-Secret` | confirmed | same page |
| Modal | Combined value as a Bearer token | confirmed, exact combination format not read | same page |
| Modal | A vLLM server on Modal exposes `/v1/chat/completions` | third-party | [Bolna guide](https://www.bolna.ai/docs/custom-llm-inference/modal) |
| Modal | The deployed model and its endpoint URL | unconfirmed (depends on the deployment the maintainer makes) | none |
| Vertex AI | Method `generateContent`, body fields `contents`, `systemInstruction`, `generationConfig` (`maxOutputTokens`, `temperature`) | confirmed | [Gemini API in Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference) |
| Vertex AI | `usageMetadata` with `promptTokenCount`, `candidatesTokenCount`, `totalTokenCount` | confirmed | [UsageMetadata reference](https://docs.cloud.google.com/ruby/docs/reference/google-cloud-ai_platform-v1/0.56.0/Google-Cloud-AIPlatform-V1-GenerateContentResponse-UsageMetadata) |
| Vertex AI | Full REST URL and OAuth token flow from a service account | not read in this pass | none |
| Prices | Meta Standard tier: $1.25 in, $4.25 out per M tokens | maintainer-confirmed | maintainer decision 2026-11-03; public pricing pages agree |
| Prices | Baseten and Modal per-token prices | unconfirmed, see `src/waggle/llm/prices.toml` | maintainer, PENDING rows 4 and 10 |

Access date for every link: 2026-11-02.

## What is implemented

| Route | Implemented | Notes |
|---|---|---|
| `meta` | Chat Completions over HTTPS with Bearer auth | Usage field names are unconfirmed, so a response without `usage` is rejected. The price is verified ($1.25 in, $4.25 out per M tokens, Standard tier), so the price gate passes for this route. |
| `baseten` | Chat Completions with Bearer auth | The auth header is the unconfirmed part. If the first cloud smoke test returns 401, check this row first. |
| `modal` | Chat Completions with `Modal-Key` and `Modal-Secret` headers | `MODAL_ENDPOINT_URL` is read as the OpenAI-style base URL (the part before `/chat/completions`). |
| `vertex` | Not implemented | Needs a service account OAuth token, which needs RSA signing that the standard library does not have. A route to `vertex` fails closed with a `ConfigError` (no provider registered). Implementing it needs a dependency decision from the maintainer. |
| Voice | Not implemented | The documented path is a WebSocket, and the batch path is disputed. A voice call fails closed in the same way. |

Fallbacks to `vertex` in `routes.toml` therefore cannot succeed yet. The client records the failure and, when fallbacks are enabled, raises `ConfigError`.

## Environment variables

Names only. Values are never printed, logged, repr'd or placed in an exception message.

| Name | Used by | Description | Default |
|---|---|---|---|
| `WAGGLE_LLM_PROVIDER` | factory | `mock` or `http`. Any other value, or no value, fails closed with `ConfigError`. | none |
| `META_API_KEY` | meta | Bearer key | none, required |
| `META_API_BASE_URL` | meta | Base URL, must be `https` | none, required |
| `BASETEN_API_KEY` | baseten | Bearer key | none, required |
| `MODAL_TOKEN_ID` | modal | Sent as `Modal-Key` | none, required |
| `MODAL_TOKEN_SECRET` | modal | Sent as `Modal-Secret` | none, required |
| `MODAL_ENDPOINT_URL` | modal | Base URL, must be `https` | none, required |
| `META_SPEND_CAP_USD`, `BASETEN_SPEND_CAP_USD`, `MODAL_SPEND_CAP_USD` | budget guard | Hard cap in USD (`135.0`, `90.0`, `90.9` in GitHub Actions variables). Missing or invalid raises `InvalidCapError` before any call. | none, required |
| `META_MODEL_ID`, `META_WONDER_MODEL_ID`, `BASETEN_MODEL_ID`, `MODAL_GLIMMER_MODEL_ID`, `MODAL_SPARK_OPEN_MODEL_ID` | routing | Model ids, read by the existing client (`muse-spark-1.3`, `muse-wonder-1.0`, `meta-models/muse-spark-open`, `meta-models/Muse-Glimmer-30B`, `meta-models/Muse-Spark-Open-816B-A42B` in GitHub Actions variables) | none, required |

The Baseten base URL is fixed in code to the documented `https://inference.baseten.co/v1`. In GitHub Actions variables, `META_API_BASE_URL` is configured to `https://api.meta.ai/v1` and `MODAL_ENDPOINT_URL` is configured to `https://inference.us-west.modal.direct/v1` (Modal workspace `ac-BQSGYNtST9xpA7WA5Cef1y`). A plain `http` URL is accepted only when a test builds the settings with the loopback switch, which the environment cannot turn on.

## Prices

`src/waggle/llm/prices.toml` holds USD per million tokens for each provider, and a `verified` flag. Each entry ships with `verified = false` and no number until the maintainer fills it. `meta` is verified at $1.25 in and $4.25 out per M tokens (Standard tier, maintainer decision 2026-11-03); `baseten` and `modal` are still unverified. For an unverified entry `estimate_cost` raises `ConfigError`, so the client makes no call on that route. Cost per call is computed from the response `usage` and these prices, never from a value the server reports as a price.

## Failure behavior

| Event | Result |
|---|---|
| Missing key, URL or cap | `ConfigError` or `InvalidCapError`, no call |
| Non-https URL | `ConfigError`, no call |
| Unverified or missing price | `ConfigError`, no call |
| 429 | Retry up to the attempt cap, waiting `Retry-After` seconds up to a cap, else backoff. Then `ProviderError`. |
| 5xx, timeout, refused connection | Retry with exponential backoff up to the attempt cap, then `ProviderError` |
| 401, 403, other 4xx | `ProviderError` at once, no retry |
| 3xx | `ProviderError`, redirects are never followed (the key would travel with them) |
| Body above the size cap, wrong content type, malformed JSON, duplicate keys, missing `choices` or `usage` | `ProviderError`, no retry |

Error messages carry the provider name and the status class only. They never carry a response body, a header or a URL.
