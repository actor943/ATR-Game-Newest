# Multi-User Messaging Library Specification

## Overview

This document outlines the requirements and contract for a unified messaging library designed to handle presence and real-time synchronization. The library uses the existing `NchanClient` as a transport layer (WebSockets for subscribe, POST for publish) and provides a semantic, stateful API for turn-based multi-user applications.

## Goals

- **Zero WebSocket Dependencies**: The consumer project should not interact with WebSockets directly.
- **Unified Client**: A single entry point for both global presence (lobby) and specific table messaging.
- **Stateful Presence**: Internal management of online users, including heartbeats and stale user pruning.
- **Semantic API**: Interaction through high-level methods rather than raw channel/URL manipulation.
- **Platform Agnostic**: Compatible with both Browser and Node.js environments.
- **Transport Reuse**: Leverages existing `NchanClient` from `src/lobby/nchanclient.ts` as the underlying transport.

---

## Core API Contract

### `MessagingClient`

The main class exposed by the library. Uses `NchanClient` internally for all transport operations.

```typescript
interface MessagingClient {
  /**
   * Initialize and start the client.
   * Handles initial connection and automatic reconnection logic.
   * In browser environments, attaches lifecycle event listeners.
   */
  start(): void;

  /**
   * Stop all connections, timers (heartbeats), and clean up resources.
   */
  stop(): Promise<void>;

  /**
   * Joins the global lobby to broadcast presence and see other online users.
   */
  joinLobby(user: PresenceMessage, options?: LobbyOptions): Promise<Lobby>;

  /**
   * Joins a specific table (game room) for 2-player communication.
   * Updates lobby presence with tableId when a lobby session exists.
   * Pass onMessage in options to receive table events; Table does not expose
   * a post-join onMessage(callback) registration method.
   */
  joinTable<T = any>(
    tableId: string,
    userId: string,
    options?: TableJoinOptions<T>,
  ): Promise<Table<T>>;

  /**
   * Subscribes to a table as a read-only spectator.
   * Does not update lobby presence. Spectator departures do not trigger onOpponentLeft.
   * Pass onMessage in options to receive table events.
   */
  spectateTable<T = any>(
    tableId: string,
    userId: string,
    options?: TableSpectatorOptions<T>,
  ): Promise<Table<T>>;
}
```

### `Lobby`

Represents the global presence state and matchmaking.

```typescript
interface Lobby {
  /**
   * Stream of the current online users.
   * Emits the full list whenever users join, leave, or time out.
   * The list must be sorted alphabetically by `userName` (case-insensitive).
   */
  onUsersChange(callback: (users: PresenceMessage[]) => void): void;

  /**
   * Update the current user's presence information (e.g., change name).
   */
  updatePresence(update: Partial<PresenceMessage>): Promise<void>;

  /**
   * Challenge another user to a game.
   * Returns the ID of the table created for the challenge.
   */
  challenge(userId: string, ruleType: string): Promise<string>;

  /**
   * Accept an incoming challenge.
   * Publishes the accept message and updates presence to show we've joined the table.
   * The table itself is joined separately via MessagingClient.joinTable() with the
   * same tableId (a client-generated channel id, not a server entity).
   */
  acceptChallenge(userId: string, ruleType: string, tableId: string, options?: Record<string, string>, challengerName?: string): Promise<void>;

  /**
   * Decline an incoming challenge.
   */
  declineChallenge(userId: string, ruleType: string, challengerName?: string): Promise<void>;

  /**
   * Cancel an outgoing challenge.
   */
  cancelChallenge(userId: string, ruleType: string): Promise<void>;

  /**
   * Subscribe to incoming challenges directed at the current user.
   */
  onChallenge(callback: (challenge: ChallengeMessage) => void): void;

  /**
   * Send a chat message to another user.
   */
  sendChat(recipientId: string, text: string): Promise<void>;

  /**
   * Subscribe to incoming chat messages directed at the current user.
   */
  onChat(callback: (message: ChatMessage) => void): void;

  /**
   * Leave the lobby.
   */
  leave(): Promise<void>;
}
```

### Table join options

Register `onMessage` in the options passed to `joinTable()` or `spectateTable()` so
it is active as the subscription starts; messages received before the callback is
registered cannot be replayed later.

```typescript
interface TableJoinOptions<T = any> {
  isSpectator?: boolean;
  onMessage?: (event: TableMessage<T>) => void;
  onBothJoined?: () => void;
}

interface TableSpectatorOptions<T = any> {
  onMessage?: (event: TableMessage<T>) => void;
  onBothJoined?: () => void;
}
```

### `Table`

Represents a specific communication channel for a 2-player/spectator scenario at a table.
The `Table` instance does **not** expose a post-join `onMessage(callback)` method;
message listeners are supplied through `joinTable()` or `spectateTable()` options.

```typescript
interface Table<T = any> {
  /**
   * Broadcast an event to all participants at the table.
   */
  publish(type: string, data: T): Promise<void>;

  /**
   * Subscribe to changes in the spectator list.
   */
  onSpectatorChange(callback: (spectators: PresenceMessage[]) => void): void;

  /**
   * Leave the table.
   */
  leave(): Promise<void>;
}
```

---

## Data Models

### `meta` (Server-Enriched Metadata)

All JSON messages published through the transport layer are automatically enriched by the server with metadata from HTTP headers and connection info. The server also assigns a unique `msgId` to each accepted message, including server-generated auto-leave messages. This `meta` object is **added by the server** and should be used by clients as the absolute source of truth for timing (`ts`). Clients should not generate or overwrite `msgId`.

```typescript
interface Meta {
  ts: number; // Epoch milliseconds (Source of Truth for event time)
  msgId?: string; // Server-generated identity used to suppress reconnect replays
  ua: string; // User-Agent header
  ip: string; // Obfuscated client address
  origin: string; // Origin header value
  method: string; // HTTP method (always POST for publish)
  country: string; // Country code from IP (e.g., "US", "GB", "XX")
  version?: string; // Optional client software version
}
```

**Note**: The client should NOT include `ua`, `ip`, `ts`, or `msgId` in published messages. The server adds metadata automatically. `msgId` is an identity for reconnect replay suppression; `ts` is only the event timestamp. The optional `version` field may be supplied through `MessagingClient.setVersion()`.

### `PresenceMessage`

Information about a user in the lobby. The `ua` field is **not** set by the client — it is provided by the server via `meta`.

```typescript
interface PresenceMessage {
  messageType: "presence";
  type: "join" | "heartbeat" | "leave";
  userId: string;
  userName: string;
  ruleType?: string;
  opponentId?: string | null;
  seek?: Seek;
  lastSeen?: number; // Managed internally for pruning (derived from meta.ts)
  meta?: Meta; // Server-enriched metadata (received messages only)

  // Current game state:
  // - If present: user is playing or spectating at that table (available for spectating)
  // - If absent: user is available for new games
  tableId?: string;
}
```

#### External Game Integration

When users are redirected from the lobby to an external game page (e.g., billiards), the game page can maintain the user's presence as "in a table" by passing `tableId` when joining the lobby:

```typescript
// In the external game page
const client = new MessagingClient({ baseUrl: nchanUrl });

// Join lobby with tableId already set - lobby users see this player as "in game"
const lobby = await client.joinLobby({
  messageType: "presence",
  type: "join",
  userId: "player1",
  userName: "Player One",
  tableId: "table-123",  // Marks user as at table-123
});
```

This is useful when:
- The game was launched from a URL with tableId (e.g., after challenge acceptance)
- The new page creates a fresh MessagingClient but wants to preserve presence state
- Other lobby users should see this player as "currently in a game"

To clear the table status (e.g., when the game ends):
```typescript
await lobby.updatePresence({ tableId: undefined });
```

**Page unload:** When the lobby page unloads, a `leave` message is sent automatically. The external game page is expected to call `joinLobby()` with `tableId` to re-establish presence as "in game". This ensures no ghost users if the redirect fails.

#### Minimal Presence for Games

Games that only need online user count (no table joining):

```typescript
// Join without tableId - user appears as "available" in lobby
await client.joinLobby({
  messageType: "presence",
  type: "join",
  userId: "player1",
  userName: "Player One",
});

// Add tableId when starting a multiplayer game
await lobby.updatePresence({ tableId: "table-123" });

// Remove tableId when game ends
await lobby.updatePresence({ tableId: undefined });
```

### `ChallengeMessage`

Represents a peer-to-peer challenge request.

> **Invariant:** `challengerId` always refers to the original challenger (the one who sent the `offer`), and `challengeeId` always refers to the person being challenged. This must hold across **all** message types: `offer`, `accept`, `decline`, and `cancel` — regardless of who is sending the message.
>
> For example, when the challengee calls `declineChallenge()` or `acceptChallenge()`, they are the sender of that message but they must still set `challengerId` to the original challenger's ID and `challengeeId` to their own ID.
>
> **Field assignment by message type:**
>
> | type | sent by | `challengerId` | `challengeeId` |
> |---|---|---|---|
> | `offer` | user-a | user-a | user-b |
> | `cancel` | user-a | user-a | user-b |
> | `accept` | user-b | user-a | user-b |
> | `decline` | user-b | user-a | user-b |

```typescript
interface ChallengeMessage {
  messageType: "challenge";
  type: "offer" | "accept" | "decline" | "cancel";
  challengerId: string;   // Always the original challenger, across all message types
  challengerName: string; // Always the original challenger's name, across all message types
  challengeeId: string;   // Always the person being challenged, across all message types
  ruleType: string;
  tableId?: string; // Optional: table created by challenger
  meta?: Meta; // Server-enriched metadata (received messages only)
}
```

### `ChatMessage`

Represents a peer-to-peer chat message.

```typescript
interface ChatMessage {
  messageType: "chat";
  senderId: string;
  recipientId: string;
  text: string;
  meta?: Meta; // Server-enriched metadata (received messages only)
}
```

### `TableInfo` (UNDER REVIEW)

Lobby-level information about an active game table.

```typescript
interface TableInfo {
  tableId: string;
  ruleType: string;
  players: { id: string; name: string }[];
  spectatorCount: number;
  status: "waiting" | "playing" | "finished";
  createdAt: number;
}
```

### `TableMessage`

A generic structure for table/game events. Replaces raw payloads with a structured, meta-aware event.

```typescript
interface TableMessage<T = any> {
  type: string;
  senderId: string;
  data: T; // Application-specific payload
  meta?: Meta; // Server-enriched metadata (received messages only)
}
```

---

## Derived State & Logic

Clients can derive additional state from the presence data provided by the `Lobby`.

### 1. Active Games List

#### `activeGames(users: PresenceMessage[]): ActiveGame[]`

Filters users with a `tableId` and returns one entry per unique table.

```typescript
interface ActiveGame {
  tableId: string;
  players: { id: string; name: string }[];
  ruleType?: string;
}
```

**Note**: Spectator vs player distinction is not available in presence data - all users with `tableId` are included as "players".

### 2. Predicates

Exported helper functions for consumer use.

#### `canChallenge(target: PresenceMessage, currentUserId: string): boolean`
Returns true if:
- `target.userId !== currentUserId` (not self)
- `!target.tableId` (not already at a table)
- `!target.seek` (not seeking a game)

#### `canSpectate(target: PresenceMessage, currentTableId?: string): boolean`
Returns true if:
- `target.tableId` exists (is at a table)
- `target.tableId !== currentTableId` (not already at this table)

---

## Internal Requirements

### 1. Presence Management

- **Heartbeat**: The library must automatically send periodic "heartbeat" messages (e.g., every 120 seconds) to the lobby while active.
- **Pruning**: The library must maintain an internal map of users and automatically remove users who haven't sent a heartbeat within a specific TTL (e.g., 90 seconds).
- **Unload Handling**: In browser environments, the library should attempt to send a "leave" message on `beforeunload` or `pagehide`.

### 2. Transport & Reconnection

- **Transport Layer**: Uses `NchanClient` from `src/lobby/nchanclient.ts` as the underlying transport. The WebSocket/POST abstraction is handled internally. `NchanClient` remains transport-agnostic and platform-neutral (Browser + Node.js).
- **Resilience**:
  - Automatic exponential backoff for reconnection on WebSocket failure.
  - Transparently handle transition between online/offline states.
- **Concurrency**: Ensure multiple `Table` instances can coexist if needed (though typically one game at a time).

### 3. Message Retention

Retention is enforced by Nchan per channel (see `docker/nchan.conf`). A channel's
settings come from its last-used **publishing** location, not from the subscriber
location.

- **Table channels**: 3000 messages retained for 24 hours (`nchan_message_timeout 24h`).
  The subscriber endpoint uses `nchan_subscriber_first_message oldest`, so a late
  joiner or spectator receives the retained messages, oldest first, before live
  traffic.
- **Presence channel**: buffering is disabled (`nchan_message_buffer_length 0`), so
  there is no replay. Clients build lobby state from live join events and heartbeats;
  a reconnecting client re-registers with a join and waits for peers' heartbeats
  rather than receiving buffered presence frames.
- **Arena chat**: 20 messages retained for 1 hour.

Nchan's built-in default for `nchan_message_timeout` is 1 hour (nchan v1.3.8 defines
`NCHAN_DEFAULT_MESSAGE_TIMEOUT 3600`), so longer retention must be set explicitly.

Retention is in-memory only (`nchan_shared_memory_size 32M`): it is lost on
restart/reload, and Nchan evicts old messages/channels when the slab fills. Messages
larger than nginx's body buffer may be stored in temp files.

### 3. Page Visibility & Browser Lifecycle

Page visibility handling (`pagehide`, `pageshow`, `visibilitychange`) is the responsibility of `MessagingClient` (application layer), **not** `NchanClient` (transport layer). This keeps the transport layer platform-agnostic.

`MessagingClient` should:

- Listen for `pagehide` to close connections and send a "leave" presence message
- Listen for `pageshow` (with `event.persisted`) to restore connections from bfcache
- Track `document.hidden` state to pause/resume heartbeats

```typescript
// Example pattern for MessagingClient
// Note: MessagingClient does NOT have direct socket access.
// It calls stop() on subscriptions returned by NchanClient, or exposes its own stop() method.

private handlePageHide = (): void => {
  this.stop(); // Stops all subscriptions and sends "leave" presence
};

private handlePageShow = (event: PageTransitionEvent): void => {
  if (event.persisted) {
    this.start().then(() => this.joinLobby(this.currentUser));
  }
};
```

### 3. State Synchronization

- The library should ensure that when a user joins a lobby, they receive the current "state of the world" or quickly populate it via incoming heartbeats.
- For tables, it should provide a reliable pipe for sequence-sensitive events (optionally implementing sequence numbering if required by the transport).

---

## Accepted Concerns

### 1. Race Conditions in Matchmaking

### 2. Presence Scaling ($O(N^2)$)

### 3. State Reconstruction

The presence channel does not buffer messages, so a new client joining the lobby receives no replayed presence. It learns about existing users from live presence heartbeats and join events, and its own join is broadcast to peers; the client prunes users that stop heartbeating. Table channels are different: their retained messages are replayed to late joiners and spectators (up to 3000 messages, 24 hours).

---

## Usage Example (Conceptual)

```typescript
const client = new MessagingClient({
  baseUrl: "billiards-network.onrender.com",
});

await client.start();

// Lobby interaction
const lobby = await client.joinLobby({
  messageType: "presence",
  type: "join",
  userId: "user-123",
  userName: "Alice",
});

lobby.onChat((msg) => {
  console.log(`Chat from ${msg.senderId}: ${msg.text}`);
});

await lobby.sendChat("user-456", "Hi Bob!");

lobby.onUsersChange((users) => {
  console.log("Online users:", users.length);
});

lobby.onChallenge((challenge) => {
  if (confirm(`Accept challenge from ${challenge.challengerName}?`)) {
    lobby.acceptChallenge(challenge.challengerId, challenge.ruleType, challenge.tableId);
  }
});

// Table interaction with a generic move type
interface Move { x: number; y: number }
const table = await client.joinTable<Move>("table-xyz", "user-123", {
  onMessage: (msg) => {
    if (msg.type === "MOVE") {
      // msg.data is typed as Move
      applyMove(msg.data);
      console.log("Move received at:", msg.meta?.ts);
    }
  },
});

table.publish("MOVE", { x: 10, y: 20 });
```

---

## Future Considerations

### 1. `beforeunload` Handler

The current implementation uses `pagehide` to handle browser page dismissal. An alternative approach is to use `beforeunload` to send a synchronous (or near-synchronous) "leave" presence message before the page unloads. This provides a fallback for browsers where `pagehide` may not fire reliably.

Trade-offs:
- `beforeunload` is synchronous and may delay page dismissal
- Not supported in all browsers (e.g., Safari iOS)
- `pagehide` is the modern recommended approach, but may not send network requests in some cases

### 2. Spectating

Use `spectateTable` for read-only table subscriptions. Spectator `table:leave` messages include `data.isSpectator: true` so player clients skip `onOpponentLeft`. The Nchan server tags auto-leaves from spectator WebSocket disconnects the same way (via `spectator=1` on the subscribe URL).

```typescript
const table = await client.spectateTable("table-xyz", "user-123", {
  onMessage: (msg) => { /* handle table messages */ },
});
```

`TableLeaveData` and `isSpectatorTableLeave()` in `types.ts` identify spectator leave messages if needed in custom handlers.
