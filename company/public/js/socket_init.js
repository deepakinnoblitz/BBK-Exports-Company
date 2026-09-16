// socket_init.js
console.log("Initializing Socket.IO connection...");

const socket = io("https://erp.innoblitz.in", {
  transports: ["polling", "websocket"],  // Force WebSocket transport (skip polling)
  reconnection: true,          // Auto-reconnect if connection drops
  reconnectionAttempts: 5,     // Retry up to 5 times
  reconnectionDelay: 2000,     // Wait 2 seconds before retry
});

socket.on("connect", () => {
  console.log("✅ Socket connected:", socket.id);
});

socket.on("disconnect", (reason) => {
  console.warn("⚠️ Socket disconnected:", reason);
});

socket.on("connect_error", (error) => {
  console.error("❌ Socket connection error:", error.message);
});

// Example: listen for a realtime event from Frappe
frappe.realtime.on("company_update", (data) => {
  console.log("📢 Received company update:", data);
});
