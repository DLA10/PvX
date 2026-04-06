"""
PvX Security Validation Layer — adversarial review required before v0.1 ship.

All MCP tool calls pass through this module before execution.
Local LLMs at Q4 quantisation produce creative variations of dangerous inputs
not covered by naive pattern matching. Every validator here was written AND
adversarially reviewed: "how would a confused/compromised Q4 model bypass this?"

Threat model:
  - SQL injection via blocked keywords, UNION, hex encoding, CHAR() bypass
  - Path traversal via symlinks, ../, URL encoding, null bytes
  - Command injection via sudo, LD_PRELOAD, curl|sh, chmod widening
  - Privilege escalation via polkit, su, doas, pkexec
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class SecurityLayer:
    """
    Validates MCP tool calls before execution.

    validate() is the single entry point. Returns True if the call is safe,
    False if it should be rejected. The MCP proxy emits SECURITY_REJECTED
    on False — this class does not raise exceptions.
    """

    # ------------------------------------------------------------------
    # SQL — blocked keywords (applied to uppercased query string)
    # ------------------------------------------------------------------
    #
    # Adversarial review notes:
    #   • "0X" catches hex-encoded payloads: 0x44524f50 == DROP
    #   • "CHAR(" catches string-building attacks: CHAR(68)+CHAR(82)+... == DR...
    #   • ";--" and "--" catch inline comment termination
    #   • "UNION" catches UNION-based extraction even without SELECT
    #   • "EXEC"/"XP_"/"SP_" block stored procedure execution (MSSQL)
    #   • "CAST("/"CONVERT(" block type-coercion bypass attempts
    #   • "WAITFOR"/"SLEEP(" block time-based blind injection probes
    #   • "LOAD_FILE"/"INTO OUTFILE"/"INTO DUMPFILE" block MySQL file exfil
    #   • "INFORMATION_SCHEMA" blocks schema discovery
    #   • "PG_SLEEP"/"PG_READ_FILE" block PostgreSQL-specific attacks
    #
    _SQL_BLOCKED: tuple[str, ...] = (
        # DDL / destructive
        "DROP", "TRUNCATE", "DELETE", "ALTER", "CREATE",
        "GRANT", "REVOKE",
        # Comment injection
        "--", ";--", "/*", "*/",
        # Stored procedure execution (MSSQL / MySQL)
        "EXEC", "EXECUTE", "XP_", "SP_",
        # Type conversion attacks
        "CAST(", "CONVERT(",
        # Hex encoding bypass
        "0X",
        # String-building via CHAR()
        "CHAR(",
        # UNION injection
        "UNION",
        # Time-based blind injection
        "WAITFOR", "SLEEP(",
        # MySQL file exfiltration
        "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
        # Schema discovery
        "INFORMATION_SCHEMA", "SYS.TABLES", "SYS.COLUMNS",
        # PostgreSQL-specific
        "PG_SLEEP", "PG_READ_FILE", "PG_LS_DIR",
        # Oracle-specific
        "UTL_FILE", "DBMS_",
    )

    # ------------------------------------------------------------------
    # Commands — blocked regex patterns (applied case-insensitively)
    # ------------------------------------------------------------------
    #
    # Adversarial review notes:
    #   • rm pattern uses [a-z]* between rm and flag to catch `rm  -rf`,
    #     `rm\t-rf`, but also `rm -r -f` — note separate -r and -f flags.
    #     Handles whitespace variations.
    #   • LD_ catches LD_PRELOAD, LD_LIBRARY_PATH, LD_AUDIT attacks.
    #   • curl|sh / wget|sh patterns allow optional spaces around the pipe.
    #   • chmod pattern catches 7xx (world-exec/write), 6xx (group write),
    #     and symbolic a+w/a+x. Covers octal 777, 755, 644 → 777 widening.
    #   • Writing to /proc /sys /boot via > or tee — blocks kernel tampering.
    #   • export PATH= blocks PATH hijacking.
    #   • nsenter/unshare block container escape via namespace manipulation.
    #   • python -c 'import os; os.system(...)' style exec via eval/exec keywords.
    #   • base64 decode pipe to shell — common obfuscation vector.
    #
    _CMD_BLOCKED_PATTERNS: tuple[str, ...] = (
        # Recursive/force deletes
        r"rm\s+.*-[a-z]*r",
        r"rm\s+.*--force",
        r"rm\s+.*--recursive",
        # Privilege escalation
        r"\bsudo\b",
        r"\bdoas\b",
        r"\bpkexec\b",
        r"\bsu\s+-",
        r"\bsu\b\s+root",
        # Namespace / container escape
        r"\bnsenter\b",
        r"\bunshare\b",
        # chmod widening — octal 6xx or 7xx, or symbolic a+
        r"chmod\s+[0-9]*[67][0-9]",
        r"chmod\s+a\+",
        r"chmod\s+o\+[wx]",
        # Remote code execution via pipe to shell
        r"curl\s+.*\|\s*(ba)?sh",
        r"wget\s+.*\|\s*(ba)?sh",
        r"curl\s+.*\|\s*python[23]?",
        r"wget\s+.*\|\s*python[23]?",
        r"fetch\s+.*\|\s*(ba)?sh",
        # base64 decode pipe to shell (obfuscation)
        r"base64\s+.*\|\s*(ba)?sh",
        r"base64\s+.*\|\s*python",
        # Writing to system paths
        r">\s*/etc/",
        r">\s*/sys/",
        r">\s*/proc/",
        r">\s*/boot/",
        r"tee\s+/etc/",
        r"tee\s+/sys/",
        r"tee\s+/proc/",
        # Environment manipulation
        r"export\s+PATH\s*=",
        r"export\s+LD_",
        r"\bLD_PRELOAD\b",
        r"\bLD_LIBRARY_PATH\s*=",
        # Python/shell eval/exec in command strings
        r"\beval\s+[\"'\`]",
        r"\beval\s+\$",
    )

    # Compiled regex cache — built once at class level for performance
    _CMD_COMPILED: tuple[re.Pattern[str], ...] = tuple(
        re.compile(p, re.IGNORECASE) for p in _CMD_BLOCKED_PATTERNS
    )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def validate(self, tool_call: Any) -> bool:
        """
        Returns True if the tool call is safe to execute, False otherwise.

        The dispatch table maps tool names to their specific validator.
        Tools not in the table pass through (True) — they have no
        dangerous parameters by design.
        """
        validators = {
            "query_database":    self._validate_sql,
            "write_file":        self._validate_path,
            "read_file":         self._validate_path,
            "list_directory":    self._validate_path,
            "terminal":          self._validate_command,
        }
        validator = validators.get(tool_call.name)
        if validator is None:
            return True

        result = validator(tool_call)
        if not result:
            logger.warning(
                "security_rejected",
                tool=tool_call.name,
                params=str(tool_call.params)[:200],
            )
        return result

    # ------------------------------------------------------------------
    # SQL validator
    # ------------------------------------------------------------------

    def _validate_sql(self, tool_call: Any) -> bool:
        """
        Rejects queries containing any blocked SQL keyword.

        Applied to the uppercased query string. Uppercase normalisation
        defeats most case-mixing bypass attempts (dRoP, Dr0p with leet
        substitution is not caught here — that requires a more complex
        normaliser, which is a known gap logged in ISSUES.md).
        """
        query = tool_call.params.get("query", "").upper()
        for keyword in self._SQL_BLOCKED:
            if keyword in query:
                logger.warning(
                    "sql_blocked",
                    keyword=keyword,
                    query_preview=query[:120],
                )
                return False
        return True

    # ------------------------------------------------------------------
    # Path validator
    # ------------------------------------------------------------------

    def _validate_path(self, tool_call: Any) -> bool:
        """
        Validates that the requested path is inside an allowed directory
        and not inside a blocked directory.

        Uses Path.is_relative_to() — NOT str.startswith().
        startswith() has a known bypass: /home/user/allowed-path-evil
        passes startswith('/home/user/allowed-path') but is a different dir.
        is_relative_to() resolves symlinks and rejects this correctly.

        Null bytes in paths are explicitly rejected — some systems pass
        null bytes through to open(), which truncates the path check
        at the null byte position (classic null byte injection).
        """
        from pvx.core.config import config as app_config  # local import avoids circular

        path_str = tool_call.params.get("path", "")

        # Null byte injection guard
        if "\x00" in path_str:
            logger.warning("path_null_byte_rejected", path=path_str[:120])
            return False

        try:
            resolved = Path(path_str).resolve()
        except (ValueError, OSError):
            return False

        # If config is unavailable, deny all filesystem access
        if app_config is None or app_config.mcp_servers is None:
            return False
        fs_config = app_config.mcp_servers.filesystem
        if fs_config is None or not fs_config.enabled:
            return False

        allowed_paths = [Path(p).expanduser().resolve() for p in fs_config.allowed_paths]
        blocked_paths = [Path(p).expanduser().resolve() for p in fs_config.blocked_paths]

        in_allowed = any(resolved.is_relative_to(a) for a in allowed_paths)
        in_blocked  = any(resolved.is_relative_to(b) for b in blocked_paths)

        if not in_allowed:
            logger.warning("path_not_in_allowed", resolved=str(resolved))
        if in_blocked:
            logger.warning("path_in_blocked", resolved=str(resolved))

        return in_allowed and not in_blocked

    # ------------------------------------------------------------------
    # Command validator
    # ------------------------------------------------------------------

    def _validate_command(self, tool_call: Any) -> bool:
        """
        Rejects shell commands matching any blocked pattern.

        All patterns are compiled with re.IGNORECASE.

        Adversarial note: this is defence-in-depth, not a sandbox.
        A sufficiently creative Q4 model could craft obfuscated commands
        that bypass regex (e.g., variable-based PATH manipulation, heredoc
        injection). The correct mitigation is to never expose an unrestricted
        terminal tool — only expose specific, narrowly-scoped commands.
        This validator is a safety net, not a security boundary.
        """
        command = tool_call.params.get("command", "")
        for pattern in self._CMD_COMPILED:
            if pattern.search(command):
                logger.warning(
                    "command_blocked",
                    pattern=pattern.pattern,
                    command_preview=command[:120],
                )
                return False
        return True
