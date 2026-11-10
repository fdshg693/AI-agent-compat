"""Helpers shared by the Claude-only hooks (formerly ``.claude/hooks/_lib``).

Import them with ``from .common.<module> import <name>`` (function imports):
the builder inlines every module into one namespace, so ``runtime.foo()``
style module access does not survive the build.
"""
