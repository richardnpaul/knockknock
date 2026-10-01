---
trigger: always_on
---

# Command Execution and Terminal Rules

These rules govern how terminal commands must be formulated and executed when using `run_command`:

## 1. Never Send Multiline Strings in `CommandLine`
- You **MUST NOT** include raw newlines (`\n`) or multiline strings inside the `CommandLine` parameter of `run_command`.
- Specifically, **NEVER** use multiline `node -e "..."`, `python -c "..."`, or multiline Bash statements spanning multiple lines with unclosed quotes.
- **Why**: Raw newlines inside quotes trigger the shell's secondary continuation prompt (`PS2`, displayed as `> `) and break VS Code/Antigravity Terminal Shell Integration (`OSC 633` hooks). The shell will finish executing the command but fail to emit the termination sequence, causing the command to hang indefinitely as an unfinished background task until a user manually types `exit $?`.

## 2. Use Scratch Scripts for Multi-Line Logic
- If logic requires multiple statements, JSON parsing (e.g., inspecting mutation reports), or file manipulation, you **MUST** write the code to a scratch file first using `write_to_file`.
- Write scratch files to `<conversation-artifact-dir>/scratch/<script-name>.js` or `scratch/<script-name>.js`.
- Execute the script cleanly on a single line:
  ```bash
  node /path/to/scratch/script.js
  ```
- Remove or clean up the scratch file after completion if no longer needed.

## 3. Strict Single-Line Formatting for Inline Commands
- If running a quick inline command (e.g., `node -e`, `python -c`, `sed`, `awk`), it **MUST** be strictly formatted as a single line using semicolons, without any line breaks:
  ```bash
  # Correct:
  node -e "const fs = require('fs'); console.log(fs.existsSync('dist'));"

  # Incorrect (Hangs the terminal):
  node -e "
  const fs = require('fs');
  console.log(fs.existsSync('dist'));
  "
  ```

## 4. Explicit Subshell Execution When Needed
- For compound commands or commands where terminal completion might be ambiguous, wrap the command in a non-interactive subshell:
  ```bash
  bash -c 'command1 && command2'
  ```
- Or append an explicit exit code forwarder when the shell must terminate immediately upon completion:
  ```bash
  command ; exit $?
  ```

## 5. Never Idle on Hanging Background Tasks
- Commands expected to complete quickly (< 10 seconds) that get sent to the background should not be left unattended.
- If a short-running command has not completed within a reasonable window, check its status with `manage_task` (`action: "status"`), kill it if stalled (`action: "kill"`), and investigate rather than waiting indefinitely.
