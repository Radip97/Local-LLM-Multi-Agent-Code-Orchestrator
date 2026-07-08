# LocalStorage Developer Guide & Constraints

This guide documents standard integration patterns, structural recommendations, and technical limitations when persisting client state using browser `localStorage`. 

---

## 1. Best Practices
* **Unique Namespacing:** Always prefix your storage keys to prevent collisions with other local apps. 
  - ❌ *Incorrect:* `localStorage.setItem('tasks', ...)`
  -  *Correct:* `localStorage.setItem('kanban_board_tasks_state', ...)`
* **Robust Try-Catch Wrappers:** Raw storage strings can easily become corrupted or null. Always wrap `JSON.parse` queries inside `try/catch` blocks:
  ```javascript
  function loadState() {
      const stored = localStorage.getItem('kanban_board_tasks_state');
      if (!stored) return [];
      try {
          return JSON.parse(stored);
      } catch (error) {
          console.error("Failed parsing localStorage state:", error);
          return [];
      }
  }
  ```
* **Escape Input Data:** When pulling raw text fields (like task descriptions) from stored JSON and injecting them into the DOM, always sanitise the HTML to protect against Cross-Site Scripting (XSS). Use `textContent` or a sanitization helper instead of `innerHTML`.

---

## 2. Architectural Tips
* **Single Source of Truth:** 
  - Keep an active state array/object in your JavaScript memory (e.g. `let tasks = []`).
  - Use `localStorage` purely as a **write-behind cache** (write to it when mutations happen, read from it *only once* at app startup).
  - Do not constantly query `localStorage` directly in your rendering functions.
* **Mutation Sync Triggers:** Call your save functions (e.g. `saveState()`) immediately following these specific state mutations:
  - Inside the drop zone event handler after a task moves columns.
  - Inside the task creation submission handler.
  - Inside the task delete event listener.

---

## 3. Programming Constraints
* **Synchronous & Blocking:** `localStorage` runs on the main browser thread. Avoid writing huge data objects inside high-frequency cycles (like scrolling, drag-over animations, or window resize loops).
* **Size Limitations:** Most modern desktop browsers enforce a strict **5MB quota limit** on `localStorage`. Do not attempt to store images, files, or large data payloads.
* **String-Only Storage:** Remember that `localStorage` only stores strings. You must serialise complex objects into JSON strings using `JSON.stringify()` before writing.
