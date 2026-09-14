"""Opt-in tracker adapters.

A tracker adapter knows one issue tracker's API and field model. Nothing in this
package is registered by :func:`harness_core.cli.build_core_parser` — the core
command surface is tracker-agnostic by contract, and a project opts in by
calling an adapter's ``register_*_commands`` from its own ``project.py``.

The dependency direction is one-way: adapters may import ``io`` / ``local`` /
``git``; no core module imports this package. That is what keeps a project on a
different tracker from paying for this one.

Project constants — owner, repo, project number, field and option names — are
injected by the caller. An adapter that names them would stop being shared code.
"""
