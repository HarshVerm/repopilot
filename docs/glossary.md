# Glossary

This page explains common RepoPilot and software terms in plain English.

## A

**Agent**

An AI-powered component given a specific job, such as planning, coding, or
debugging.

**Alembic**

The tool that applies versioned changes to the PostgreSQL database structure.

**API**

A set of URLs and data formats that let the frontend communicate with the
backend.

**Artifact**

A saved output of a workflow stage, such as a plan, diff, verification result,
or publication.

## B

**Backend**

The server-side FastAPI application. It owns security checks, business rules,
workflow state, database access, AI calls, and GitHub operations.

**Base commit**

The exact Git commit from which a task started. RepoPilot uses it to detect
stale or conflicting changes.

**Background task**

Work that continues in the backend after the initial HTTP request returns. In
the current application, this work is tied to the backend process.

## C

**Change set**

The exact group of file additions, modifications, and deletions proposed by the
coding agent.

**Chunk**

A bounded piece of source code stored and searched by the RAG system.

**Client ID**

A public identifier telling GitHub which application is requesting OAuth.

**Client secret**

A server-only secret proving that the backend owns the OAuth application.

**Clone**

Downloading a Git repository and its history into a local workspace.

**Commit**

A named snapshot of repository changes in Git.

**CSRF**

Cross-site request forgery. CSRF protection prevents another website from
silently making state-changing requests with a user's RepoPilot cookie.

## D

**Diff**

A text representation of exact line additions and deletions.

**Docker sandbox**

An isolated container where RepoPilot runs repository verification commands
with resource and security limits.

## E

**Embedding**

A list of numbers representing the meaning of text or code. Similar meanings
produce nearby vectors and can be found with semantic search.

**Environment variable**

A configuration value supplied to a process, often used for URLs, feature
settings, and secrets.

**Evaluation**

A repeatable run that measures how well RepoPilot performs on representative
tasks.

## F

**FastAPI**

The Python web framework used by the RepoPilot backend.

**Finite-state machine (FSM)**

A workflow model with known states and rules controlling which transition may
happen next.

**Frontend**

The Next.js application shown in the browser.

## G

**Git**

The version-control system that tracks repository files and history.

**GitHub App**

A GitHub integration installed on selected accounts and repositories. RepoPilot
uses it for repository-scoped access.

**GitHub App installation**

The connection between a GitHub App and a user or organization account,
including the repositories and permissions granted to it.

## H

**HTTP-only cookie**

A browser cookie that JavaScript cannot read. RepoPilot uses it for safer
sessions.

## I

**Index**

Structured, lexical, and vector records built from repository code so it can be
searched efficiently.

**Installation token**

A short-lived GitHub token granting only the permissions and repositories of
one GitHub App installation.

## J

**JWT**

JSON Web Token. RepoPilot signs a short-lived JWT with the GitHub App private
key to prove the App's identity to GitHub.

## L

**Lexical search**

Search based on exact or related words, identifiers, and text.

## M

**Migration**

A versioned script that changes database tables, columns, constraints, or
indexes.

**Modular monolith**

One deployable backend process separated internally into clear modules. This is
RepoPilot's current high-level architecture.

## N

**Next.js**

The React framework used by the RepoPilot frontend.

## O

**OAuth**

A standard authorization flow. RepoPilot uses GitHub OAuth to identify a user
and obtain user-approved access without asking for their GitHub password.

**Operation lock**

A database record that prevents conflicting copies of an operation from running
at the same time.

**Orchestrator**

The service that moves a task through repository preparation, retrieval,
planning, coding, verification, review, and publication.

## P

**pgvector**

A PostgreSQL extension that stores vectors and finds nearby embeddings.

**Polling**

Repeatedly requesting the latest state. The task page polls while a workflow is
active.

**PostgreSQL**

The relational database used as RepoPilot's durable source of truth.

**Private key**

A secret cryptographic key used by RepoPilot to sign GitHub App JWTs. It must
never be sent to the browser or committed to Git.

**Pull request (PR)**

A GitHub proposal to merge changes from one branch into another. RepoPilot opens
pull requests but does not merge them automatically.

## R

**RAG**

Retrieval-augmented generation. RepoPilot searches the repository and supplies
relevant code to an AI model rather than sending every file.

**Readiness check**

An endpoint indicating whether required dependencies are available and the
application can serve real work.

**Reconcile**

Comparing saved task state with durable artifacts to repair a stale or
interrupted representation.

**Reciprocal-rank fusion**

A method for combining several ranked search result lists without treating
their raw scores as directly equivalent.

**Repository**

A Git project containing source files, history, branches, and related GitHub
issues and pull requests.

## S

**Semantic search**

Search based on meaning rather than exact words.

**Session**

The server-managed record proving that a browser is signed in to RepoPilot.

**Source of truth**

The authoritative place for state. PostgreSQL is the source of truth for
RepoPilot task and user data.

**Stale state**

Saved approval or workflow information that no longer matches the current
repository or diff.

**Structural search**

Search using code organization such as class, function, method, and file
symbols.

## T

**TanStack Query**

The frontend library that fetches, caches, refetches, and updates backend data.

**Task event**

A timestamped timeline record describing an important task transition.

**Token**

Depending on context, either a credential used to access an API or a unit of
text processed by an AI model. Credentials must stay secret; AI text tokens are
used for limits and cost measurement.

**Tree-sitter**

A parser used to identify code structures in multiple programming languages.

## V

**Verification**

Running tests, lint, type checking, builds, or other checks against a proposed
change.

## W

**Webhook**

An HTTP request GitHub sends to a public server when an event happens. GitHub
cannot send a webhook to a developer's private localhost.

**Workspace**

An isolated local directory containing the repository clone and task-specific
artifacts.

