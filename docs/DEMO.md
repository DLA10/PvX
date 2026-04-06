# PvX Demo Script

Follow these steps to demonstrate the full power of PvX.

1. **The Doctor**: Show the dependency check.
   ```bash
   pvx doctor
   ```

2. **The Start**: Launch the platform.
   ```bash
   pvx start
   ```

3. **The Web UI**: Open `http://localhost:8765`.
   - Point out the VRAM live monitor.
   - Show the empty orchestration feed.

4. **Claude Delegation**: Run a command in Claude Code.
   ```bash
   claude -p "Generate docstrings for all files in src/pvx/core/"
   ```

5. **Observe the Swap**: 
   - Watch the Web UI as PvX classifies the task as `docstrings`.
   - Watch the VRAM manager unload Qwen-14B and load Qwen-3B.
   - Observe the feed as Claude delegates the work.

6. **The Shadow Terminal**: Collapse and show the raw system actions (file writes, etc.).

7. **The Savings**: Go to the Cost panel and show the 98%+ token savings.
