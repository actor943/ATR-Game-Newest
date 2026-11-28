# Billiards Messaging Client

A stateful messaging library for Nchan-powered real-time applications. This library handles presence, heartbeats, matchmaking (challenges), and game table communication.

## Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Run Nchan Server (Docker)
The library requires an Nchan server for transport. You can build the image and start the local development server using:
```bash
npm run docker:start
```
To stop the server:
```bash
npm run docker:stop
```

### 3. Run the Example
```bash
npm run build:all

```
Then open [http://localhost:3000](http://localhost:3000) in multiple tabs to test presence and challenges.

---

## Testing

The project includes three levels of testing:

### 1. Unit & Integration Tests (Jest)
Comprehensive tests for `MessagingClient`, `Lobby`, and `Table` logic. These use `testcontainers` to automatically spin up an Nchan instance.
```bash
npm run test
npm run playwright
```
To debug leaks or hanging processes:
```bash
npx jest --config test/jest.config.js --detectOpenHandles --forceExit
```

### 2. Browser Connection Tests (Playwright)
Verifies that the client correctly connects and communicates within a real browser environment.
```bash
npm run test:debug
```

### 3. Nchan Configuration Tests (Shell)
A suite of `curl`-based tests to verify that the Nchan server endpoints and metadata enrichment are working correctly.
```bash
# Ensure local docker is running first
npm run docker:start
./docker/testnchan.sh
```

---

## Building

### Library & Example
The example is bundled using `esbuild`:
```bash
npm run build:all
```

### Lobby (Lit)
The lobby is a single-file implementation using Google Lit, located at `docker/html/lobby.html`. It provides a lightweight, reactive UI for presence, challenges, and chat, designed to be served directly by the Nchan/Nginx container.

### Docker Image
To rebuild the Nchan server image:
```bash
npm run docker:build
```

---

## Development

- **Linting**: `npm run lint`
- **Formatting**: `npm run format`

## Publishing

To release a new version to npm:

```bash
npm run release  # Builds and bumps version
npm login        # Login to npm (if needed)
npm publish      # Publish to npm registry
npm run crossdeploy
```

## Additional Documentation

- **Specification**: See [MESSAGING_SPEC.md](./MESSAGING_SPEC.md) for the API contract and data models.
- **Usage Guide**: See [SKILL.md](./SKILL.md) for a quick reference guide.
- **Architectural Overview**: See [AGENTS.md](./AGENTS.md) for the design patterns used.
