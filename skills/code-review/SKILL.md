---
name: code-review
description: Comprehensive guidelines for reviewing code quality, security vulnerabilities, design patterns, and performance.
---

# Code Review Skill

When performing a code review, always follow these structured steps:

1. **Architecture & Design**:
   - Check if classes and functions follow the Single Responsibility Principle.
   - Check naming conventions and code readability.
2. **Security & Vulnerabilities**:
   - Check for command injection flaws, path traversal, unsafe execution, and unsanitized inputs.
   - Verify proper permission controls and sensitive credential handling.
3. **Error Handling & Edge Cases**:
   - Ensure proper exception handling instead of broad silent `except: pass`.
   - Check resource cleanups (e.g., file descriptors, network connections).
4. **Performance & Efficiency**:
   - Identify redundant computations or repetitive disk/network IO operations inside loops.

### Required Output Format
Always structure your review response with the following sections:
- **Summary**: High-level verdict (Approved / Needs Work / Major Flaws).
- **Critical Issues**: Immediate blockers, security bugs, or functional errors.
- **Suggestions for Improvement**: Readability, maintainability, or minor optimizations.
- **Positive Observations**: Well-designed patterns observed in the code.
