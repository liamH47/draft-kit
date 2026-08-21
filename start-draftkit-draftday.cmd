@echo off
REM Draft day launcher. Refreshes every source, then runs pinned to disk so
REM no board refresh can wait on a slow feed. Use this one on the morning of
REM a draft; use start-draftkit.cmd the rest of the time.
call "%~dp0start-draftkit.cmd" offline
