// Built-in daily quotes: offline by design, no API key, no network.
(function (root) {
  var QUOTES = [
    { text: "First, solve the problem. Then, write the code.", author: "John Johnson" },
    { text: "Simplicity is the soul of efficiency.", author: "Austin Freeman" },
    { text: "The best way to predict the future is to invent it.", author: "Alan Kay" },
    { text: "Programs must be written for people to read, and only incidentally for machines to execute.", author: "Harold Abelson" },
    { text: "Talk is cheap. Show me the code.", author: "Linus Torvalds" },
    { text: "It is not the language that makes programs, but the programmer.", author: "Unknown" },
    { text: "Make it work, make it right, make it fast.", author: "Kent Beck" }
  ];
  if (typeof module !== "undefined" && module.exports) { module.exports = QUOTES; }
  root.QUOTES = QUOTES;
})(typeof globalThis !== "undefined" ? globalThis : this);
