# Core LLM Coding Guidelines

This note contains strict rules and formatting expectations compiled during local agent orchestrator runs. The agent automatically retrieves these guidelines when planning its execution.

---

## 1. Output Format Constraints
* **Use OVERWRITE ALL:** When creating new files or applying major updates, always use the `OVERWRITE ALL` format:
  ```text
  ### OVERWRITE ALL: path/to/file.ext
  <<<<
  full content of the file
  >>>>
  ```
* **Avoid Hallucinated SEARCH/REPLACE:** Do not output `### FILE:` patches with `====` separators on empty files. Only use `SEARCH/REPLACE` for minor, targeted fixes where the original code can be matched exactly.

---

## 2. File Path Safety
* **Omit Directory Prefixes:** When patching files, use paths relative to the target project directory (e.g. `index.html` or `src/main.js`). Do not prefix the project directory name (e.g. write `index.html`, NOT `advanced-kanban/index.html`).

---

## 3. UI and Modal Implementations (HTML & JS Sync)
* **Ensure Dual Implementations:** When designing interactive features (such as modal popups, edit forms, or task drawers):
  1. **HTML:** You must write the actual element wrappers, inputs, and form containers in `index.html`.
  2. **JS:** Bind the modal controls and selectors in `src/main.js`.
* **Triggers Must Exist:** Ensure there is always a visible trigger button (e.g. `id="add-task-btn"` or `class="add-btn"`) on the main body of the page to open the interaction modal. Do not isolate the buttons inside hidden elements.

---

## 4. Python Environment & Headless Compatibility
* **Python f-string Backslashes:** Your code will run on Python versions 3.10 and below. **Never place backslashes inside f-string expressions.** For example:
  - ❌ *Incorrect:* `f"path: {path.replace('\\', '/')}"`
  -  *Correct:* 
    ```python
    normalized_path = path.replace('\\', '/')
    print(f"path: {normalized_path}")
    ```
* **Headless Browser Execution:** When running Playwright or Selenium in background execution environments, always pass no-sandbox and GPU-disabled arguments to avoid Access Violation crashes (`0xC0000005`):
  - Launch arguments: `args=["--no-sandbox", "--disable-gpu"]`
