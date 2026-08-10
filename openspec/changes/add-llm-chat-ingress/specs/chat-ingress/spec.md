## ADDED Requirements

### Requirement: MCP server exposes a chat tool

The `chat` tool SHALL accept a text message and an optional session ID.
The tool SHALL return an LLM-generated response based on the message and
conversation history from the specified session.

#### Scenario: Send a message and get a response
- **WHEN** the user sends a message to the `chat` tool with a session ID
- **THEN** the tool returns the LLM's response as a text content field

#### Scenario: No session ID creates a new session
- **WHEN** the user calls the `chat` tool without a session ID
- **THEN** the server generates a new session ID and returns the response
- **AND** the session ID is included in the tool response so the client
  can reuse it

#### Scenario: Reusing a session continues the conversation
- **WHEN** the user sends a subsequent message with an existing session ID
- **THEN** the server includes all prior messages in the conversation context
  when calling the LLM

### Requirement: Vault context is gathered automatically

Before every LLM call, the chat function SHALL gather current vault state —
the list of companies and their vacancy counts — and include it in the system
prompt so the model has accurate data.

#### Scenario: Company list is included in system context
- **WHEN** the `chat_message` function is called
- **THEN** it builds a system prompt that includes every company in the vault
  with its vacancy count

#### Scenario: Context is gathered from vault live
- **WHEN** the `chat_message` function reads company data
- **THEN** it fetches the data from the vault (unchanged `read_vault` call)
  and does not cache stale state

### Requirement: OpenAI-compatible API integration

The chat function SHALL call an OpenAI-compatible `chat.completions.create`
endpoint. The endpoint URL is configured via the `OPENAI_BASE_URL` environment
variable. The model is configured via the `OPENAI_MODEL` environment variable,
defaulting to `chatgpt-4o-mini`.

#### Scenario: API call uses configured base URL
- **WHEN** `OPENAI_BASE_URL` is set to `http://localhost:11434/v1`
- **THEN** the chat function sends the request to that URL

#### Scenario: API call uses default model when OPENAI_MODEL is unset
- **WHEN** `OPENAI_MODEL` is not set
- **THEN** the chat function uses `chatgpt-4o-mini` as the model name

#### Scenario: API call includes configured model when OPENAI_MODEL is set
- **WHEN** `OPENAI_MODEL` is set to `llama3.1`
- **THEN** the chat function uses `llama3.1` as the model name

#### Scenario: Missing base URL returns a typed error
- **WHEN** `OPENAI_BASE_URL` is not set and the user calls `chat_message`
- **THEN** the function raises `ChatConfigError` (a subclass of
  `CoreError`) with a message naming the missing variable

### Requirement: Conversation sessions are in-memory and keyed

Sessions SHALL be stored in memory, keyed by session ID. Each session
contains the full conversation history (user and assistant messages).
Sessions do not persist across server restarts.

#### Scenario: New session starts with empty history
- **WHEN** a new session is created (no prior call with that ID)
- **THEN** the conversation history for that session is a list containing
  only the system prompt

#### Scenario: Each message is appended to session history
- **WHEN** a user message is added to an existing session
- **THEN** the history list contains all prior messages plus the new one

#### Scenario: Sessions are in-memory only
- **WHEN** the MCP server process restarts
- **THEN** all session data is discarded (no persistence)

### Requirement: Tool invariant compliance

The `chat` tool SHALL not contain business logic of its own. All chat
functionality — session management, vault context gathering, and LLM API
calling — lives in `core.py`'s `chat_message` function. The MCP server
tool is purely argument marshalling around one call.

#### Scenario: MCP tool delegates to core.chat_message
- **WHEN** the `chat` tool is called via the MCP server
- **THEN** the handler is a thin wrapper that calls `core.chat_message(
  message, session, vault=vault_path)` and converts the result

#### Scenario: No new business logic in MCP server
- **WHEN** someone reviews `mcp_server.py`
- **THEN** they see that the `chat` tool handler has no logic beyond
  calling `core.chat_message` and converting the return type

### Requirement: Chat sessions resource

The MCP server SHALL expose a `vacancy-radar://chat-sessions` resource
that lists all active session IDs and their message counts.

#### Scenario: Chat sessions resource lists all sessions
- **WHEN** a client reads `vacancy-radar://chat-sessions`
- **THEN** they receive a list of objects with `session_id` and
  `message_count` for every active session

#### Scenario: Chat sessions resource is empty when no sessions exist
- **WHEN** no chat sessions have been created yet
- **THEN** the `vacancy-radar://chat-sessions` resource returns an empty list

### Requirement: Tool annotation correctness

The `chat` tool SHALL be annotated as `read_only_hint=false` and
`destructive_hint=false`, since it appends messages to a session but
never modifies vault state.

#### Scenario: Chat tool has correct annotations
- **WHEN** the tool list is retrieved
- **THEN** the `chat` tool has `read_only_hint=false`,
  `destructive_hint=false`, and `open_world_hint=false`
