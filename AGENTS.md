# Rules for Agent (Ponytail mode)
Before writing code, stop at the first rung that holds:
1. Does this need to exist?   → no: skip it (YAGNI)
2. Already in this codebase?  → reuse it, don't rewrite
3. Stdlib does it?            → use it
4. Native platform feature?   → use it
5. Installed dependency?      → use it
6. One line?                  → one line
7. Only then: the minimum that works
Never cut validation, error handling, security, or accessibility.
Write only what the task needs, no bloat, no extra dependencies.