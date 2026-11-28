---
name: tailuge-messaging
description: |
  Integration guide for @tailuge/messaging library. Use when building applications with:
  - Real-time presence/lobby systems
  - User matchmaking via challenges
  - Game table communication with players and spectators
  - Nchan-powered transport layer
---

# @tailuge/messaging

Quick integration guide. See [MESSAGING_SPEC.md](./MESSAGING_SPEC.md) for full API contract.

## Install

```bash
npm install @tailuge/messaging
```

## Quick Start

```typescript
import { MessagingClient } from '@tailuge/messaging';

const client = new MessagingClient({ baseUrl: "https://your-nchan-server.com" });
client.start();
```

## Lobby & Presence

```typescript
const lobby = await client.joinLobby({
  messageType: "presence",
  type: "join",
  userId: "user-123",
  userName: "Alice",
});

lobby.onUsersChange((users) => {
  console.log(`Online: ${users.length}`);
  users.forEach(u => {
    const flag = countryToFlag(u.meta?.country);
    console.log(`${flag} ${u.userName}`);
  });
});
```

## Challenge Opponent

```typescript
const tableId = await lobby.challenge(targetUserId, "billiards");

lobby.onChallenge((challenge) => {
  if (challenge.type === "offer") {
    lobby.acceptChallenge(challenge.challengerId, challenge.ruleType, challenge.tableId);
  }
});

## Chat

```typescript
await lobby.sendChat(targetUserId, "Hello!");

lobby.onChat((msg) => {
  console.log(`Message from ${msg.senderId}: ${msg.text}`);
});
```
```

## Table Messaging

```typescript
interface Move { x: number; y: number }
const table = await client.joinTable<Move>("table-xyz", "user-123", {
  onMessage: (msg) => {
    if (msg.type === "MOVE") {
      console.log(`Move at: ${msg.meta?.ts}`);
    }
  },
});

// Safe immediately after joinTable(): the library queues until the
// subscription is ready, sends in order, and retries transient failures.
await table.publish("MOVE", { x: 10, y: 20 });
await table.bothJoined; // two-player readiness; may remain pending if no opponent joins
```

`onMessage` and `onBothJoined` must be supplied on the initial join call. The
library suppresses reconnect buffer replays internally using server-generated
`meta.msgId`; consumers should not generate message IDs or deduplicate by `meta.ts`.

## Spectators

```typescript
table.onSpectatorChange((spectators) => {
  console.log(`Spectators: ${spectators.length}`);
});
```

## Cleanup

```typescript
await client.stop();
```

## Key Imports

```typescript
import {
  MessagingClient,
  canChallenge,
  canSpectate,
  activeGames,
} from '@tailuge/messaging';
```

## Predicates

```typescript
if (canChallenge(targetUser, currentUserId)) {
  await lobby.challenge(targetUser.userId, "billiards");
}

if (canSpectate(targetUser, currentTableId)) {
  await client.spectateTable(targetUser.tableId, currentUserId);
}
```

See [MESSAGING_SPEC.md](./MESSAGING_SPEC.md) for complete interface definitions.
